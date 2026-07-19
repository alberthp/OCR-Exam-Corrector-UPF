# OMR Exam Corrector

Automatic correction of scanned multiple-choice exams (UPF bubble-sheet
format): scans a PDF of filled-in answer sheets, matches each page to a
student, grades it against an answer key (with support for shuffled exam
permutations), and produces an Excel gradebook plus a visually annotated PDF
for review — with a desktop GUI to fix any mismatches by hand.

## What it does

1. **Reads each scanned page**: corrects perspective/skew, locates the
   bubble grid via alignment markers, and reads identification fields
   (U-number, DNI, PARCIAL, PERMUT, GRUP) and every answer bubble — purely
   from filled-in bubbles, no OCR of handwriting.
2. **Validates the answer key before grading**: checks the permutation
   answer-key file for missing or duplicate questions per permutation — the
   kind of copy/paste slip that would otherwise silently under-grade or
   mis-grade an entire permutation — and proposes a one-click fix instead of
   grading against a broken key.
3. **Matches and grades**: looks up the student by U-number, grades against
   the answer key for *that page's own* permutation (each page can use a
   different shuffled key), with partial credit for multi-answer questions.
   If the student list includes a theory-group column, the scanned GRUP
   field is cross-checked against it (and backfilled when unreadable).
4. **Generates output**: `results.xlsx` (one sheet per permutation, a flat
   per-theory-group roster, and a summary) and `annotated_review.pdf` (the
   scan with vector-graphics overlays — coloured boxes per bubble, ID field
   values, traffic-light status per page).
5. **Lets you review and fix mistakes**: a page-by-page review screen shows
   the annotated page next to an editable form — including a live per-question
   and total score in the answers grid — corrections save immediately (and
   persist across sessions), with a one-click "Revert to original" and
   "Rescan this page" if the OCR read something wrong.

## Desktop app

Run `python omr_gui.py` (or the packaged `.exe` — see below). Three screens:

- **Start** — evaluate a new exam, or reopen a previous run for review.
- **New exam** — pick the scanned PDF, student list, and answer key; runs
  the pipeline in the background with live per-page progress, then switches
  straight into review.
- **Review** — search for a student by name, surname, or U-number to jump
  straight to their page, or step through pages one at a time; fix
  identification fields (U-Number, DNI, Group, Partial, Permutation, Exam
  type) and answer marks, zoom (`+`/`-`, `Ctrl`+scroll wheel) and pan
  (middle-click drag) the annotated preview. Toggle **"Show expected
  answers"** to overlay blue diagonal slashes on every bubble the answer
  key marks correct — a visual aid for the reviewer that never modifies the
  underlying scan. Every correction is saved automatically (`results.xlsx`
  and `annotated_review.pdf` updated immediately) and a `review_cache.pkl`
  lets the same session be reopened later. The "Apply correction" button
  turns orange while a change hasn't fully reached disk yet, and back to
  normal once it has.

Manually-added/removed answer marks and manually-edited Group/Partial/
Permutation values are highlighted in **purple** on the annotated PDF
(circle = added, cross = removed, purple pill = field corrected by hand) so
it's clear at a glance what came from the scanner versus a human correction.
The same orange/purple colouring also appears directly in the review
screen's answer grid, and a one-click **"Export for student review
request..."** button produces a 2-page PDF (raw scan + fully annotated page,
with the expected-answers overlay and colour legend included) named after
the student's identification fields — ready to hand over for a grade-review
request. A **"Send by email..."** button next to it can email that same PDF
straight to the student via your Gmail account (App Password auth, one send
at a time with a preview before anything goes out), using the email address
from the students list or one entered by hand directly in the review screen
if the roster doesn't have one.

See [MANUAL.md](MANUAL.md) for the full step-by-step user manual, and
[INSTALL.md](INSTALL.md) for detailed setup, input file formats, the
command-line interface (`omr_correct.py`), and troubleshooting.

## Running from source

