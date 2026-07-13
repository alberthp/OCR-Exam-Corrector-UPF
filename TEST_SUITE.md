# Pre-Production Test Suite

Date: 2026-07-11 · Framework: [pytest](https://docs.pytest.org/) 9.1.1 ·
Location: [`tests/`](tests/) · Config: [`pytest.ini`](pytest.ini)

This project had **zero automated tests** before this suite — every bug
found and fixed in the two prior review passes ([`RELEASE_REVIEW_v1.4.md`](RELEASE_REVIEW_v1.4.md))
was caught by disposable, ad-hoc scripts that were written once, verified,
and deleted. This suite turns that one-off verification into a permanent
regression net: **166 tests**, **100% passing** (of the ones that run —
see the integration-skip note in Results below), run in **~66 seconds**
(~14 seconds without the real-data integration pass).

## How to run it

```bash
pip install -r requirements-dev.txt

pytest                        # everything (~61s, needs the real exam files)
pytest -m "not integration"   # fast unit/GUI suite only (~14s, no real data needed)
pytest -m integration         # just the real-data pass
pytest -m "not slow"          # everything except the full OCR pipeline test
```

The integration tests in `test_integration_real_data.py` use the real exam
PDF and roster/answer-key files that normally sit in the project root —
these are gitignored (private student data) and each integration test
**skips itself automatically** if its file isn't present, so the suite is
safe to run (with reduced coverage) on a fresh checkout that doesn't have
them.

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
| GUI state | `test_review_screen_gui.py`, `test_main_window_gui.py`, `test_new_exam_screen_gui.py`, `test_startup_splash_gui.py` | 37 | Offscreen Qt platform | No |
| Shipped examples | `test_examples.py` | 9 | No | No (synthetic `examples/` files) |
| End-to-end | `test_integration_real_data.py` | 6 | No | Yes (skips if absent) |

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
165 passed, 1 skipped in 66.03s
```

| Test file | Tests | Result | Notes |
|---|---:|---|---|
| `test_answer_key.py` | 18 | ✅ all pass | `load_correct_answers`, `validate_answer_key` (all 4 issue classes), `apply_answer_key_row_fix` |
| `test_decode_identifier.py` | 11 | ✅ all pass | Every branch of the 6/7/8-digit U-number recovery logic |
| `test_email_utils.py` | 30 | ✅ all pass | Template substitution (incl. `exam_type`), settings persistence, body-template `.txt` file storage/migration, keyring credential storage |
| `test_examples.py` | 9 | ✅ all pass | The shipped `examples/` files load correctly and stay mutually consistent |
| `test_grup_and_perm_normalization.py` | 23 | ✅ all pass | `decode_grup`, both `_normalize_*_value` helpers, `backfill_and_validate_groups` |
| `test_load_students.py` | 16 | ✅ all pass | All 4 student-list formats + encoding/blank-cell/duplicate edge cases |
| `test_main_window_gui.py` | 4 | ✅ all pass | `closeEvent` busy-state guard |
| `test_new_exam_screen_gui.py` | 5 | ✅ all pass | Run Analysis button's red/green colour state vs. which required fields are filled |
| `test_review_screen_gui.py` | 23 | ✅ all pass | Navigation confirmation, busy-lock, grid boundaries, zero-page guard, search/filter, manual email entry, `exam_type` persistence |
| `test_scoring_and_excel.py` | 16 | ✅ all pass | `score_question` boundaries, `write_excel` with empty/missing/orphan inputs |
| `test_startup_splash_gui.py` | 5 | ✅ all pass | Startup splash construction, no-close-button guard, log text, `gui.app_info` import-weight check |
| `test_integration_real_data.py` | 6 | 5 pass, 1 skip | Real answer key, both real rosters (one currently renamed locally, see below), real PDF DPI detection, full OCR pipeline (11/11 pages, 45.9s) |
| **Total** | **166** | **✅ 165/166** (1 self-skip) | 66.03s wall time |

One test failure surfaced during development — `test_full_fix_workflow_resolves_all_issues`
initially used a synthetic answer-key fixture that didn't fully mirror the
real bug it was modeling (the real file had the misplaced row *and* the
permutation's own genuine entry elsewhere; the first draft of the fixture
only had the misplaced one). This was a flawed test, not an app bug: after
correcting the fixture to include both rows — matching the real file's
structure — the suite (and the underlying `validate_answer_key`/
`apply_answer_key_row_fix` code) passed correctly. No application code
changed as a result.

No other failures occurred. One test self-skipped as designed: the local
`llistatGGiA (8).xls` roster the integration suite looks for has since
been renamed on disk (to `llistatGGiALSDS.xls`, outside this project's
control — it's gitignored, private, user-managed data) — the test skips
itself cleanly rather than failing, exactly as it's meant to when a real
data file isn't present under the expected name. Not a regression; every
other real data file was present and every non-integration test passed.

---

## Recommendation before shipping

Run `pytest` (the full suite, including integration) once more immediately
before packaging the `.exe` or tagging the release, and treat any failure
as a release blocker. For day-to-day development, `pytest -m "not
integration"` (~14s) is fast enough to run on every change; save the full
pass (with real OCR) for pre-release and after any change touching
`process_page`, `detect_markers`, or the perspective-correction pipeline.

This suite does not replace the manual verification workflow described in
`MANUAL.md`/`INSTALL.md`'s troubleshooting sections (visually checking the
annotated PDF, spot-checking a few grades by hand) — it catches
*regressions* in logic that's already been verified once, not
first-time correctness of a brand-new feature.
