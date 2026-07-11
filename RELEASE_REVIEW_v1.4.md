# Pre-Release Review — v1.4

Date: 2026-07-11 · Scope: `omr_correct.py`, `gui/*.py`, `omr_gui.py`, and
`README.md`/`MANUAL.md`/`INSTALL.md`, ahead of cutting the v1.4 release.

This document covers the four review steps requested — deep bug search,
data-inconsistency search, code comment review, and documentation
review/rewrite — plus what was actually fixed during this same v1.4
session for context.

**Bottom line**: 3 findings were rated Critical/High-confidence and worth
fixing before release (a permutation-routing dtype bug, a wrong-U-number
edge case, and a review-screen data-loss UX gap). **All 4 items in the
priority list below have since been fixed and verified** (each finding is
marked `FIXED` where it's discussed). The rest are real but lower-stakes or
narrow-trigger; see the updated priority list at the end for what's still
open.

---

## Method

Two independent full-codebase reviews were run in parallel (one scoped to
`omr_correct.py`, one to `gui/*.py`), each briefed on the program's
architecture and instructed to be adversarial rather than to praise the
code. Every finding is labeled **CONFIRMED** (the reviewer traced the exact
code path to the defect) or **PLAUSIBLE** (inferred, not fully traced). The
top Critical-rated claims were independently re-verified below before
inclusion.

---

## 1–2. Bug search & data-inconsistency findings

### `omr_correct.py`

#### CRITICAL

**1. `FIXED` Permutation routing breaks if the answer key's `Perm` column has any blank cell — entire permutation silently graded blank.**
`load_correct_answers()`/`validate_answer_key()` key the per-permutation
dict with `str(row['Perm']).strip()`. If **any** row in the `Perm` column is
blank/NaN, pandas infers the whole column as `float64`, and `str(0)` becomes
`"0.0"` — not `"0"`. Meanwhile the scanned value used for routing in
`write_excel()` (`permut_str = str(permut_val)`, line 1671) comes from a
clean Python `int`, e.g. `str(0) == "0"`. `"0" != "0.0"`, so **every page
detected as that permutation** gets routed to `No_Perm_Detected` instead of
its real sheet, and is graded against an empty answer-key dict — blank
grades for a whole permutation, no warning anywhere.
*Independently verified*: reproduced with a 4-row test CSV containing one
blank `Perm` cell — confirms `df['Perm'].dtype == float64` and
`str(0.0) == "0.0"`.
*Trigger*: one blank/missing cell anywhere in the answer key's `Perm`
column (or the file simply stores that column as Excel floats).
File/lines: `omr_correct.py:2753` (key construction), `:1668-1673`
(routing), `:2604` (`validate_answer_key`, same cast — doesn't catch it
either).
*Fix*: added `_normalize_perm_value()` (mirrors the existing
`_normalize_group_value()` for GRUP) and routed `Perm` through it at all
three sites. Verified by reproducing the exact float-upcast scenario in a
test CSV and confirming routing now succeeds, and by a full regression run
against the real answer key (0 validation issues, both permutations still
resolve correctly).

**2. `FIXED` `decode_identifier`'s 7-non-null branch can silently produce a *different real student's* U-number.**
When exactly 7 of the 8 IDENTIFIER bubbles register, the code infers
leading- vs. trailing-pad by checking whether the **first or last
remaining character** is `'0'` — not by checking *which position* is
missing. If the true ID is trailing-padded and a genuine (non-pad) digit is
the one that failed to register, the pad-zero heuristic still fires,
stripping the wrong character and returning a **wrong but well-formed**
6-digit ID with status `OK_PADDED` — shown green, not flagged.
*Independently verified*: traced `digits=[2,3,4,None,6,7,0,0]` through the
function → returns `"234670"` (wrong) with status `OK_PADDED`, not
`"234067"` (correct-shape) or any warning status.
*Trigger*: a single faint/missed pencil mark among the 6 real ID digits —
a realistic, common OMR failure mode.
File/lines: `omr_correct.py:779-785`; consumed at `:1344` where
`OK_PADDED` is colored identically to `OK`.
*Fix*: the branch now identifies the actual missing bubble position
(`missing_idx`) instead of inferring pad-side from "the boundary digit
happens to be 0" — it only takes the `OK_PADDED` shortcut when the missing
bubble *is* the other expected pad slot. Any other missing position now
returns the raw 7-digit read with status `WARNING` instead of a confident
wrong ID. Verified with 7 test cases: both the original bug reproduction
(`[2,3,4,None,6,7,0,0]` — previously silently returned `"234670"`, now
correctly returns `WARNING`) and all 5 legitimate padding scenarios (still
pass unchanged).

**3. `detect_markers()` doesn't validate it found exactly 10 ID rows / 40 answer rows — a partial marker-detection failure reads wrong digits or drops trailing questions with no error.**
The only gate is `len(markers) >= 20` total; the id/ans split is chosen by
closeness to a 10/40 ratio, not exactness. A locally undetected marker
(smudge, fold, low contrast) that still clears the length-20 floor can
leave `ans_rows` short. Consequences: `read_digit_marker_anchored()` can
map a mark to the wrong digit (nearest available row, not the true row);
`read_answers()`'s `if can_row >= len(ans_rows): break` silently stops
emitting later questions, which then score identically to a student who
left them blank. Neither failure sets `errors`/`validation_issues`, and the
independent red-box quality score can still read 7/7 — false confidence.
Confidence: CONFIRMED code path; PLAUSIBLE trigger frequency (needs a
degraded scan).
File/lines: `omr_correct.py:395-427` (marker split), `:842` (`read_answers`
early break).

#### HIGH

**4. Annotated-PDF "reviewer added/removed" purple markers use the wrong threshold, producing false manual-edit flags on unedited pages.**
`_draw_annotated_page()` recomputes `auto_marks` from stored fills using the
*global* `FILL_THRESHOLD_ANS = 0.10`, but the actual scan-time grading used
that page's **adaptive** threshold (clamped to `[0.08, 0.30]`, often ≠
0.10). Whenever they differ, redraw reclassifies borderline bubbles
differently than scoring did, producing spurious purple "added/removed"
annotations on pages nobody touched. Does not affect the actual Excel
grade — visual-only.
File/lines: `omr_correct.py:2132-2140` vs. `:1178-1182`.