```bash
pip install -r requirements.txt
python omr_gui.py          # desktop GUI
python omr_correct.py exams.pdf students.csv answers.csv --questions 10   # CLI
```

Requires Poppler (`pdftoppm`/`pdfinfo`/`pdfimages`) to be installed and on
PATH — see [INSTALL.md](INSTALL.md) for platform-specific instructions.

## Running the test suite

```bash
pip install -r requirements-dev.txt
pytest                        # everything, including a real OCR pass (~2.5 min)
pytest -m "not integration"   # fast unit/GUI suite only (~19s, no real exam data needed)
pytest -m packaging --packaged-exe <path>   # opt-in: drives an already-built frozen .exe
```

214 tests, organized around every bug class found in past review passes,
plus a dedicated stability suite (malformed input, real thread lifecycle,
a packaged-.exe smoke test) — see [TEST_SUITE.md](TEST_SUITE.md) for the
full design and latest results. **v1.8: all tests passing** (206/206
runnable, 8 self-skip for absent private data), including the opt-in
packaged-`.exe` smoke test verified clean against the actual release
binary immediately before tagging.

## Standalone Windows executable

A pre-built, self-contained `.exe` doesn't need Python or Poppler installed
on the target machine — everything (Python runtime, OpenCV/NumPy/SciPy,
PySide6, `keyring`, and a standalone Poppler build) is bundled.

To build it yourself:

```powershell
pip install pyinstaller
pytest -m "not integration"                         # optional but recommended: fast gate before packaging
python -m PyInstaller --noconfirm "OMR Exam Corrector.spec"
```

`poppler_bin/` must be populated with the real Poppler binaries first — it's
gitignored (~19MB of third-party binaries) and ships empty except for
instructions. See [`poppler_bin/README.md`](poppler_bin/README.md) for the
exact file list and download link; the build will still "succeed" without
them, but the resulting `.exe` won't be able to render PDFs on a machine
that doesn't already have Poppler installed and on PATH — defeating the
point of a standalone build.

