"""gui/new_exam_screen.py: the Run Analysis button's colour must reflect
whether the three required inputs (PDF, students list, answers file --
the output directory has a default and doesn't count) are all filled in,
so it's obvious at a glance whether clicking it will actually do anything.
"""

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def new_exam_screen(qapp):
    from gui.new_exam_screen import NewExamScreen
    return NewExamScreen()


def test_run_button_starts_red_when_nothing_selected(new_exam_screen):
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_run_button_turns_green_once_all_three_required_fields_are_set(new_exam_screen):
    new_exam_screen.pdf_row.setText("exam.pdf")
    new_exam_screen.students_row.setText("students.csv")
    new_exam_screen.answers_row.setText("answers.csv")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.READY_STYLE


def test_run_button_stays_red_if_only_two_of_three_are_set(new_exam_screen):
    new_exam_screen.pdf_row.setText("exam.pdf")
    new_exam_screen.students_row.setText("students.csv")
    # answers_row left blank
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_run_button_turns_red_again_if_a_field_is_cleared(new_exam_screen):
    new_exam_screen.pdf_row.setText("exam.pdf")
    new_exam_screen.students_row.setText("students.csv")
    new_exam_screen.answers_row.setText("answers.csv")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.READY_STYLE

    new_exam_screen.students_row.setText("")
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE


def test_output_directory_field_does_not_count_toward_ready_state(new_exam_screen):
    """output_row already defaults to './output' -- that pre-filled value
    must not make the button look ready before the three actually-required
    fields are set."""
    assert new_exam_screen.output_row.text() == "./output"
    assert new_exam_screen.run_btn.styleSheet() == new_exam_screen.NOT_READY_STYLE
