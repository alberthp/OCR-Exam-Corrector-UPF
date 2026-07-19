# Pre-Production Test Suite

Date: 2026-07-19 · Framework: [pytest](https://docs.pytest.org/) 9.1.1 ·
Location: [`tests/`](tests/) · Config: [`pytest.ini`](pytest.ini)

> **v1.8 release status: ALL TESTS PASSING.** 206/206 runnable tests pass
> (214 collected, 8 self-skip for absent private data — see Results
> below), plus the opt-in packaged-`.exe` smoke test verified clean
> (3/3) against the actual frozen release binary under the exact stress
> conditions that reliably crashed it before the fix documented in
> "Packaged-.exe smoke test" below. Confirmed immediately before tagging
> this release.

This project had **zero automated tests** before this suite — every bug
found and fixed in the two prior review passes ([`RELEASE_REVIEW_v1.4.md`](RELEASE_REVIEW_v1.4.md))
was caught by disposable, ad-hoc scripts that were written once, verified,
and deleted. This suite turns that one-off verification into a permanent
regression net: **214 tests**, **100% passing** (of the ones that run —
see the skip notes in Results below), run in **~2.5 minutes**
(~17 seconds without the real-data integration pass).

## How to run it

```bash
pip install -r requirements-dev.txt

pytest                        # everything (~2.5min, needs the real exam files)
pytest -m "not integration"   # fast unit/GUI suite only (~19s, no real data needed)
pytest -m integration         # just the real-data pass
pytest -m "not slow"          # everything except the full OCR pipeline test
pytest -m packaging --packaged-exe <path>   # opt-in: drives an already-built frozen .exe
```

The integration tests in `test_integration_real_data.py` and
`test_stability_e2e_subprocess.py`/`test_stability_packaged_exe.py` use
real exam PDFs and roster/answer-key files (either in the project root or
`testing_dataset/`) — these are gitignored (private student data) and
each integration test **skips itself automatically** if its file isn't
present, so the suite is safe to run (with reduced coverage) on a fresh
checkout that doesn't have them. `packaging`-marked tests additionally
need an explicit `--packaged-exe <path>` and are excluded from every other
run entirely (see "Packaged-.exe smoke test" below).

---

## Design

### Coverage strategy

The two prior review passes found that essentially every real bug in this
project lived in one of three places: **pure data-transformation logic**
(decoding, normalizing, validating, scoring — no I/O, no UI), **file
loading** (four different spreadsheet formats, each with its own parsing
edge cases), and **GUI state management** (what happens when a background
thread is still running, or a page has no data). The suite is organized
around exactly those three layers, in order of how cheaply each layer can
be tested:

| Layer | Files | Tests | Needs a display? | Needs real data? |
|---|---|---|---|---|
| Pure logic | `test_decode_identifier.py`, `test_grup_and_perm_normalization.py`, `test_scoring_and_excel.py` | 50 | No | No |
| File loading | `test_load_students.py`, `test_answer_key.py`, `test_email_utils.py` | 64 | No | No |
| GUI state | `test_review_screen_gui.py`, `test_main_window_gui.py`, `test_new_exam_screen_gui.py`, `test_startup_splash_gui.py` | 39 | Offscreen Qt platform | No |
| Shipped examples | `test_examples.py` | 9 | No | No (synthetic `examples/` files) |
| End-to-end | `test_integration_real_data.py` | 6 | No | Yes (skips if absent) |
| Stability | `test_stability_malformed_input.py`, `test_stability_threading.py`, `test_stability_thread_affinity.py`, `test_stability_e2e_subprocess.py`, `test_stability_packaged_exe.py` | ~43 | Some (`gui`-marked ones) | Some (real-data ones skip if absent) |

All fixture data in the first three layers is **synthetic** (fake names
like "Alice Example", fake U-numbers) — the suite never reads or depends
on real student data except in the explicitly-marked, self-skipping
integration layer. The "shipped examples" layer is a different kind of
synthetic coverage: it doesn't test a function's edge cases, it verifies
that the actual files in `examples/` (the ones a new user opens first)
still load the way `examples/README.md` claims, so a future change to
`load_students()`/`load_correct_answers()` can't silently break the
onboarding path without a test noticing.

**v1.5 additions** followed the same file-loading/GUI-state split: the new
body-template `.txt` file storage (migration from the old JSON-embedded
template, round-tripping, `open_body_template_file()`) landed in
`test_email_utils.py`; the new search box, manual email entry/persistence,
and the `exam_type` whole-run setting landed in `test_review_screen_gui.py`.

**v1.6 additions** are two new GUI-state files: `test_new_exam_screen_gui.py`
covers the Run Analysis button's red/not-ready vs. green/ready colour
state, and `test_startup_splash_gui.py` covers the new startup window
(including a static-source-inspection test that `gui/app_info.py` stays
free of heavy imports -- see that file's docstring for why that's load-bearing,
not just tidiness).

**v1.7** was a stability fix (a packaged-.exe crash traced to importing
`gui.main_window` off the main thread -- see README.md's "What's new in
v1.7") plus extending the Run Analysis ready-state to also require Exam
type; `test_new_exam_screen_gui.py` grew two regression tests for the
latter (files-alone-isn't-enough-anymore, and clearing Exam type turns
the button red again). The crash fix itself isn't unit-testable (it's a
threading/import-order property of the packaged executable, not a
function with a return value) -- it was instead verified by scripting the
real app (New exam -> Review) end to end against the real files the crash
was originally reported against.

**v1.8** shifted focus from *correctness* to *crash resistance* (see
README.md's "What's new in v1.8"). Five new files target failure classes
the rest of the suite structurally cannot: `test_stability_malformed_input.py`
feeds the pipeline corrupt/adversarial input (bad PDFs, corrupt Excel/CSV,
pathological images, a real Windows-locked output file) and asserts clean
failure rather than a hang; `test_stability_threading.py` drives *real*
`QThread`s (not mocked busy-flags) through start/close-during-busy/
back-navigation-during-busy/exception-in-run, and found two real gaps this
way — `MainWindow.closeEvent()` never checked whether a scan was still
running (only review-screen saves/renders were guarded), and "Back to
start" had the same gap on the navigation side; `test_stability_thread_affinity.py`
statically guards every `QThread.run()` body against the exact import
mistake that caused the v1.6 native crash; `test_stability_e2e_subprocess.py`
runs the real app in a real subprocess end-to-end (the only technique that
can catch a native crash from in-process pytest) plus a memory-growth
regression check; `test_stability_packaged_exe.py` goes one step further
and drives an *actually frozen* `.exe` (see "Packaged-.exe smoke test"
below) through the same lifecycle, across all 5 real exams in
`testing_dataset/`, since packaging-specific regressions (missing hidden
imports, bundled-resource paths resolving differently once frozen) are
exactly how the only real crash this project has had actually manifested.
Also fixed along the way: `detect_markers()` threw an unhandled
`TypeError` on a degenerate input image instead of its documented
"not found" contract, and `read_digit_marker_anchored()`'s row-alignment
tolerance was tightened after a real scan showed printed header artwork
above row 0 of an ID column occasionally outscoring a genuine, weaker
student mark.

Building and running the packaged-.exe smoke test itself then surfaced a
second real native crash (see "Packaged-.exe smoke test" below for the
full investigation): rapid Review-page navigation could spawn enough
concurrent `_PreviewRenderWorker` threads to crash natively with real,
non-deterministic probability. Bisected precisely on real data (5
concurrent renders safe, 6+ crashed with real probability) and fixed with
a concurrency cap (`PREVIEW_WORKER_CAP = 2`) plus two more bugs found
while building that fix (a spurious duplicate-worker spawn, and an
infinite retry loop on a failed render). This was a *different* bug from
v1.6's, despite producing the identical `STATUS_STACK_BUFFER_OVERRUN`
OS-level signature -- a reminder that the same crash code doesn't imply
the same root cause.

### Every regression test traces to a specific, previously-real bug

Rather than testing generically "does this function work," most tests are
written as **regression tests for a specific defect that was actually
found and fixed** in this project's history, with the test's docstring
naming the bug. This is deliberate: generic tests tend to test what the
author *assumes* the code does; regression tests test what the code
*actually got wrong once*. The table below is the full traceability map —
every row is a real bug this suite would now catch if it came back.

| Bug (see `RELEASE_REVIEW_v1.4.md` for the full write-up) | Test(s) |
|---|---|
| `Perm` column upcast to float64 by a blank cell breaks permutation routing (Critical) | `test_normalize_perm_value_float_upcast_matches_int_form` |
| `decode_identifier` misreads a missing real digit as a padding zero, returning a *wrong* U-number (Critical) | `test_7_digits_real_digit_missing_*_variant_does_not_guess_wrong` (×2), `test_7_digits_pad_slot_present_but_not_actually_zero_does_not_guess` |
| Review screen silently discards unapplied edits on navigation (Critical) | `test_navigating_away_with_unsaved_changes_prompts_and_blocks_on_no`, `...proceeds_on_yes`, `...proceeds_silently` |
| Rescan page-index race / no busy-state nav lock | `test_busy_state_disables_navigation` |
| `GRUP_Check` false-mismatch: scanned `"01"` vs. roster `"1"` compared as raw strings | `test_backfill_normalizes_padded_scan_before_comparing` |
| Blank `Perm` cell creates a phantom `"nan"` permutation + spurious Excel sheet | `test_validate_flags_blank_perm_cell`, `test_load_correct_answers_skips_blank_perm_row_instead_of_faking_one`, `test_write_excel_does_not_create_phantom_nan_sheet` |
| Two blank-`Perm` rows crash the issue-list sort (`None` vs. `None`) | `test_validate_two_blank_perm_rows_does_not_crash_the_sort` |
| `;`-separated UPF roster export (course-title-only first line) fails to load unconditionally | `test_upf_official_export_semicolon_csv_with_no_separator_on_title_line` |
| Blank `Nom`/`Cognom1`/`Email` cells render as literal `"nan"` | `test_blank_nom_renders_as_empty_string_not_nan`, `test_blank_cognom2_renders_as_empty_string` |
| Answer key with fewer option columns than configured silently zero-scores real answers | `test_validate_flags_missing_option_columns`, `test_missing_option_scores_a_legitimate_mark_as_always_wrong` |
| `ReviewScreen.load()` crashes on a zero-page result set | `test_load_with_zero_pages_does_not_crash` |
| Closing the app mid-save/render can hard-crash the process or corrupt output files | `test_close_blocked_while_local_busy`, `test_close_blocked_while_sync_worker_pending`, `test_close_blocked_while_preview_worker_pending` |
| `fill_template()` crashes on a stray `{`/`}` in a user-edited template | `test_fill_template_unbalanced_open_brace_does_not_crash`, `...close_brace...`, `...positional_field...` |
| Corrupted `email_settings.json` permanently breaks email sending | `test_corrupted_settings_file_falls_back_to_defaults`, `test_settings_file_wrong_json_type_falls_back_to_defaults` |
| Settings/credentials must never land inside the (possibly cloud-synced) project folder | `test_config_dir_is_never_the_project_folder` |
| Printed header artwork above ID row 0 could outscore a real, weaker student mark and misread the digit | `test_artifact_peak_above_row_0_does_not_mask_real_mark_in_row_1` |
| `detect_markers()` raised `TypeError` on a degenerate (e.g. 1px-wide) input image instead of returning "not found" | `test_process_page_tiny_1x1_image_does_not_crash` |
| Closing the app while an exam scan was still running was never guarded (only review-screen saves/renders were) | `test_closing_main_window_while_scan_is_running_does_not_destroy_a_live_thread` |
| "Back to start" during a running scan wasn't guarded, and the scan later force-jumped the user to Review regardless | `test_back_button_blocked_while_scan_is_running` |
| `_config_dir()` raised a raw, unhandled exception if the per-user config directory couldn't be created | `test_config_dir_falls_back_when_primary_location_is_not_writable` |
| Rapid page navigation could spawn 6+ concurrent `_PreviewRenderWorker` threads, crashing natively (`STATUS_STACK_BUFFER_OVERRUN`) with real, non-deterministic probability (Critical) | `test_preview_worker_cap_never_exceeded_during_rapid_navigation` |
| A failed preview render retried the identical failing page forever (never cached, so never "resolved") — introduced and fixed alongside the concurrency cap above | `test_failed_preview_render_does_not_retry_forever` |

### What's deliberately *not* covered

- **Pixel-level OCR correctness** (does the bubble-fill threshold correctly
  read a specific pencil mark) — this needs real scanned images with known
  ground truth, which the project doesn't have as a labeled dataset. The
  integration test's `test_full_pipeline_end_to_end` is the closest proxy:
  it asserts every real page processes without error, but doesn't verify
  the resulting *marks* are correct beyond that.
- **Two known, accepted issues from the review docs** that aren't crash
  bugs, just documented gaps: `score_question` scoring 0 on a "mark every
  option correct" answer-key row (Medium, not fixed — `test_score_good_equals_num_options_returns_zero`
  documents the current behavior rather than asserting a fix), and
  duplicate U-numbers in a roster resolving to "last row wins" everywhere
  (not a bug, just worth knowing — `test_duplicate_u_number_resolves_to_last_roster_row`
  and `test_duplicate_u_number_both_rows_kept` document it).
- **The `_SaveWorker` same-page-edit race** (GUI Critical #2 in the review
  doc) — flagged in the review but not fixed, so not regression-tested
  either; there's nothing fixed yet to protect.

---

## Results

```
206 passed, 8 skipped in 128.52s     # full run (pytest)
198 passed, 5 skipped, 9 deselected in 17.34s   # fast run (pytest -m "not integration")
```

| Test file | Tests | Result | Notes |
|---|---:|---|---|
| `test_answer_key.py` | 18 | ✅ all pass | `load_correct_answers`, `validate_answer_key` (all 4 issue classes), `apply_answer_key_row_fix` |
| `test_decode_identifier.py` | 11 | ✅ all pass | Every branch of the 6/7/8-digit U-number recovery logic |
| `test_digit_marker_anchored.py` | 5 | ✅ all pass | `read_digit_marker_anchored()`: header-artifact-vs-real-mark, genuine ambiguity (v1.8) |
| `test_email_utils.py` | 30 | ✅ all pass | Template substitution (incl. `exam_type`), settings persistence, body-template `.txt` file storage/migration, keyring credential storage |
| `test_examples.py` | 9 | ✅ all pass | The shipped `examples/` files load correctly and stay mutually consistent |
| `test_grup_and_perm_normalization.py` | 23 | ✅ all pass | `decode_grup`, both `_normalize_*_value` helpers, `backfill_and_validate_groups` |
| `test_load_students.py` | 16 | ✅ all pass | All 4 student-list formats + encoding/blank-cell/duplicate edge cases |
| `test_main_window_gui.py` | 4 | ✅ all pass | `closeEvent` busy-state guard |
| `test_new_exam_screen_gui.py` | 7 | ✅ all pass | Run Analysis button's red/green colour state vs. which required fields (incl. Exam type, v1.7) are filled |
| `test_review_screen_gui.py` | 25 | ✅ all pass | Navigation confirmation, busy-lock, grid boundaries, zero-page guard, search/filter, manual email entry, `exam_type` persistence, preview-worker concurrency cap + no-infinite-retry (v1.8) |
| `test_scoring_and_excel.py` | 16 | ✅ all pass | `score_question` boundaries, `write_excel` with empty/missing/orphan inputs |
| `test_startup_splash_gui.py` | 5 | ✅ all pass | Startup splash construction, no-close-button guard, log text, `gui.app_info` import-weight check |
| `test_stability_malformed_input.py` | 21 | ✅ all pass | Corrupt PDF/Excel/CSV, pathological images, locked output file, config-dir fallback (v1.8) |
| `test_stability_threading.py` | 9 | ✅ all pass | Real `QThread` lifecycle, close/back guards during a real scan, locked-file-in-worker (v1.8) |
| `test_stability_thread_affinity.py` | 2 | ✅ all pass | Static guard against the v1.6 native-crash import mistake (v1.8) |
| `test_integration_real_data.py` | 6 | 3 pass, 3 skip | Real answer key; both real rosters and the real PDF currently sit under a renamed/moved path locally, so those 3 self-skip (not a regression — see note below) |
| `test_stability_e2e_subprocess.py` | 3 | ✅ all pass | Real subprocess run (New Exam→scan→Review→close), memory-growth regression (v1.8) |
| `test_stability_packaged_exe.py` | 5 | see below | Opt-in, needs `--packaged-exe`; skips (not counted above) in every normal run (v1.8) |
| **Total (normal runs)** | **214 collected** | **206 passed, 8 skipped** | 128.52s wall time (full), 17.34s (fast) |

No test failures. Skips break down as: 3 self-skips in `test_integration_real_data.py`
(the real PDF was relocated into `testing_dataset/` and one roster filename
changed since that file's skip conditions were written — gitignored, private,
user-managed data outside this project's control, not a regression) plus
5 in `test_stability_packaged_exe.py` (always skip without an explicit
`--packaged-exe` path — see below).

### Packaged-.exe smoke test (v1.8, opt-in)

`test_stability_packaged_exe.py` is deliberately **not** part of any
routine run — building a frozen executable takes several minutes and
doesn't belong in a fast feedback loop. It exists because packaging is
exactly where this project's only real crash (v1.6) actually happened:
source-level testing cannot catch a missing hidden import or a
bundled-resource path that resolves differently once frozen.

To run it: build `.exe` from `tests/_e2e_driver.py` (a PyInstaller spec
mirroring `"OMR Exam Corrector.spec"`'s `binaries`/`datas`/`hiddenimports`,
entry point swapped so the frozen binary is still scriptable through the
same New Exam→scan→Review→close flow), then:

```bash
pytest -m packaging tests/test_stability_packaged_exe.py \
    --packaged-exe "<path>\dist\e2e_driver\e2e_driver.exe"
```

**Investigation, 2026-07-18** (isolated sandbox venv + fresh PyInstaller
build, entirely outside the tracked project — see chat history for exact
steps). Initial runs across ~19 packaged-exe launches over roughly 45
minutes were noisy: one run hit a `STATUS_STACK_BUFFER_OVERRUN` (v1.6's
native-crash signature) during review-page navigation on a file that had
otherwise passed cleanly 4 separate times; other runs hit plain timeouts
on a shifting set of files. That first read pointed at accumulating
system load from repeated heavy launches, not a code defect — but it
turned out to be wrong, or at least incomplete: a **dedicated stress
test** (`tests/_e2e_driver.py`'s `stress`/`stress-forward-only` nav
modes, added specifically to probe this) that fires page-navigation calls
back-to-back with zero delay reproduced the exact same crash **reliably
and immediately**, both from source and in the packaged exe — no waiting
on accumulated system load required.

**Root cause, found by bisection on real data**: `ReviewScreen`
navigation (`_go_next`/`_go_prev`) is only gated by whether a *save* is
in progress, not by pending preview renders, so fast repeated navigation
could spawn many concurrent `_PreviewRenderWorker` threads — each
launching its own poppler subprocess against the same PDF file. Bisecting
the exact number of rapid, zero-delay navigations needed to trigger it
pinned the threshold precisely: **5 concurrent renders never crashed**
across repeated trials, **6+ crashed with real, non-deterministic
probability** — the signature of a genuine race condition, not a hard
resource limit or environmental noise.

**Fix**: `PREVIEW_WORKER_CAP = 2` in `gui/review_screen.py` caps
concurrent `_PreviewRenderWorker` instances; `_maybe_start_preview_worker()`
re-checks the current target reactively once a slot frees, instead of
firing a new worker on every navigation call. Building that fix surfaced
two more real bugs, both fixed alongside it: calling the reactive
recheck *before* the just-finished render's result was cached made it
spawn a spurious duplicate for the page that had just finished; and
calling it unconditionally (rather than only when the target had moved
on) meant a *failed* render — never cached, so never "resolved" — would
retry the identical failing page forever, an infinite loop confirmed to
hang the test suite outright once introduced.

**Verification**: 3/3 clean at the exact stress conditions that crashed
reliably before the fix, both from source and in a freshly-rebuilt
packaged exe; no crash dumps generated (Windows Error Reporting local
dumps were configured for this investigation); full test suite passes
(206 tests, +2 permanent regression tests for this specific bug:
`test_preview_worker_cap_never_exceeded_during_rapid_navigation`,
`test_failed_preview_render_does_not_retry_forever` in
`test_review_screen_gui.py`). The static guard against v1.6's *original*
root cause (`test_stability_thread_affinity.py`) was and remains clean
throughout — this was a genuinely different bug that happened to produce
the same OS-level crash signature.

---

## Recommendation before shipping

Run `pytest` (the full suite, including integration) once more immediately
before packaging the `.exe` or tagging the release, and treat any failure
as a release blocker. For day-to-day development, `pytest -m "not
integration"` (~19s) is fast enough to run on every change; save the full
pass (with real OCR) for pre-release and after any change touching
`process_page`, `detect_markers`, or the perspective-correction pipeline.
Before an actual release, also consider a `packaging`-marked pass (see
above) — it's the only technique that can catch a packaging-specific
regression at all.

This suite does not replace the manual verification workflow described in
`MANUAL.md`/`INSTALL.md`'s troubleshooting sections (visually checking the
annotated PDF, spot-checking a few grades by hand) — it catches
*regressions* in logic that's already been verified once, not
first-time correctness of a brand-new feature.
