"""Sanity-checks the shipped synthetic example files in examples/ actually
load the way examples/README.md claims -- these are the files a new user
tries first, so a silent format drift here (e.g. a future load_students()
change that the real, gitignored fixtures wouldn't catch) would be an
especially bad first impression.

Every value in these files is invented; see examples/README.md.
"""

import os

import pytest

import omr_correct as omr

EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

STUDENT_LIST_FILES = [
    "students_standard_example.csv",
    "students_upf_official_example.csv",
    "students_moodle_example.csv",
    "students_llistatGGiA_example.xlsx",
]


@pytest.mark.parametrize("filename", STUDENT_LIST_FILES)
def test_example_student_list_loads(filename):
    df = omr.load_students(os.path.join(EXAMPLES_DIR, filename))
    assert len(df) == 13
    assert {"Nom", "Cognom1", "Cognom2", "U_number"}.issubset(df.columns)
    assert df["U_number"].notna().all()


def test_example_student_lists_describe_the_same_13_students():
    """All four formats are meant to be the same fake roster, just
    exported differently -- catches an example file being edited out of
    sync with the others."""
    u_numbers = []
    for filename in STUDENT_LIST_FILES:
        df = omr.load_students(os.path.join(EXAMPLES_DIR, filename))
        cleaned = set(df["U_number"].astype(str).str.strip().str.upper().str.replace("U", ""))
        u_numbers.append(cleaned)
    assert len(set(map(frozenset, u_numbers))) == 1, "example rosters disagree on which students exist"


def test_example_moodle_and_llistatgia_lists_have_a_theory_group():
    for filename in ["students_moodle_example.csv", "students_llistatGGiA_example.xlsx"]:
        df = omr.load_students(os.path.join(EXAMPLES_DIR, filename))
        assert "TheoryGroup" in df.columns
        assert df["TheoryGroup"].isin(["1", "2"]).all()


def test_example_llistatgia_list_has_email():
    df = omr.load_students(os.path.join(EXAMPLES_DIR, "students_llistatGGiA_example.xlsx"))
    assert "Email" in df.columns
    assert df["Email"].str.contains("@").all()


def test_example_answer_key_is_clean():
    path = os.path.join(EXAMPLES_DIR, "answers_example.csv")
    issues = omr.validate_answer_key(path, expected_num_questions=10, expected_num_options=4)
    assert issues == []


def test_example_answer_key_loads_both_permutations_complete():
    path = os.path.join(EXAMPLES_DIR, "answers_example.csv")
    correct = omr.load_correct_answers(path)
    assert set(correct.keys()) == {"1", "2"}
    assert len(correct["1"]) == 10
    assert len(correct["2"]) == 10
    # a mix of single- and multi-correct-answer questions, as advertised
    sizes = {len(v) for v in correct["1"].values()}
    assert sizes == {1, 2}


def test_example_scan_answer_key_is_clean():
    path = os.path.join(EXAMPLES_DIR, "answers_scan_example.csv")
    issues = omr.validate_answer_key(path, expected_num_questions=20, expected_num_options=4)
    assert issues == []


def test_example_scan_answer_key_flags_a_5_option_mismatch():
    """This is the exact misconfiguration MANUAL.md section 5 warns about
    (a 4-option key used for a 5-option exam) -- reproduced here for real
    since answers_scan_example.csv only defines A-D and
    scanned_exam_example.pdf's template physically has an E row."""
    path = os.path.join(EXAMPLES_DIR, "answers_scan_example.csv")
    issues = omr.validate_answer_key(path, expected_num_questions=20, expected_num_options=5)
    assert len(issues) == 1
    assert "Missing: E" in issues[0]["message"]


def test_example_scan_answer_key_loads():
    path = os.path.join(EXAMPLES_DIR, "answers_scan_example.csv")
    correct = omr.load_correct_answers(path)
    assert set(correct.keys()) == {"1"}
    assert len(correct["1"]) == 20


class TestScannedExamExample:
    """End-to-end smoke test against the shipped (invented, non-gitignored)
    scanned exam -- unlike tests/test_integration_real_data.py this always
    runs, since scanned_exam_example.pdf ships with the repo. See
    MANUAL.md section 5.1 for what each question is meant to demonstrate;
    the assertions below are the same numbers documented there."""

    @staticmethod
    def _process(num_options):
        from pdf2image import convert_from_path

        pdf_path = os.path.join(EXAMPLES_DIR, "scanned_exam_example.pdf")
        dpi = omr.detect_pdf_dpi(pdf_path)
        pages = convert_from_path(pdf_path, dpi=dpi)
        assert len(pages) == 1
        result, _ = omr.process_page(pages[0], 1, num_questions=20, num_options=num_options, source_dpi=dpi)
        assert result["status"] == "OK"
        return result

    def test_identification_fields(self):
        r = self._process(num_options=4)
        assert r["dni"] == "21566429"
        assert r["u_number"] == "237958"
        assert r["grup"] == "1"
        assert r["permut"] == 1
        assert sum(1 for a in r["answers"].values() if a["marks"]) == 19  # Q15 left blank

    def test_stray_extra_option_mark_is_ignored_when_num_options_matches_key(self):
        """Question 11: the student also filled bubble E, which doesn't
        exist in this exam's 4-option key. Configured correctly
        (--num-options 4, matching answers_scan_example.csv), that mark
        is simply never read -- Q11 scores full credit."""
        r = self._process(num_options=4)
        assert r["answers"][11]["marks"] == {"C"}

    def test_stray_extra_option_mark_is_read_when_num_options_is_misconfigured(self):
        """Same page, but processed as a 5-option exam (matching the
        sheet's generic template, not the 4-option key) -- now the E mark
        is read, and scoring will treat it as always-wrong since the key
        has no E column for any question."""
        r = self._process(num_options=5)
        assert r["answers"][11]["marks"] == {"C", "E"}
