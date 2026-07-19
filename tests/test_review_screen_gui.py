"""Headless tests for gui/review_screen.py's non-visual logic: navigation
guards, busy-state locking, grid rendering at option-count boundaries, and
score computation -- run with QT_QPA_PLATFORM=offscreen (set by the qapp
fixture), asserting on widget state/text, not rendered pixels.

Includes permanent regression tests for three bugs found during the v1.4
stress-testing passes: a zero-page result set crashed load(), navigating
away silently discarded unapplied edits, and closing the app while a
background QThread was still running could hard-crash the process.
"""

import os

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QMessageBox

import omr_correct as omr

pytestmark = pytest.mark.gui


@pytest.fixture
def review_screen(qapp):
    from gui.review_screen import ReviewScreen
    screen = ReviewScreen()
    yield screen
    settle(screen)


def settle(screen):
    """Wait for any background QThread a load()/save call started and pump
    the event loop so its queued signal is delivered. Without this, a
    still-running worker at process/object teardown crashes natively
    (confirmed by testing) -- see the closeEvent fix in
    gui/main_window.py for the equivalent real-app protection.

    Loops until both worker lists are genuinely empty rather than a single
    snapshot-then-wait pass: ReviewScreen.PREVIEW_WORKER_CAP means a
    _PreviewRenderWorker can be started *reactively*, from inside another
    worker's done-signal handler, while this function's own
    app.processEvents() calls are what deliver that first signal -- a
    fixed-count pass can finish while that second, reactively-started
    worker is still running, and a still-running QThread at test teardown
    (when `screen` itself gets garbage-collected) is exactly the native
    "destroyed while running" crash this function exists to prevent.
    Confirmed by testing: a fixed 20-iteration pass let this happen.
    """
    import PySide6.QtWidgets as qw
    app = qw.QApplication.instance()
    for _ in range(200):
        pending = (list(getattr(screen, "_pending_preview_workers", []))
                   + list(getattr(screen, "_pending_sync_workers", [])))
        if not pending:
            break
        for worker in pending:
            worker.wait(5000)
        app.processEvents()
    else:
        raise AssertionError("settle(): workers still pending after 200 iterations")
    for _ in range(20):
        app.processEvents()


@pytest.fixture
def backing_files(tmp_path):
    """_setup_local_scratch() copies these two paths -- they don't need to
    be valid PDF/xlsx content (a failed render is handled gracefully and
    doesn't crash), just present."""
    pdf_path = tmp_path / "annotated_review.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 not a real pdf, just needs to exist\n")
    xlsx_path = tmp_path / "results.xlsx"
    xlsx_path.write_bytes(b"not a real xlsx, just needs to exist")
    return str(pdf_path), str(xlsx_path)


def make_run_state(all_results, backing_files, students_df=None,
                    correct_answers_by_perm=None, num_questions=3, num_options=4):
    pdf_path, xlsx_path = backing_files
    return {
        "all_results": all_results,
        "students_df": students_df if students_df is not None else pd.DataFrame(
            columns=["Nom", "Cognom1", "Cognom2", "U_number"]),
        "correct_answers_by_perm": correct_answers_by_perm or {},
        "num_questions": num_questions,
        "num_options": num_options,
        "excel_path": xlsx_path,
        "pdf_path": pdf_path,
        "cache_path": None,
        "exam_pdf": None,
        "dpi": 300,
    }


# ----- Zero-page guard (regression) -----

def test_load_with_zero_pages_does_not_crash(review_screen, backing_files):
    rs = make_run_state([], backing_files)
    review_screen.load(rs)  # must not raise IndexError
    settle(review_screen)
    assert review_screen.page_label.text() == "Page 0 / 0"
    assert not review_screen.prev_btn.isEnabled()
    assert not review_screen.next_btn.isEnabled()


# ----- Preview-worker concurrency cap (regression) -----
#
# Found via a real native STATUS_STACK_BUFFER_OVERRUN crash reproduced by
# rapid, zero-delay page navigation through a packaged .exe: navigation is
# only gated by _local_busy (which guards saves), not by pending preview
# renders, so fast repeated navigation could spawn many concurrent
# _PreviewRenderWorker threads -- each launching its own poppler subprocess
# against the same PDF file. Bisected on real data: 5 concurrent renders
# never crashed across repeated trials, 6+ crashed with meaningful,
# non-deterministic probability (the signature of a genuine race, not a
# hard resource limit). Fixed by capping concurrent workers
# (PREVIEW_WORKER_CAP) and re-checking the current target reactively once
# a slot frees, rather than firing a new worker on every navigation call.

