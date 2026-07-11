"""load_correct_answers(), validate_answer_key(), apply_answer_key_row_fix().

Covers every issue class validate_answer_key() knows about (duplicate
question, missing question, blank Perm, missing option column) plus the
scoring-safe loading behavior of load_correct_answers(), and includes
permanent regression tests for three bugs found during the v1.4 stress
testing passes.
"""

import pandas as pd
import pytest

import omr_correct as omr


def write_csv(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


# ----- load_correct_answers: happy path -----

def test_load_correct_answers_basic(simple_answer_key_csv):
    correct = omr.load_correct_answers(simple_answer_key_csv)
    assert correct == {
        "1": {1: {"A"}, 2: {"B", "C"}},
        "2": {1: {"B"}, 2: {"A", "D"}},
    }


def test_load_correct_answers_perm_keys_are_strings(simple_answer_key_csv):
    correct = omr.load_correct_answers(simple_answer_key_csv)
    assert set(correct.keys()) == {"1", "2"}


# ----- validate_answer_key: clean file -----

def test_validate_clean_file_has_no_issues(simple_answer_key_csv):
    issues = omr.validate_answer_key(simple_answer_key_csv, expected_num_questions=2)
    assert issues == []


# ----- DUPLICATE -----

def test_validate_flags_duplicate_question(tmp_path):
    path = write_csv(tmp_path, "dup.csv",
                      "Perm,QuestionNum,A,B\n1,1,1,0\n1,1,0,1\n")
    issues = omr.validate_answer_key(path)
    assert len(issues) == 1
    assert "appears 2 times" in issues[0]["message"]
    assert issues[0]["rows"] == [2, 3]


# ----- MISSING -----

def test_validate_flags_missing_question_relative_to_expected_num_questions(tmp_path):
    path = write_csv(tmp_path, "missing.csv", "Perm,QuestionNum,A,B\n1,1,1,0\n")
    issues = omr.validate_answer_key(path, expected_num_questions=2)
    assert len(issues) == 1
    assert issues[0]["question"] == 2


def test_validate_suggests_fix_for_perm_labeled_one_row_too_early(tmp_path):
    """The exact real-world bug this session's answer-key fix was built
    for: a Perm value copy/pasted one row too early in a file ordered by
    Perm-then-QuestionNum.
    """
    path = write_csv(
        tmp_path, "shifted.csv",
        "Perm,QuestionNum,A,B\n"
        "1,1,1,0\n"
        "2,2,0,1\n"   # should be Perm=1 (continues Perm 1's Q1 -> Q2)
        "2,1,1,0\n",
    )
    issues = omr.validate_answer_key(path, expected_num_questions=2)
    missing = [i for i in issues if i["perm"] == "1" and i["question"] == 2]
    assert len(missing) == 1
    fix = missing[0]["suggested_fix"]
    assert fix is not None
    assert fix["row"] == 3
    assert fix["new_perm"] == "1"


# ----- Blank Perm (regression: used to become a phantom "nan" permutation) -----

def test_validate_flags_blank_perm_cell(tmp_path):
    path = write_csv(tmp_path, "blank_perm.csv",
                      'Perm,QuestionNum,A,B\n"",1,1,0\n1,1,1,0\n')
    issues = omr.validate_answer_key(path, expected_num_questions=1)
    blank_issues = [i for i in issues if "blank Perm" in i["message"]]
    assert len(blank_issues) == 1
    assert blank_issues[0]["rows"] == [2]


def test_load_correct_answers_skips_blank_perm_row_instead_of_faking_one(tmp_path):
    path = write_csv(tmp_path, "blank_perm2.csv",
                      'Perm,QuestionNum,A,B\n"",1,1,0\n1,1,1,0\n')
    correct = omr.load_correct_answers(path)
    assert "nan" not in correct
    assert set(correct.keys()) == {"1"}


def test_validate_two_blank_perm_rows_does_not_crash_the_sort(tmp_path):
    """Regression test: the issue-sort key assumed 'question' was always an
    int; two blank-Perm rows (question=None for both) used to raise
    TypeError comparing None to None.
    """
    path = write_csv(
        tmp_path, "two_blank.csv",
        'Perm,QuestionNum,A,B\n"",1,1,0\n"",2,0,1\n1,1,1,0\n1,2,0,1\n',
    )
    issues = omr.validate_answer_key(path, expected_num_questions=2)
    assert len([i for i in issues if "blank Perm" in i["message"]]) == 2


def test_write_excel_does_not_create_phantom_nan_sheet(tmp_path):
    """End-to-end regression test for the spurious 'Perm nan' sheet bug:
    write_excel must never create a sheet for a blank-Perm row.
    """
    import openpyxl
    path = write_csv(tmp_path, "blank_perm3.csv",
                      'Perm,QuestionNum,A,B\n"",1,1,0\n1,1,1,0\n')
    correct = omr.load_correct_answers(path)
    out = tmp_path / "out.xlsx"
    results = [{"page": 1, "status": "OK", "u_number": "000001", "u_status": "OK",
                "dni": "1", "parcial": "1", "permut": 1, "grup": "1",
                "answers": {1: {"marks": {"A"}}}}]
    omr.write_excel(results, None, correct, str(out), num_questions=1, num_options=2)
    wb = openpyxl.load_workbook(out)
    assert not any("nan" in s.lower() for s in wb.sheetnames)


# ----- MISSING_OPTION (answer key has fewer option columns than configured) -----

def test_validate_flags_missing_option_columns(simple_answer_key_csv):
    issues = omr.validate_answer_key(simple_answer_key_csv, expected_num_options=6)
    option_issues = [i for i in issues if "Missing:" in i["message"]]
    assert len(option_issues) == 1
    assert "E, F" in option_issues[0]["message"]


def test_validate_does_not_flag_option_columns_when_count_matches(simple_answer_key_csv):
    issues = omr.validate_answer_key(simple_answer_key_csv, expected_num_options=4)
    assert not any("Missing:" in i["message"] for i in issues)


def test_validate_option_check_is_opt_in(simple_answer_key_csv):
    """Without expected_num_options, a genuinely too-small answer key is
    not flagged -- this must stay backward compatible for callers that
    don't pass it."""
    issues = omr.validate_answer_key(simple_answer_key_csv)
    assert not any("Missing:" in i["message"] for i in issues)


def test_missing_option_scores_a_legitimate_mark_as_always_wrong(tmp_path):
    """Demonstrates the actual grading consequence the MISSING_OPTION check
    exists to catch: with only A-D in the key but a 6-option exam, marking
    E is indistinguishable from marking a wrong answer.
    """
    path = write_csv(tmp_path, "narrow.csv", "Perm,QuestionNum,A,B,C,D\n1,1,1,0,0,0\n")
    correct = omr.load_correct_answers(path)
    score = omr.score_question({"E"}, correct["1"][1], num_options=6)
    assert score == 0.0  # E can never be credited: it's not in any correct set


# ----- apply_answer_key_row_fix -----

def test_apply_answer_key_row_fix_relabels_the_row(tmp_path):
    path = write_csv(
        tmp_path, "fixme.csv",
        "Perm,QuestionNum,A,B\n1,1,1,0\n2,2,0,1\n2,1,1,0\n",
    )
    omr.apply_answer_key_row_fix(path, row_number=3, new_perm="1")
    df = pd.read_csv(path)
    assert df.loc[1, "Perm"] == 1  # row_number=3 -> data index 1 (0-based)


def test_apply_answer_key_row_fix_writes_a_backup(tmp_path):
    path = write_csv(tmp_path, "fixme2.csv", "Perm,QuestionNum,A,B\n1,1,1,0\n")
    omr.apply_answer_key_row_fix(path, row_number=2, new_perm="2")
    assert (tmp_path / "fixme2.csv.bak").exists()


def test_apply_answer_key_row_fix_out_of_range_raises(tmp_path):
    path = write_csv(tmp_path, "fixme3.csv", "Perm,QuestionNum,A,B\n1,1,1,0\n")
    with pytest.raises(ValueError):
        omr.apply_answer_key_row_fix(path, row_number=999, new_perm="2")


def test_full_fix_workflow_resolves_all_issues(tmp_path):
    """The exact scenario from the real LSDS_Retake2026_PermALL_Fixed.csv
    bug this session found: a row is mislabeled into Perm 2 right where
    Perm 1's sequence ends (row 3: Perm=2, Q=2, immediately after Perm 1's
    Q1) -- but Perm 2 ALSO has its own genuine Q2 later in the file (row
    5), same as the real file had a genuine Perm-2 Q30 elsewhere. Applying
    the suggested fix must resolve both the resulting duplicate AND the
    missing question in one step, exactly like the real file did.
    """
    path = write_csv(
        tmp_path, "workflow.csv",
        "Perm,QuestionNum,A,B\n"
        "1,1,1,0\n"
        "2,2,0,1\n"   # row 3: misplaced -- should be Perm=1, Q=2
        "2,1,1,0\n"
        "2,2,1,1\n",  # row 5: Perm 2's own genuine Q2
    )
    issues = omr.validate_answer_key(path, expected_num_questions=2)
    fixable = [i for i in issues if i["suggested_fix"]]
    assert len(fixable) == 1
    fix = fixable[0]["suggested_fix"]
    omr.apply_answer_key_row_fix(path, fix["row"], fix["new_perm"])
    remaining = omr.validate_answer_key(path, expected_num_questions=2)
    assert remaining == []
