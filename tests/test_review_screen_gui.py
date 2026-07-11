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
    """
    import PySide6.QtWidgets as qw
    app = qw.QApplication.instance()
    for worker in list(getattr(screen, "_pending_preview_workers", [])):
        worker.wait(5000)
    for worker in list(getattr(screen, "_pending_sync_workers", [])):
        worker.wait(5000)
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