def test_preview_worker_cap_never_exceeded_during_rapid_navigation(review_screen, backing_files):
    results = []
    for i in range(10):
        results.append({
            "page": i + 1, "status": "OK",
            "_corrected": np.zeros((10, 10, 3), dtype="uint8"),
            "u_number": f"{i:06d}", "u_status": "OK", "dni": "1" * 8,
            "parcial": "1", "permut": "1", "grup": "1", "answers": {},
        })
    rs = make_run_state(results, backing_files, num_questions=1, num_options=4)
    review_screen.load(rs)

    # Rapidly request every page without waiting for any render to finish
    # (mirrors the zero-delay navigation that reproduced the real crash).
    for i in range(len(results)):
        review_screen._load_page(i)
        assert len(review_screen._pending_preview_workers) <= review_screen.PREVIEW_WORKER_CAP, (
            f"exceeded PREVIEW_WORKER_CAP after navigating to page {i}: "
            f"{len(review_screen._pending_preview_workers)} workers in flight"
        )
    settle(review_screen)


def test_failed_preview_render_does_not_retry_forever(review_screen, backing_files):
    """backing_files' PDF is deliberately not real PDF content, so every
    render attempt fails -- regression test for a bug introduced (and
    fixed) alongside the concurrency cap above: reactively starting the
    next worker unconditionally on every completion, including a failed
    one, re-requested the *same* still-failing page forever, since a
    failed render is never cached and so never looks "already resolved".
    Confirmed by testing to hang indefinitely before the fix; settle()
    itself would now raise AssertionError rather than hang if this
    regressed, but this test names the property directly.
    """
    result = {
        "page": 1, "status": "OK",
        "_corrected": np.zeros((10, 10, 3), dtype="uint8"),
        "u_number": "000001", "u_status": "OK", "dni": "1" * 8,
        "parcial": "1", "permut": "1", "grup": "1", "answers": {},
    }
    rs = make_run_state([result], backing_files, num_questions=1, num_options=4)
    review_screen.load(rs)
    settle(review_screen)  # would hang/raise here if the retry-loop regressed
    assert review_screen.preview_label.text().startswith("Could not render preview")


# ----- num_options boundaries in the answers grid -----

@pytest.mark.parametrize("num_options", [2, 10])
def test_grid_column_count_at_option_boundaries(review_screen, backing_files, sample_result, num_options):
    opt = omr.OPTION_LABELS[:num_options][-1]  # last valid option letter
    sample_result["answers"] = {1: {"marks": {opt}}}
    rs = make_run_state([sample_result], backing_files,
                         correct_answers_by_perm={"1": {1: {opt}}},
                         num_questions=1, num_options=num_options)
    review_screen.load(rs)
    settle(review_screen)
    assert review_screen.answers_table.columnCount() == num_options + 1  # + Score
    score_item = review_screen.answers_table.item(0, num_options)
    assert score_item.text() == "1.00"


# ----- Empty / orphan data -----