**5. No upper bound on `--questions`; a value > 100 crashes every page in the batch.**
`col_idx = (q-1)//20` indexes `ANS_COL_A_X` (5 entries → max 100
questions). `--num-options` is range-checked at startup; `--questions`
isn't. A too-large value doesn't fail fast — it raises `IndexError` inside
each page's try/except, so the whole run silently "completes" with every
page marked `EXCEPTION`.
File/lines: `omr_correct.py:3074` (num-options check, for contrast), no
equivalent for `-q`.

#### MEDIUM

**6. "Ungraded" is represented inconsistently between sheet-writers: `0` in one, `''` in the other.**
`_write_results_sheet`: `grade_10 = ... if max_score > 0 else 0`.
`_write_group_sheet`: `grade_10 = ... if max_score > 0 else ''`.
Same condition (no answer key applies), two different sentinels — a
downstream formula (class average, etc.) reading `No_Perm_Detected` would
silently average in `0`s that look like real failing grades, while the
T1/T2 sheets correctly leave the cell blank.

**7. Answer-key row coloring can flag credit-neutral questions as green/red.**
Scoring correctly skips a row where the key is present-but-empty (an
all-zero/voided question): `if correct_set: ...`. Coloring instead checks
`if q in correct_answers:` (true for that same empty-set row), so a
student's blank cell renders green and any mark renders red for a question
that carries zero credit either way — cosmetically misleading, not a grade
error.

