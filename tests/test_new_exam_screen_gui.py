"""gui/new_exam_screen.py: the Run Analysis button's colour must reflect
whether the four required inputs (PDF, students list, answers file, exam
type -- the output directory has a default and doesn't count) are all
filled in, so it's obvious at a glance whether clicking it will actually
do anything.
"""

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def new_exam_screen(qapp):
    from gui.new_exam_screen import NewExamScreen
    return NewExamScreen()


def _fill_files(screen):
    screen.pdf_row.setText("exam.pdf")
    screen.students_row.setText("students.csv")
    screen.answers_row.setText("answers.csv")


def test_run_button_starts_red_when_nothing_selected(new_exam_screen):
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_run_button_stays_red_with_files_set_but_no_exam_type(new_exam_screen):
    """Regression test: the three file fields alone used to be enough to
    turn the button green, before Exam type was made a required field too."""
    _fill_files(new_exam_screen)
    assert new_exam_screen.exam_type_combo.currentText() == ""
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_run_button_turns_green_once_all_four_required_fields_are_set(new_exam_screen):
    _fill_files(new_exam_screen)
    new_exam_screen.exam_type_combo.setCurrentText("Midterm")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.READY_STYLE


def test_run_button_stays_red_if_only_two_of_three_files_are_set(new_exam_screen):
    new_exam_screen.pdf_row.setText("exam.pdf")
    new_exam_screen.students_row.setText("students.csv")
    # answers_row left blank
    new_exam_screen.exam_type_combo.setCurrentText("Midterm")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_run_button_turns_red_again_if_a_field_is_cleared(new_exam_screen):
    _fill_files(new_exam_screen)
    new_exam_screen.exam_type_combo.setCurrentText("Midterm")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.READY_STYLE

    new_exam_screen.students_row.setText("")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_run_button_turns_red_again_if_exam_type_is_cleared(new_exam_screen):
    _fill_files(new_exam_screen)
    new_exam_screen.exam_type_combo.setCurrentText("Midterm")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.READY_STYLE

    new_exam_screen.exam_type_combo.setCurrentText("")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_output_directory_field_does_not_count_toward_ready_state(new_exam_screen):
    """output_row already defaults to './output' -- that pre-filled value
    must not make the button look ready before the actually-required
    fields are set."""
    assert new_exam_screen.output_row.text() == "./output"
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE
