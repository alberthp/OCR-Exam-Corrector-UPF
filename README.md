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
2. **Matches and grades**: looks up the student by U-number, grades against
   the answer key for *that page's own* permutation (each page can use a
   different shuffled key), with partial credit for multi-answer questions.
3. **Generates output**: `results.xlsx` (one sheet per permutation + a
   summary) and `annotated_review.pdf` (the scan with vector-graphics
   overlays — coloured boxes per bubble, ID field values, traffic-light
   status per page).
4. **Lets you review and fix mistakes**: a page-by-page review screen shows
   the annotated page next to an editable form; corrections save immediately
   (and persist across sessions), with a one-click "Revert to original" and
   "Rescan this page" if the OCR read something wrong.

## Desktop app

Run `python omr_gui.py` (or the packaged `.exe` — see below). Three screens:

- **Start** — evaluate a new exam, or reopen a previous run for review.
- **New exam** — pick the scanned PDF, student list, and answer key; runs
  the pipeline in the background with live per-page progress, then switches
  straight into review.
- **Review** — step through pages, fix identification fields (U-Number, DNI,
  Group, Partial, Permutation) and answer marks, zoom (`+`/`-`, `Ctrl`+scroll
  wheel) and pan (middle-click drag) the annotated preview. Toggle **"Show
  expected answers"** to overlay blue diagonal slashes on every bubble the
  answer key marks correct — a visual aid for the reviewer that never
  modifies the underlying scan. Every correction is saved automatically
  (`results.xlsx` and `annotated_review.pdf` updated immediately) and a
  `review_cache.pkl` lets the same session be reopened later. The "Apply
  correction" button turns orange while a change hasn't fully reached disk
  yet, and back to normal once it has.

Manually-added/removed answer marks and manually-edited Group/Partial/
Permutation values are highlighted in **purple** on the annotated PDF
(circle = added, cross = removed, purple pill = field corrected by hand) so
it's clear at a glance what came from the scanner versus a human correction.
The same orange/purple colouring also appears directly in the review
screen's answer grid, and a one-click **"Export for student review
request..."** button produces a 2-page PDF (raw scan + fully annotated page,
with the expected-answers overlay and colour legend included) named after
the student's identification fields — ready to hand over for a grade-review
request.

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

## Standalone Windows executable

A pre-built, self-contained `.exe` doesn't need Python or Poppler installed
on the target machine — everything (Python runtime, OpenCV/NumPy/SciPy,
PySide6, and a standalone Poppler build) is bundled.

To build it yourself:

```powershell
python -m PyInstaller --noconfirm "OMR Exam Corrector.spec"
```

The runnable app is `dist\OMR Exam Corrector\OMR Exam Corrector.exe` (the
whole `dist\OMR Exam Corrector` folder must be copied/distributed together —
`build\` is just PyInstaller's intermediate scratch space and isn't
runnable). No installer: copy the folder anywhere and run the `.exe`.

Two things worth knowing when building or distributing it:

- **Build on a local disk**, not a cloud-synced folder (Google Drive,
  OneDrive, Dropbox...) — running a multi-hundred-file frozen app from a
  cloud-mounted virtual drive is dramatically slower (every DLL load goes
  through the cloud filesystem layer instead of native disk).
- **First launch on a new machine may be slow** (antivirus/EDR products
  often deep-scan an unsigned, unfamiliar multi-DLL executable the first
  time they see it). On a managed/corporate machine where it never finishes,
  ask IT to whitelist the app's folder or file hash.

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
gui/
  start_screen.py           landing screen (new exam / review existing)
  new_exam_screen.py        input form + background OCR run
  review_screen.py          page-by-page review/correction screen
  main_window.py            wires the three screens together
assets/
  upf_logo.png              logo shown on the start screen
  screenshots/              screenshots embedded in MANUAL.md
poppler_bin/              bundled standalone Poppler binaries (for the .exe build)
"OMR Exam Corrector.spec" PyInstaller build configuration
requirements.txt          Python dependencies
INSTALL.md                detailed setup, file formats, CLI reference, troubleshooting
MANUAL.md                 step-by-step user manual
```

## Author

Albert Hernansanz (with Claude)