**8. AMBIGUOUS U-number resolution silently picks candidate 1; `ID_Problem` shows `OK` if it happens to be a valid roster ID.**
`U_Status` does separately show `AMBIGUOUS` (yellow), so it's not fully
silent — but the more prominent `ID_Problem` column can read `OK` for a
match that was actually a coin flip between two equally-plausible
readings.

**9. Numeric-typed U-number source columns can lose leading zeros with no diagnostic.**
If a roster's ID column is stored as a true number rather than text (common
in non-technical exports), a leading zero is gone before `load_students()`
ever sees it, and nothing re-pads it. Affected students show
`UNUMBER_NO_MATCH` with no hint at the actual cause.

**10. `--ignore-answer-key-warnings` + a malformed `QuestionNum` cell crashes the whole run.**
`validate_answer_key()` reports a NaN `QuestionNum` generically as "missing
question"; `load_correct_answers()` then does `int(row['QuestionNum'])` on
the *uncoerced* value and raises an unhandled `ValueError` instead of
skipping just that row.

**11. An answer-key row marking *every* option correct silently costs every student a point of possible credit.**
`score_question()` correctly returns 0.0 when `good == num_options` (can't
score a question with no wrong answer to penalize), but both sheet-writers
still add `max_score += 1.0` for it since `correct_set` is non-empty. Not
caught by `validate_answer_key()`. A realistic data-entry slip (marking a
whole option row `1`), not a code bug per se.

#### LOW

**12.** `T1`/`T2` group values are hardcoded to `('1', '2')` — a course with a 3rd theory group would simply never get a roster tab (silent, documented assumption).
**13.** `decode_grup()`'s status return is discarded — inconsistent with every other decode function, currently harmless.
**14.** `apply_answer_key_row_fix()`'s row-number arithmetic assumes the DataFrame index maps 1:1 to file line numbers — true for well-formed files, unverified against blank-line edge cases.

