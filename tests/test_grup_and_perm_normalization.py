"""decode_grup(), _normalize_group_value(), _normalize_perm_value(), and
backfill_and_validate_groups() -- the GRUP/roster cross-check machinery.
"""

import pandas as pd
import pytest

import omr_correct as omr


# ----- decode_grup -----

def test_decode_grup_blank():
    assert omr.decode_grup([None, None]) == (None, "BLANK")


def test_decode_grup_single_digit():
    assert omr.decode_grup([1, None]) == ("1", "OK")


def test_decode_grup_two_digits():
    assert omr.decode_grup([0, 1]) == ("01", "OK")


# ----- _normalize_group_value -----

@pytest.mark.parametrize("raw,expected", [
    ("01", "1"),
    ("1", "1"),
    ("02", "2"),
    ("2", "2"),
    (" 1 ", "1"),
    ("abc", "abc"),
    ("", ""),
])
def test_normalize_group_value(raw, expected):
    assert omr._normalize_group_value(raw) == expected


# ----- _normalize_perm_value -----

@pytest.mark.parametrize("raw,expected", [
    (0, "0"),
    ("0", "0"),
    (0.0, "0"),  # the float-upcast case that caused the Critical routing bug
    ("1.0", "1"),
    (" 2 ", "2"),
    ("A", "A"),
])
def test_normalize_perm_value(raw, expected):
    assert omr._normalize_perm_value(raw) == expected


def test_normalize_perm_value_float_upcast_matches_int_form():
    """Regression test for the Critical bug: if the answer key's Perm
    column gets upcast to float64 (any blank cell elsewhere in it triggers
    this in pandas), the normalized form must still match the normalized
    form of the clean int the scanner produces -- otherwise every page for
    that permutation silently routes to No_Perm_Detected.
    """
    from_scan = omr._normalize_perm_value(0)          # decode() always yields a clean int
    from_float_upcast_csv = omr._normalize_perm_value(0.0)
    assert from_scan == from_float_upcast_csv == "0"


# ----- backfill_and_validate_groups -----

def _students_df_with_theory_group(theory_group):
    return pd.DataFrame({
        "Nom": ["Alice"], "Cognom1": ["Example"], "Cognom2": ["Smith"],
        "U_number": ["U000001"], "TheoryGroup": [theory_group],
    })


def test_backfill_fills_blank_grup_from_roster():
    results = [{"u_number": "000001", "grup": None}]
    omr.backfill_and_validate_groups(results, _students_df_with_theory_group("2"))
    assert results[0]["grup"] == "2"
    assert results[0]["grup_source"] == "roster"
    assert results[0]["grup_check"] == "FROM_ROSTER"


def test_backfill_confirms_matching_scan():
    results = [{"u_number": "000001", "grup": "1"}]
    omr.backfill_and_validate_groups(results, _students_df_with_theory_group("1"))
    assert results[0]["grup"] == "1"
    assert results[0]["grup_check"] == "OK"


def test_backfill_normalizes_padded_scan_before_comparing():
    """Regression test: scanned GRUP is zero-padded ('01') but the roster
    TheoryGroup is a bare digit ('1') -- these must be treated as equal,
    not flagged as a false MISMATCH (the bug found and fixed this session).
    """
    results = [{"u_number": "000001", "grup": "01"}]
    omr.backfill_and_validate_groups(results, _students_df_with_theory_group("1"))
    assert results[0]["grup_check"] == "OK"


def test_backfill_flags_genuine_mismatch_without_overwriting():
    results = [{"u_number": "000001", "grup": "2"}]
    omr.backfill_and_validate_groups(results, _students_df_with_theory_group("1"))
    assert results[0]["grup"] == "2"  # NOT auto-corrected
    assert "MISMATCH" in results[0]["grup_check"]


def test_backfill_noop_when_no_theory_group_column():
    results = [{"u_number": "000001", "grup": None}]
    students_df = pd.DataFrame({"Nom": ["Alice"], "U_number": ["U000001"]})
    omr.backfill_and_validate_groups(results, students_df)
    assert results[0]["grup"] is None
    assert "grup_check" not in results[0]


def test_backfill_unmatched_student_leaves_grup_alone():
    results = [{"u_number": "999999", "grup": None}]
    omr.backfill_and_validate_groups(results, _students_df_with_theory_group("1"))
    assert results[0]["grup"] is None
    assert results[0]["grup_check"] == ""
