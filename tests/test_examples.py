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
    assert len(df) == 12
    assert {"Nom", "Cognom1", "Cognom2", "U_number"}.issubset(df.columns)
    assert df["U_number"].notna().all()


def test_example_student_lists_describe_the_same_12_students():
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