def test_page_with_empty_answers_dict(review_screen, backing_files, sample_result):
    sample_result["answers"] = {}
    rs = make_run_state([sample_result], backing_files,
                         correct_answers_by_perm={"1": {1: {"A"}}},
                         num_questions=3, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    assert "0.00" in review_screen.total_score_label.text()


def test_page_permutation_with_no_matching_answer_key(review_screen, backing_files, sample_result):
    sample_result["permut"] = "99"
    rs = make_run_state([sample_result], backing_files,
                         correct_answers_by_perm={"1": {1: {"A"}}},
                         num_questions=1, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    assert "no answer key" in review_screen.total_score_label.text()


# ----- Duplicate U-number resolution (documents current behavior) -----

def test_duplicate_u_number_resolves_to_last_roster_row(review_screen, backing_files, sample_result):
    students_df = pd.DataFrame({
        "Nom": ["Alice", "Zoe"], "Cognom1": ["A", "Z"], "Cognom2": ["", ""],
        "U_number": ["U000001", "U000001"],
    })
    rs = make_run_state([sample_result], backing_files, students_df=students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}},
                         num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    matched = review_screen.student_lookup.get("000001")
    assert matched["Nom"] == "Zoe"  # last row in the roster wins


# ----- Navigation confirmation gate (regression) -----

def test_navigating_away_with_no_unsaved_changes_proceeds_silently(
        review_screen, backing_files, sample_result, monkeypatch):
    r2 = dict(sample_result)
    r2["page"] = 2
    rs = make_run_state([sample_result, r2], backing_files,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    called = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: called.append(1) or QMessageBox.Yes)
    review_screen._go_next()
    settle(review_screen)

    assert called == []  # no confirmation needed -- nothing was dirty
    assert review_screen.current_index == 1


def test_navigating_away_with_unsaved_changes_prompts_and_blocks_on_no(
        review_screen, backing_files, sample_result, monkeypatch):
    """Regression test: _go_next()/_go_prev()/table-row-click used to call
    _load_page() unconditionally, silently discarding an unapplied answer
    toggle or field edit with only the Apply button's orange tint as a
    hint. Must now ask, and must stay put if the answer is No."""
    r2 = dict(sample_result)
    r2["page"] = 2
    rs = make_run_state([sample_result, r2], backing_files,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    review_screen._form_dirty = True
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    review_screen._go_next()
    settle(review_screen)

    assert review_screen.current_index == 0  # blocked, stayed on page 1


def test_navigating_away_with_unsaved_changes_proceeds_on_yes(
        review_screen, backing_files, sample_result, monkeypatch):
    r2 = dict(sample_result)
    r2["page"] = 2
    rs = make_run_state([sample_result, r2], backing_files,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    review_screen._form_dirty = True
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    review_screen._go_next()
    settle(review_screen)

    assert review_screen.current_index == 1


# ----- Busy-state navigation lock -----

def test_busy_state_disables_navigation(review_screen, backing_files, sample_result):
    r2 = dict(sample_result)
    r2["page"] = 2
    rs = make_run_state([sample_result, r2], backing_files,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    review_screen._local_busy = True
    review_screen._refresh_action_buttons()
    assert not review_screen.prev_btn.isEnabled()
    assert not review_screen.next_btn.isEnabled()
    assert not review_screen.table.isEnabled()

    review_screen._local_busy = False
    review_screen._refresh_action_buttons()
    assert review_screen.table.isEnabled()


# ----- Search/filter box -----

def _two_page_run_state(backing_files, sample_result, students_df):
    r2 = dict(sample_result)
    r2["page"] = 2
    r2["u_number"] = "000002"
    return make_run_state([sample_result, r2], backing_files, students_df=students_df,
                           correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)


def test_search_filters_pages_table_by_name(review_screen, backing_files, sample_result, sample_students_df):
    review_screen.load(_two_page_run_state(backing_files, sample_result, sample_students_df))
    settle(review_screen)

    review_screen.search_edit.setText("Bob")
    assert review_screen.table.isRowHidden(0)      # Alice
    assert not review_screen.table.isRowHidden(1)  # Bob


def test_search_filters_pages_table_by_u_number(review_screen, backing_files, sample_result, sample_students_df):
    review_screen.load(_two_page_run_state(backing_files, sample_result, sample_students_df))
    settle(review_screen)

    review_screen.search_edit.setText("000002")
    assert review_screen.table.isRowHidden(0)
    assert not review_screen.table.isRowHidden(1)


def test_clearing_search_shows_all_rows_again(review_screen, backing_files, sample_result, sample_students_df):
    review_screen.load(_two_page_run_state(backing_files, sample_result, sample_students_df))
    settle(review_screen)

    review_screen.search_edit.setText("Bob")
    review_screen.search_edit.setText("")
    assert not review_screen.table.isRowHidden(0)
    assert not review_screen.table.isRowHidden(1)


def test_search_box_resets_on_new_load(review_screen, backing_files, sample_result, sample_students_df):
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    review_screen.search_edit.setText("Bob")

    rs2 = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                          correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs2)
    settle(review_screen)
    assert review_screen.search_edit.text() == ""


# ----- Manual email entry/edit -----

def test_email_field_prefilled_from_roster(review_screen, backing_files, sample_result):
    students_df = pd.DataFrame({
        "Nom": ["Alice"], "Cognom1": ["Example"], "Cognom2": ["Smith"],
        "U_number": ["U000001"], "Email": ["alice@example.upf.edu"],
    })
    rs = make_run_state([sample_result], backing_files, students_df=students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    assert review_screen.edit_email.text() == "alice@example.upf.edu"
    assert review_screen.edit_email.isEnabled()


def test_email_field_editable_and_empty_when_no_email_on_file(
        review_screen, backing_files, sample_result, sample_students_df):
    """sample_students_df has no Email column -- a matched student with no
    email on file must still get an editable (not disabled) field, per the
    'enable adding one manually' requirement."""
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    assert review_screen.edit_email.text() == ""
    assert review_screen.edit_email.isEnabled()


def test_email_field_disabled_when_no_matched_student(review_screen, backing_files, sample_result):
    r = dict(sample_result)
    r["u_number"] = "999999"  # not in the roster
    rs = make_run_state([r], backing_files,
                         students_df=pd.DataFrame(columns=["Nom", "Cognom1", "Cognom2", "U_number"]),
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)
    assert not review_screen.edit_email.isEnabled()


def test_manually_entered_email_persists_to_students_df_and_lookup(
        review_screen, backing_files, sample_result, sample_students_df, monkeypatch):
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    monkeypatch.setattr(review_screen, "_save_async", lambda r: None)
    review_screen.edit_email.setText("new@upf.edu")
    review_screen._on_email_edited()

    assert review_screen.student_lookup["000001"]["Email"] == "new@upf.edu"
    row = review_screen.students_df[review_screen.students_df["U_number"] == "U000001"]
    assert row.iloc[0]["Email"] == "new@upf.edu"


def test_manually_entered_email_creates_email_column_if_missing(
        review_screen, backing_files, sample_result, sample_students_df, monkeypatch):
    """sample_students_df has no Email column at all -- adding one manually
    must not crash even though the source DataFrame never had it."""
    assert "Email" not in sample_students_df.columns
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    monkeypatch.setattr(review_screen, "_save_async", lambda r: None)
    review_screen.edit_email.setText("new@upf.edu")
    review_screen._on_email_edited()

    assert "Email" in review_screen.students_df.columns


def test_on_email_edited_does_not_save_when_unchanged(review_screen, backing_files, sample_result, monkeypatch):
    students_df = pd.DataFrame({
        "Nom": ["Alice"], "Cognom1": ["Example"], "Cognom2": ["Smith"],
        "U_number": ["U000001"], "Email": ["alice@example.upf.edu"],
    })
    rs = make_run_state([sample_result], backing_files, students_df=students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    calls = []
    monkeypatch.setattr(review_screen, "_save_async", lambda r: calls.append(r))
    review_screen.edit_email.setText("alice@example.upf.edu")  # unchanged
    review_screen._on_email_edited()
    assert calls == []


# ----- Exam type -----

def test_exam_type_loaded_from_run_state(review_screen, backing_files, sample_result, sample_students_df):
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    rs["exam_type"] = "Final"
    review_screen.load(rs)
    settle(review_screen)
    assert review_screen.exam_type == "Final"
    assert review_screen.exam_type_combo.currentText() == "Final"


def test_exam_type_defaults_to_empty_for_older_cache_without_it(
        review_screen, backing_files, sample_result, sample_students_df):
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    assert "exam_type" not in rs
    review_screen.load(rs)  # must not raise KeyError
    settle(review_screen)
    assert review_screen.exam_type == ""


def test_changing_exam_type_after_load_triggers_save(
        review_screen, backing_files, sample_result, sample_students_df, monkeypatch):
    rs = make_run_state([sample_result], backing_files, students_df=sample_students_df,
                         correct_answers_by_perm={"1": {1: {"A"}}}, num_questions=2, num_options=4)
    review_screen.load(rs)
    settle(review_screen)

    calls = []
    monkeypatch.setattr(review_screen, "_save_async", lambda r: calls.append(r))
    review_screen.exam_type_combo.setCurrentText("Final")
    assert review_screen.exam_type == "Final"
    assert len(calls) == 1
