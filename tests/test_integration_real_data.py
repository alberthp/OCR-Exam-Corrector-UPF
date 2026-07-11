"""Integration tests against the real (gitignored, private) exam PDF and
roster/answer-key files sitting in the project root, if present.

These exercise the parts no synthetic fixture can: real scanned bubble
sheets through the actual OCR/perspective-correction pipeline. Every test
here is skipped automatically when the underlying file isn't present (a
fresh checkout won't have it -- see .gitignore), so this file is safe to
ship and run anywhere; it just does less on a machine without the real
data. Run with `pytest -m integration` to select only these, or
`pytest -m "not integration"` to exclude the slow OCR pass.
"""

import os

import pytest

import omr_correct as omr

pytestmark = pytest.mark.integration

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_PDF = os.path.join(PROJECT_ROOT, "LSDS Retake Juliol2026 Questionnarie.pdf")
REAL_ANSWERS = os.path.join(PROJECT_ROOT, "LSDS_Retake2026_PermALL_Fixed.csv")
REAL_STUDENTS_MOODLE = os.path.join(PROJECT_ROOT, "courseid_91223_participants.csv")
REAL_STUDENTS_LLISTAT = os.path.join(PROJECT_ROOT, "llistatGGiA (8).xls")

skip_no_pdf = pytest.mark.skipif(not os.path.exists(REAL_PDF), reason="real exam PDF not present (gitignored)")
skip_no_answers = pytest.mark.skipif(not os.path.exists(REAL_ANSWERS), reason="real answer key not present (gitignored)")
skip_no_moodle = pytest.mark.skipif(not os.path.exists(REAL_STUDENTS_MOODLE), reason="real Moodle roster not present (gitignored)")
skip_no_llistat = pytest.mark.skipif(not os.path.exists(REAL_STUDENTS_LLISTAT), reason="real llistatGGiA roster not present (gitignored)")


@skip_no_answers
def test_real_answer_key_is_currently_clean():
    """The real answer key had a data bug (a Perm value copy/pasted one
    row too early) found and fixed earlier in this project's history --
    this asserts it's still fixed, not that it always was."""
    issues = omr.validate_answer_key(REAL_ANSWERS, expected_num_questions=30, expected_num_options=4)
    assert issues == []


@skip_no_answers
def test_real_answer_key_loads_both_permutations_complete():
    correct = omr.load_correct_answers(REAL_ANSWERS)
    assert set(correct.keys()) == {"1", "2"}
    assert len(correct["1"]) == 30
    assert len(correct["2"]) == 30


@skip_no_moodle
def test_real_moodle_roster_loads():
    df = omr.load_students(REAL_STUDENTS_MOODLE)
    assert len(df) > 0
    assert "TheoryGroup" in df.columns
    assert df["TheoryGroup"].isin(["1", "2"]).any()


@skip_no_llistat
def test_real_llistatgia_roster_loads_with_email():
    df = omr.load_students(REAL_STUDENTS_LLISTAT)
    assert len(df) > 0
    assert "Email" in df.columns
    assert df["Email"].str.contains("@").any()


@skip_no_pdf
def test_real_pdf_dpi_detection():
    dpi = omr.detect_pdf_dpi(REAL_PDF)
    assert dpi in (300, 600)


@skip_no_pdf
@skip_no_answers
@skip_no_moodle
@pytest.mark.slow
def test_full_pipeline_end_to_end(tmp_path):
    """The real, slow one: runs actual OCR against every page of the real
    scanned exam PDF and writes results.xlsx + annotated_review.pdf, the
    same way `python omr_correct.py ...` does. Takes on the order of a
    minute; this is the closest thing this project has to a true
    end-to-end smoke test and is worth the cost before a release.
    """
    from pdf2image import convert_from_path

    students_df = omr.load_students(REAL_STUDENTS_MOODLE)
    correct_answers_by_perm = omr.load_correct_answers(REAL_ANSWERS)
    dpi = omr.detect_pdf_dpi(REAL_PDF)
    pages = convert_from_path(REAL_PDF, dpi=dpi)
    assert len(pages) > 0

    all_results = []
    for i, page in enumerate(pages):
        r, _ = omr.process_page(page, i + 1, num_questions=30, num_options=4, source_dpi=dpi)
        all_results.append(r)

    n_ok = sum(1 for r in all_results if r.get("status") == "OK")
    assert n_ok == len(all_results), (
        f"{len(all_results) - n_ok} of {len(all_results)} pages failed processing"
    )

    omr.backfill_and_validate_groups(all_results, students_df)

    excel_path = tmp_path / "results.xlsx"
    pdf_path = tmp_path / "annotated_review.pdf"
    omr.write_excel(all_results, students_df, correct_answers_by_perm,
                     str(excel_path), num_questions=30, num_options=4)
    omr.write_annotated_pdf(all_results, str(pdf_path), students_df=students_df)

    assert excel_path.exists()
    assert pdf_path.exists()

    import openpyxl
    wb = openpyxl.load_workbook(excel_path)
    assert set(wb.sheetnames) >= {"Perm 1", "Perm 2", "No_Perm_Detected", "T1", "T2", "Summary"}