The runnable app is `dist\OMR Exam Corrector\OMR Exam Corrector.exe` (the
whole `dist\OMR Exam Corrector` folder must be copied/distributed together —
`build\` is just PyInstaller's intermediate scratch space and isn't
runnable). No installer: copy the folder anywhere and run the `.exe`.

Three things worth knowing when building or distributing it:

- **Build on a local disk**, not a cloud-synced folder (Google Drive,
  OneDrive, Dropbox...) — running a multi-hundred-file frozen app from a
  cloud-mounted virtual drive is dramatically slower (every DLL load goes
  through the cloud filesystem layer instead of native disk).
- **First launch on a new machine may be slow** (antivirus/EDR products
  often deep-scan an unsigned, unfamiliar multi-DLL executable the first
  time they see it). On a managed/corporate machine where it never finishes,
  ask IT to whitelist the app's folder or file hash. A startup window (v1.6)
  shows what's loading during this wait, so it doesn't look like the app
  hung with nothing on screen — but the wait itself is unavoidable.
- **`keyring` (used by the email feature) needs an explicit hidden-import**:
  it picks its OS credential-store backend at runtime via `importlib.metadata`
  entry points, which PyInstaller's static import analysis can't see. This
  is already handled in `"OMR Exam Corrector.spec"`
  (`hiddenimports=['keyring.backends.Windows']`) — if you ever add a new
  keyring-dependent feature or target a different OS, that list needs the
  matching backend module too, or "Email settings..." fails in the frozen
  build with "No recommended backend was available" despite working fine
  from source.

## What's new in v1.8

- **Fixed a wrong-digit misread caused by printed header artwork**: a
  real scan showed a genuine student mark (row 1 of an ID column)
  silently losing out to the printed decorative artwork sitting just
  above row 0 of every ID column — on a faint enough scan, that artwork's
  peak could actually outscore the real mark and get returned as the
  digit. `read_digit_marker_anchored()`'s row-alignment tolerance is
  tightened (70%→45% of row spacing) and now falls through to the next-
  best candidate instead of giving up when the top peak is misaligned.
  Confirmed fix on the real page that reported it: `049700` → `149700`.
  A second, genuine case (a student marking two different rows in one
  column) is now surfaced as a "Multiple marks detected" warning instead
  of being silently resolved.
- **Stability fixes for two real close/navigation gaps**: closing the
  app while an exam scan was still running was never guarded (only
  review-screen saves/renders were) — the same class of hazard that
  caused a confirmed native crash previously. Clicking "Back to start"
  during a running scan had the same gap on the navigation side, plus a
  worse symptom: the background scan would finish later and forcibly
  jump the user to the Review screen regardless of where they'd
  navigated to since. Both now block with a "please wait" message,
  mirroring the existing review-screen guard.
- **`_config_dir()` now falls back gracefully** instead of raising a raw,
  unhandled exception out of "Email settings..." or "Send by email" if
  the per-user config directory can't be created (e.g. a locked-down
  `APPDATA` in a managed environment) — falls back to a system-temp
  location rather than breaking the feature outright.
- **New stability test suite** (`tests/test_stability_*.py`, ~40 new
  tests): malformed/adversarial input handling (corrupt PDFs/Excel/CSV,
  pathological images, locked output files), real `QThread` lifecycle
  (not mocked busy-flags), a static guard against the exact import
  mistake that caused the v1.6 native crash, a real subprocess
  end-to-end run (New Exam → scan → Review → close) with a memory-growth
  regression check, and a new opt-in packaged-`.exe` smoke test that
  builds and drives the actual frozen binary (not just source) through
  the same full lifecycle — the only test technique that can catch a
  packaging-specific regression at all. Also fixed a related bug this
  work turned up: `detect_markers()` threw an unhandled `TypeError` on a
  degenerate (e.g. 1px-wide) input image instead of its documented
  "not found" contract.
- **Fixed a real native crash from rapid Review-page navigation**: while
  building the packaged-`.exe` smoke test above, one run hit a
  `STATUS_STACK_BUFFER_OVERRUN` (the same signature as the v1.6 crash)
  during review-page navigation. Unlike v1.6, this one didn't reproduce
  from a plain scripted run — it took a dedicated stress test firing page
  navigation back-to-back with no delay, which then reproduced it
  reliably. Root cause: navigation is only gated by whether a *save* is in
  progress, not by pending preview renders, so fast repeated navigation
  could spawn many concurrent `_PreviewRenderWorker` threads — each
  launching its own poppler subprocess against the same PDF file.
  Bisecting on real data pinned the threshold exactly: 5 concurrent
  renders never crashed across repeated trials, 6+ crashed with real,
  non-deterministic probability — the signature of a genuine race, not
  environmental noise. Fixed by capping concurrent preview-render workers
  (`PREVIEW_WORKER_CAP = 2`) and re-checking the current target reactively
  once a slot frees, rather than firing a new worker on every navigation
  call. Two more bugs surfaced and got fixed while building that fix: a
  worker could spawn a spurious duplicate for the page it had *just*
  finished (checking the cache before it was actually written), and a
  failed render could retry the same failing page forever (a failure is
  never cached, so it never looked "already resolved"). Verified clean
  across every reproduction attempt that previously crashed reliably, in
  both the packaged `.exe` and from source — see TEST_SUITE.md's
  "Packaged-.exe smoke test" section for the full investigation.

## What's new in v1.7

- **Stability fix for a packaged-.exe crash**: v1.6's startup window (see
  below) imported `gui.main_window` — which touches `PySide6.QtWidgets` —
  from a background thread. Pure Python imports are thread-safe, but
  PySide6/Qt can do thread-affinity-sensitive static initialization the
  *first* time one of its submodules is touched; doing that off the main
  thread silently corrupted Qt's internal state without crashing
  immediately, only to fail unpredictably later (confirmed against two
  real native crashes in the packaged `.exe`, both faulting in
  `Qt6Core.dll` at the same offset, well after startup had already
  finished — once mid-scan, once mid-review). `gui.main_window` is now
  imported back on the main thread; only the genuinely Qt-independent
  libraries (cv2, numpy, pandas, scipy, pdf2image, reportlab) still run on
  the background thread.
- **Run Analysis now also requires an Exam type**: the button used to turn
  green as soon as the three files were selected, before Exam type had
  been set. It's a required field for the green state now, though it
  still doesn't block the run itself (Exam type can be set later from the
  review screen).
- **Softer Run Analysis green**: matching the softer red from v1.6, the
  ready-state green is now a lighter pastel tone instead of the legend's
  saturated "Correct" green.

## What's new in v1.6

- **Startup window**: a small window appears the moment the app launches,
  showing the name/version and a log of what's loading — first launch on a
  new machine can take a while (antivirus/EDR scanning, cold disk cache for
  the image-processing libraries), and previously nothing appeared on
  screen at all during that wait, which could look like the app had hung
  or crashed. The slow imports run on a background thread while this
  window stays genuinely responsive and adds a heartbeat dot once a second,
  so it never looks frozen or gets marked "(Not Responding)" by Windows. It
  closes itself once the main window is ready.
- **Run Analysis is colour-coded**: a soft red until the scanned PDF,
  students list, and answers file are all selected, green once they are —
  green matches the same "Correct" colour used elsewhere in the app (the
  annotated PDF's legend), while red is deliberately a lighter, easier-on-
  the-eyes tone rather than that same legend's saturated "Wrong" red, since
  this button sits on screen throughout instead of appearing briefly.

## What's new in v1.5

- **Manual email entry**: the review screen's new **Email** field shows the
  matched student's address from the roster, but stays editable even when
  there isn't one — type an address in by hand and it's remembered for
  that student (and written into `results.xlsx`'s Email column, adding it
  if the students list didn't have one) instead of blocking "Send by
  email..." outright.
- **Editable email body template as a plain text file**: the body template
  now also lives in its own `.txt` file in the app's config folder, openable
  and editable directly in any text editor via a new **"Open template
  file..."** button in Email settings — not just the dialog's text box.
- **English default email templates with exam type**: the default
  subject/body are now in English and include the student's name, surname,
  U-Number, and group, plus a new **Exam type** (Midterm/Final/Retake)
  setting — picked once per run (or corrected later in the review screen)
  and substituted into emails via `{exam_type}`.
- **Search the Pages table**: a new search box in the review screen filters
  by name, surname, or U-number and jumps to the matching page on click —
  no more scrolling through a long roster to find one student.

## What's new in v1.4

- **Answer-key validation**: before grading starts, the answer key is
  checked for questions missing or duplicated within a permutation — errors
  that previously graded silently (a missing question was just excluded
  from that permutation's max score; a duplicate let the last row win, with
  no indication anything was wrong). The GUI shows a dialog listing every
  issue, with a one-click **"Apply fix"** for the common case (a `Perm`
  value copy/pasted one row too early), a button to open the file for
  manual review, and the choice to continue anyway or cancel. The CLI
  prints the same issues and refuses to proceed unless you pass
  `--ignore-answer-key-warnings`.
- **Two more student-list formats**: alongside the existing plain
  `Nom/Cognom1/Cognom2/U_number` format and the UPF `IDUSUARI` export, the
  students list now also accepts a Moodle "participants" export
  (`Cognoms`/`Número ID`/`Grups`) and a UPF `llistatGGiA` export
  (`EMAIL`/`PRACTICA`). Both formats' group column is parsed into a theory
  group used for GRUP cross-checking below; the `llistatGGiA` format's
  email is carried through into `results.xlsx`.
- **GRUP cross-check and backfill**: when the student list has a theory
  group per student, each page's scanned GRUP value is compared against
  it — backfilling it when the bubble wasn't readable, and flagging a
  mismatch for review otherwise — via a new `GRUP_Check` column in
  `results.xlsx` and a teal ("from roster") / red ("mismatch") pill on the
  annotated PDF, distinct from the green scanned-value pill.
- **T1/T2 roster tabs**: `results.xlsx` now includes a flat DNI/U-Number/Score
  sheet per theory group, cutting across exam permutations — useful for
  handing a single theory-group instructor just their students' scores.
- **Live scoring in the review grid**: the answers grid in the review screen
  now shades every option the answer key marks correct, shows a per-question
  score in a trailing column, and totals it in a footer — all of which
  update immediately as you toggle a mark, before you click **"Apply
  correction"**.
- **Reliability fix**: ID-field box detection (used to validate perspective
  correction and to draw the annotated PDF's field outlines) was rejecting
  some genuinely-present boxes — most often ASSIGNATURA and occasionally
  CENTRE — on scans where their printed content happened to have a lower
  ink density than usual, incorrectly flagging otherwise-good pages for
  manual review.

## What's new in v1.3

- **Student review-request export**: a new "Export for student review
  request..." button in the review screen writes a 2-page PDF for the
  current page (raw scan + fully annotated page, complete with the
  expected-answers overlay and colour legend) with a suggested filename
  built from the student's U-number, group, partial, and permutation
  (e.g. `U225659_T1_Q2_P2.pdf`).
- **Answer-grid manual-mark colouring**: cells in the review screen's answer
  grid turn orange when toggled but not yet saved, and bold purple once
  saved if they don't match what the scanner detected — so a hand-corrected
  answer is never confused with an automatically detected one, even after
  reopening the session.
- **Reordered identification fields**: the review screen's right-hand panel
  now lists U-Number, DNI, Group, Partial, Permutation (previously
  U-Number, DNI, Partial, Permutation, Group).

## What's new in v1.2

- **Expected-answers overlay** in the review screen: click "Show expected
  answers" in the preview toolbar to display blue diagonal-slash outlines
  over every bubble the answer key marks correct for the current page's
  permutation. The overlay is purely visual (the underlying scan is
  unchanged), scales with zoom, and is off by default.

## Project structure

```text
omr_correct.py            OCR/grading pipeline + CLI entry point
omr_gui.py                GUI entry point (also bootstraps bundled Poppler)
email_utils.py             Gmail SMTP send + credential/template storage for review-PDF emails
gui/
  app_info.py                app name/version/author constants (no heavy imports -- see docstring)
  startup_splash.py          "loading..." window shown while omr_gui.py's slow imports run
  start_screen.py           landing screen (new exam / review existing)
  new_exam_screen.py        input form + background OCR run
  review_screen.py          page-by-page review/correction screen
  email_dialogs.py          email settings + send-preview dialogs
  main_window.py            wires the three screens together
tests/                     pytest suite (214 tests, all passing) -- see TEST_SUITE.md
  conftest.py                shared fixtures (synthetic data only)
  test_*.py                  one file per module/concern
  test_stability_*.py        crash-resistance: malformed input, real thread
                              lifecycle, packaged-.exe smoke test
  _e2e_driver.py              not a test file -- entry point for the
                              subprocess/packaged-.exe end-to-end tests
assets/
  upf_logo.png              logo shown on the start screen
  screenshots/              screenshots embedded in MANUAL.md
poppler_bin/              bundled standalone Poppler binaries (for the .exe build;
                           gitignored/empty until populated -- see poppler_bin/README.md)
"OMR Exam Corrector.spec" PyInstaller build configuration
pytest.ini                 pytest markers/config
requirements.txt          Python dependencies
requirements-dev.txt      + pytest, for running the test suite
INSTALL.md                detailed setup, file formats, CLI reference, troubleshooting
MANUAL.md                 step-by-step user manual
TEST_SUITE.md             test suite design + latest run results
RELEASE_REVIEW_v1.4.md    pre-release bug audit + documentation review
```

## Author

Albert Hernansanz (with Claude)