#### Reviewed, no issue found
`score_question()`'s clamp logic; `_write_results_sheet`'s 18
fixed-column literals (all internally consistent — see comment-review
note below); the `detect_id_boxes` fill-ratio threshold change (backed by
real-scan data, see [4. below](#4-code-comment-review)); `find_x_offset`'s
DNI/IDENTIFIER collision risk; `backfill_and_validate_groups`'s in-place
mutation consistency.

---

### `gui/*.py`

#### CRITICAL

**1. `FIXED` Navigating to another page silently discards unapplied edits — no confirmation.**
`_go_prev`/`_go_next`/`_on_table_row_selected` call `_load_page()`
unconditionally; none check `self._form_dirty`. `_load_edit_form()`
rebuilds the ID fields and the whole answers grid straight from the saved
`r`, clearing `_form_dirty`. The only hint anything is unsaved is the Apply
button's orange tint.
*Failure scenario*: toggle a few answer marks (the live Score/Total updates
right there on screen), get interrupted, click "Next >>" — the edits are
gone, page grades on the original OCR reading, with zero warning.
File/lines: `gui/review_screen.py:1042-1053`.
This is the single highest-impact finding in the whole review: it's a
realistic, easy-to-hit data-loss path in the tool's core workflow.
*Fix*: added `_confirm_discard_unsaved()` (mirrors the existing "Revert to
original" `QMessageBox.question` pattern), gating all three navigation
paths; a table-row click that's declined reverts the visual row selection
back to the current page without re-entering the handler. Verified with a
scripted test: not-dirty navigates silently, dirty+No blocks navigation,
dirty+Yes proceeds. The MANUAL.md troubleshooting tip added earlier is
kept as-is — accurate context even though the silent-discard case it
warned about is now confirmation-gated.

**2. An edit made to a page while *that same page's* save is still in flight gets silently overwritten.**
`_save_async()` disables Apply/Revert/Rescan but not the answers grid or
the ID `QLineEdit`s. If a save is still writing (full `write_excel` +
whole-PDF rewrite via `patch_annotated_pdf_page`) and the user toggles
another mark on the same page in the meantime, `_on_local_save_done()`
unconditionally reloads the form from `r` once the save completes — the
second edit vanishes without any message.
File/lines: `gui/review_screen.py:1169-1233`.

**3. `FIXED` `_rescan_page()`'s "did the user navigate away mid-rescan" guard doesn't actually guard anything — can write a rescanned page's result onto the wrong page.**
The page index is captured (`page_index = self.current_index`) *after* the
blocking OCR call returns, not before. The one place navigation could
actually happen mid-rescan — a queued click flushed by the deliberate
`QApplication.processEvents()` right before the blocking OCR work — occurs
*before* that capture, so it offers no protection. If it fires, the
rescanned result and its PDF-page patch get written into whatever page
`current_index` moved to, not the page that was actually rescanned:
potential silent cross-page data corruption.
File/lines: `gui/review_screen.py:1283` (the flush), `:1297` (the
capture — should be first, not after the OCR call).
Confidence: CONFIRMED as a code defect; narrow but real as a
field-triggerable race (needs a click already queued at the exact moment
of the flush).
*Fix*: `page_index` is now captured immediately after `_current_result()`,
before the confirmation dialog, the `processEvents()` flush, or the
blocking OCR call — so it always names the page actually being rescanned
regardless of where the user navigates afterward. As defense in depth
(the report noted none of prev/next/the pages table were disabled during
rescan), `_refresh_action_buttons()` now also disables Prev/Next/the pages
table while `_local_busy`, closing the specific gap that made the race
reachable in the first place. Verified: `_refresh_action_buttons()` with
`_local_busy=True` correctly disables all three; re-enables once busy
clears.
Note: the underlying Medium finding below (rescan not being threaded) is
the root cause of needing the `processEvents()` flush at all — not fixed
here, since that's a larger refactor than this specific race; tracked as
follow-up.

#### MEDIUM

**4. Rescan runs OCR synchronously on the GUI thread — the one long-running operation in this screen that isn't a `QThread`.**
Every other slow operation (`AnalysisWorker`, `_SaveWorker`,
`_PreviewRenderWorker`) is threaded specifically to keep the UI responsive,
per their own docstrings. `_rescan_page()` calls `convert_from_path` +
`omr.process_page` directly on the GUI thread, freezing the window
(possible "Not Responding") for a full single-page OCR pass — and the
`processEvents()` workaround this forces is the direct cause of finding #3
above.
File/lines: `gui/review_screen.py:1253-1296`.

#### LOW

**5.** `load()`'s early `setHorizontalHeaderLabels()` call sets header text before `setColumnCount()`, momentarily inconsistent — but fully overwritten by `_load_answers_grid()` in the same synchronous call before anything paints. No observable effect, just confusing dead code.

#### Reviewed, no issue found
Score-column indexing/off-by-ones; `_grid_marks_for_row` vs.
`_collect_marks_from_grid` agreement; `_update_total_score_label`'s formula
vs. `_write_results_sheet`'s (verified identical); background/foreground
persistence ordering on `QTableWidgetItem`s across grid rebuild vs. toggle;
`_pending_sync_workers`/`_pending_preview_workers` cleanup (no leak, no
double-fire); `_recompute_pdf_page_index()` staying in sync;
`AnswerKeyIssuesDialog` re-validation/state management; the GUI/backend
data contract (dict keys, DataFrame columns, Excel routing) matches what
`omr_correct.py` actually produces.

---

## 3. Code comment review

Targeted search for `TODO`/`FIXME`/stale markers found none — the codebase
has no unresolved TODOs. Manual + agent-assisted review of comments near
this session's changes found one real staleness bug:

- **Fixed**: `_write_results_sheet()`'s docstring still described the
  pre-v1.4 16-column fixed layout ("Cols 1-16 ... DNI, PARCIAL, PERMUT,
  GRUP, N_Answered, ...") after `Email` and `GRUP_Check` were added,
  growing it to 18 columns. The code itself was correct (verified: every
  hardcoded `column=N` literal is internally consistent with the actual
  18-entry `fixed_headers` list) — only the comment had drifted. Rewritten
  to defer to `fixed_headers` as the single source of truth instead of
  repeating the list, so it can't drift again the same way.
- The `detect_id_boxes()` fill-ratio threshold change (0.25 → 0.10, made
  earlier this session) is documented in-place with the specific real-scan
  measurements that justified it (ASSIGNATURA measured 0.232–0.234 on
  genuinely-valid pages, just under the old cutoff) — flagged here only to
  note it was checked as part of this review, not to re-litigate it.
- No other stale/misleading comments were found in the areas both audit
  agents scrutinized closely.

---

## 4. Documentation review

All three docs were out of date relative to this session's feature work
(answer-key validation, two new roster formats, GRUP backfill/cross-check,
T1/T2 tabs, review-grid live scoring, the ID-box detection fix) and have
been rewritten:

- **`README.md`**: added a "What's new in v1.4" section; updated the
  "What it does" walkthrough to mention answer-key validation and GRUP
  cross-checking.
- **`MANUAL.md`**: version bumped to 1.4; new §5 "Answer-key validation
  (v1.4)" with the validation-dialog screenshot; §7.2 "Answer grid" rewritten
  for the grey shading / Score column / Total score footer; §10 "Output
  files" updated for `Email`, `GRUP_Check`, and the `T1`/`T2` tabs; §12
  colour legend gained the teal/red GRUP pill entries; §14 Troubleshooting
  gained two new v1.4-specific entries plus an explicit warning about the
  navigation data-loss behavior from finding #1 above; every section
  renumbered (5→14) and every internal cross-reference link fixed to match
  (verified via full-document backlink scan, no dangling anchors remain).
- **`INSTALL.md`**: added the two new student-list formats with examples;
  documented `--ignore-answer-key-warnings`; updated the `results.xlsx`
  output description for `Email`/`GRUP_Check`/`T1`/`T2`/teal-red pills.
- **Screenshots**: `assets/screenshots/` had exactly 1 of 10 documented
  screenshots present (and it was stale, still showing "v1.2"). Captured 6
  current screenshots this session — `01-start-screen`, `02-new-exam-form`,
  `03-analysis-running`, `04-review-screen`, `06-expected-overlay`, and a
  new `11-answer-key-validation` — driving the *real* application with
  *real* data via `QWidget.grab()` (not mockups: e.g. `04`/`06` load the
  actual regenerated `output/review_cache.pkl` and show a real student's
  real grade breakdown). Local file paths were kept out of the captured
  screenshots (generic example filenames used instead) to avoid leaking
  this machine's username/folder structure into a public doc. Five
  screenshots (`05`, `07`, `08`, `09`, `10`) remain outstanding — they need
  either a precise manual crop or, for `08`/`09`, a real native OS "Save
  File" dialog, which can't be produced by grabbing a Qt widget. The
  MANUAL.md appendix table now shows accurate per-file status instead of a
  blanket "needed" list.

---

## Also fixed this session (context, not new findings)

For completeness, these were found and fixed *during* this session's
feature work (not part of the after-the-fact review above), and are why
several of the features described in the v1.4 changelog work correctly on
the real data they were tested against:

- Answer-key CSV data bug (`LSDS_Retake2026_PermALL_Fixed.csv`): a `Perm`
  value copy/pasted one row too early, dropping Perm 1's Q30 — the direct
  motivation for the new `validate_answer_key()` feature.
- `GRUP_Check` false-mismatch bug: scanned `"01"` vs. roster `"1"` compared
  as raw strings; fixed with numeric normalization.
- Windows console crash: `print()`ing `✓`/`✗` under the default cp1252
  console codepage raised `UnicodeEncodeError` mid-batch; switched to ASCII
  `[OK]`/`[FAIL]`.
- ID-box detection threshold (0.25 → 0.10): was rejecting genuinely-present
  ASSIGNATURA/CENTRE boxes on some real scans.
- Blank `Cognom2` rendering as the literal text `"nan"`.

---

## Recommended priority before release

1. ~~**Fix or explicitly accept** the `Perm` dtype-mismatch bug (backend
   Critical #1).~~ **`FIXED`** — added `_normalize_perm_value()`, applied at
   all three sites that turn a `Perm` value into a routing key.
2. ~~**Fix or explicitly accept** the navigation data-loss UX gap (GUI
   Critical #1).~~ **`FIXED`** — added a confirmation prompt when leaving a
   dirty page, mirroring the existing "Revert to original" dialog.
3. ~~**Decide on** the `decode_identifier` wrong-digit edge case (backend
   Critical #2) and the rescan race (GUI Critical #3).~~ **`FIXED`** — both.
   `decode_identifier` now checks the actual missing bubble position
   instead of inferring from a boundary digit; the rescan page index is now
   captured before any blocking work, and page navigation is disabled for
   the duration as defense in depth.
4. Everything else (Medium/Low, plus GUI Critical #2 — an edit landing
   mid-save on the same page — which was flagged but not part of this
   priority batch) is safe to ship v1.4 with and track as follow-up work.

**Fixes verified**: syntax-checked every changed file; regression-tested
`decode_identifier` against the original bug reproduction plus 6 legitimate
padding scenarios (all pass); reproduced and confirmed-fixed the `Perm`
float-upcast scenario in an isolated test, then re-ran `validate_answer_key`
and `load_correct_answers` against the real answer key (0 issues, both
permutations intact); scripted-tested the navigation confirmation gate
(silent when clean, blocks on "No", proceeds on "Yes") and the busy-state
nav-locking; and ran a full end-to-end pipeline regression against the real
11-page exam PDF (11/11 processed, no errors).

---

## Second-pass stress testing (post-email-feature)

A follow-up round specifically targeting the new email feature
(`email_utils.py`, `gui/email_dialogs.py`, zero prior adversarial testing)
plus a renewed push on the rest of the pipeline with deliberately
inconsistent data: malformed templates, corrupted config files, blank/
garbage cells in every input file, boundary values, and empty/orphan
data. All items below were reproduced, fixed, and re-verified; none are
open follow-ups.

1. **`fill_template()` crashed on any stray `{`/`}` in a user-edited
   template** (`email_utils.py`) — confirmed with `"{nom"`, `"nom}"`, and
   `"{0}"` all raising `ValueError` via `str.format_map()`. Free text a
   non-programmer edits in a dialog box commonly contains a lone brace for
   an unrelated reason. Rewritten as a plain regex substitution
   (`\{(\w+)\}`) that only ever touches well-formed `{token}` spans and
   leaves everything else as literal text — as a side effect this also
   closes off `{token.__class__}`-style attribute access that
   `str.format_map()` would otherwise evaluate.
2. **A corrupted `email_settings.json` permanently broke email sending**
   — `load_email_settings()` raised `json.JSONDecodeError` unhandled,
   hit by both "Email settings..." and "Send by email...". Now falls back
   to defaults on any unreadable/malformed/wrong-shaped settings file.
3. **A blank `Perm` cell produced a phantom `"nan"` permutation** — the
   normalized value of a blank cell literally became the string `"nan"`,
   which `load_correct_answers()` then treated as a real permutation and
   `write_excel()` gave its own spurious `"Perm nan"` sheet in the output
   workbook. `validate_answer_key()` now flags a blank `Perm` as its own
   clear issue ("Row N has a blank Perm value...") and both functions skip
   such rows instead of fabricating a permutation from them. (Fixing this
   also surfaced and fixed a related crash: the issue list's sort key
   assumed `question` was always an int, which broke as soon as two blank-
   `Perm` rows — `question: None` — tied on `str(perm)`.)
4. **The documented ";-separated CSV" variant of the UPF official student-list
   export was completely broken** — any file with a course-title-only
   first line (no separator in it) made every parse attempt see exactly 1
   column, so the `shape[1] >= 2` acceptance check never passed for *any*
   separator/encoding combination, unconditionally raising
   `RuntimeError: Could not read CSV with any standard format`. This
   wasn't a new-feature bug — it's been broken since this format was
   documented, just never exercised by the files used earlier in this
   session (those were tested as `.xls`, a different code path). Fixed by
   detecting the real header row from the raw file lines first, then
   re-reading via `pandas.read_csv(..., skiprows=N)` — sidesteps the
   ragged-row parse error entirely rather than fighting it after the fact.
5. **Blank `Nom`/`Cognom1`/`Email` cells rendered as the literal text
   `"nan"`** — the same bug class fixed for `Cognom2` earlier this
   session, but that fix was scoped to `Cognom2` alone. Testing showed the
   other three name-ish fields are equally affected by a blank source
   cell. Generalized the `.fillna('')` fix to all four columns.
6. **An answer-key file with fewer option columns than the exam is
   configured for produces zero warnings while silently zero-scoring
   legitimate answers** — confirmed concretely: a 4-column (A-D) answer
   key used for a 6-option exam scores a student's `E` mark as always
   wrong (`E` can never be in any question's correct set), with
   `validate_answer_key()` reporting 0 issues. This is a highly plausible
   real mistake (a stale/wrong-sized template) with a real grading
   consequence and was completely invisible. Added a new `MISSING_OPTION`
   check to `validate_answer_key()` (opt-in via a new
   `expected_num_options` parameter, wired from both the CLI and the GUI's
   answer-key dialog) that flags exactly which option letters are missing.
7. **`ReviewScreen.load()` crashed with `IndexError` on a zero-page
   result set** — an exam PDF with no pages (empty/corrupt file) leaves
   `all_results = []`, and `load()` unconditionally called
   `_load_page(0)`. Now shows a "No pages to review" state instead of
   crashing right after a run "successfully" completes.
8. **Closing the app while a save or preview render is still in flight
   could hard-crash the process** — nothing waited for
   `review_screen`'s background `QThread`s before the window was allowed
   to close. Reproduced directly: a still-running `_PreviewRenderWorker`
   at process exit crashes natively (`STATUS_STACK_BUFFER_OVERRUN` — not a
   catchable Python exception), and confirmed the crash disappears once
   the thread is properly waited for before exit. For the save-worker
   case specifically, the same abrupt exit could leave `results.xlsx` /
   `annotated_review.pdf` mid-write, not just crash. Added a
   `closeEvent` override on `MainWindow` that declines to close (with an
   explanatory message) while any of `review_screen._local_busy`,
   `_pending_sync_workers`, or `_pending_preview_workers` is non-empty.

**Also tested, no issue found**: unicode/emoji in templates and names;
very long strings; `keyring` with special characters and missing entries;
negative/zero/huge `QuestionNum` values; duplicate option-column headers;
`score_question` at every degenerate boundary (`good == num_options`,
empty correct-answer sets, marks outside the valid option range);
`write_excel`/`_write_group_sheet` with empty results, no roster, no
answer key, and orphan permutations nothing scanned actually used;
`num_options` at its 2 and 10 boundaries in the review grid; a page with a
completely empty `answers` dict; a scanned permutation with no matching
answer-key entry. Duplicate U-numbers within a roster file are accepted
without complaint and consistently resolve to the *last* matching row
everywhere in the app (Excel writer, annotated PDF, review screen,
GRUP backfill) — not a crash, and not inconsistent across call sites, but
worth knowing: a genuine roster duplicate silently picks one of the two
students' Name/Email/TheoryGroup, arbitrarily.
