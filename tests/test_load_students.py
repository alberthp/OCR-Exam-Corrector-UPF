"""load_students(): all 4 supported student-list formats, plus adversarial
data (blank cells, duplicates, encodings, malformed headers).

Includes permanent regression tests for two bugs found during the v1.4
stress-testing pass: the documented ";-separated CSV" variant of the UPF
official export was completely unreadable, and blank Nom/Cognom1/Email
cells rendered as the literal text "nan".
"""

import pandas as pd
import pytest

import omr_correct as omr


def write_csv(tmp_path, name, content, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(content.encode(encoding))
    return str(path)


# ----- Format 1: plain Nom/Cognom1/Cognom2/U_number -----

def test_standard_format(simple_students_csv):
    df = omr.load_students(simple_students_csv)
    assert len(df) == 3
    assert list(df.columns[:4]) == ["Nom", "Cognom1", "Cognom2", "U_number"]
    assert df.iloc[0]["Nom"] == "Alice"


# ----- Format 2: UPF official export (course title + real header) -----

def test_upf_official_export_xls_style_two_row_header(upf_export_csv):
    df = omr.load_students(upf_export_csv)
    assert len(df) == 2
    assert df.iloc[0]["U_number"] == "u000001"
    assert df.iloc[0]["Cognom1"] == "Example"


def test_upf_official_export_semicolon_csv_with_no_separator_on_title_line(tmp_path):
    """Regression test: a course-title-only first line with zero
    separators used to make EVERY read attempt see exactly 1 column
    (pandas infers the header from line 1), so the >= 2 column acceptance
    check never passed for any separator/encoding combination and the
    whole file unconditionally failed to load.
    """
    path = write_csv(
        tmp_path, "clean_upf.csv",
        "LSDS2025\n"
        "IDUSUARI;NIA;COGNOM1;COGNOM2;NOM\n"
        "u000001;1;Example;Smith;Alice\n"
        "u000002;2;Sample;Jones;Bob\n",
    )
    df = omr.load_students(path)
    assert len(df) == 2
    assert df.iloc[0]["Nom"] == "Alice"
    assert df.iloc[1]["Nom"] == "Bob"


def test_upf_official_export_with_blank_cell_in_a_ragged_row(tmp_path):
    """The variant that originally surfaced the bug: a trailing blank
    PRACTICA-like cell producing a ragged row shouldn't matter here since
    this format doesn't have that column -- kept as a second, slightly
    different repro of the same header-detection path."""
    path = write_csv(
        tmp_path, "upf2.csv",
        "LSDS2025\n"
        "IDUSUARI;NIA;COGNOM1;COGNOM2;NOM;EMAIL;PRACTICA\n"
        "u000001;1;A;A;Alice;a@upf.edu;102\n"
        "u000002;2;B;B;Bob;b@upf.edu;\n",
    )
    df = omr.load_students(path)
    assert len(df) == 2
    assert pd.isna(df.iloc[1]["TheoryGroup"])  # blank PRACTICA -> no theory group


# ----- Format 3: Moodle "participants" export -----

def test_moodle_participants_format(moodle_participants_csv):
    df = omr.load_students(moodle_participants_csv)
    assert len(df) == 2
    assert df.iloc[0]["Cognom1"] == "Example"
    assert df.iloc[0]["Cognom2"] == "Smith"
    assert df.iloc[0]["TheoryGroup"] == "2"  # leading digit of "201-7"
    assert df.iloc[1]["TheoryGroup"] == "1"  # leading digit of "101-1"


def test_moodle_format_invalid_theory_group_codes_become_nan(tmp_path):
    path = write_csv(
        tmp_path, "moodle_bad.csv",
        'Nom,Cognoms,"Número ID",Grups\n'
        'Alice,"A A",u1,301-1\n'   # leading digit 3 -- not a valid theory group
        'Bob,"B B",u2,-5\n'
        'Carol,"C C",u3,\n',
    )
    df = omr.load_students(path)
    assert df["TheoryGroup"].isna().all()


# ----- Format 4: llistatGGiA export (EMAIL/PRACTICA) -----

def test_llistatgia_format_email_and_practica(tmp_path):
    path = write_csv(
        tmp_path, "llistat.csv",
        "LSDS2025\n"
        "IDUSUARI;NIA;COGNOM1;COGNOM2;NOM;EMAIL;PRACTICA\n"
        "u000001;1;Example;Smith;Alice;alice@upf.edu;102\n",
    )
    df = omr.load_students(path)
    assert df.iloc[0]["Email"] == "alice@upf.edu"
    assert df.iloc[0]["TheoryGroup"] == "1"


# ----- Adversarial / edge cases -----

def test_duplicate_u_number_both_rows_kept(tmp_path):
    """load_students() itself doesn't dedupe -- callers building a lookup
    dict resolve duplicates via last-wins, consistently across the app.
    This test documents current (accepted) behavior, not a bug."""
    path = write_csv(tmp_path, "dup.csv",
                      "Nom,Cognom1,Cognom2,U_number\nAlice,A,A,U1\nBob,B,B,U1\n")
    df = omr.load_students(path)
    assert len(df) == 2


def test_headers_only_zero_rows(tmp_path):
    path = write_csv(tmp_path, "empty.csv", "Nom,Cognom1,Cognom2,U_number\n")
    df = omr.load_students(path)
    assert len(df) == 0


def test_missing_u_number_column_raises(tmp_path):
    path = write_csv(tmp_path, "nouid.csv", "Nom,Cognom1,Cognom2\nAlice,A,A\n")
    with pytest.raises(ValueError, match="U_number"):
        omr.load_students(path)


def test_all_blank_u_numbers_drops_all_rows(tmp_path):
    path = write_csv(tmp_path, "blank_uid.csv",
                      "Nom,Cognom1,Cognom2,U_number\nAlice,A,A,\nBob,B,B,   \n")
    df = omr.load_students(path)
    assert len(df) == 0


def test_blank_nom_renders_as_empty_string_not_nan(tmp_path):
    """Regression test: a blank Nom cell used to read back as the float
    NaN, which rendered as the literal text 'nan' wherever it was
    interpolated into a display string (Excel, PDF, email)."""
    path = write_csv(tmp_path, "blank_nom.csv",
                      "Nom,Cognom1,Cognom2,U_number\n,Smith,,U000001\n")
    df = omr.load_students(path)
    assert df.iloc[0]["Nom"] == ""
    assert df.iloc[0]["Nom"] is not None


def test_blank_cognom2_renders_as_empty_string(simple_students_csv, tmp_path):
    path = write_csv(tmp_path, "single_surname.csv",
                      "Nom,Cognom1,Cognom2,U_number\nAlice,Example,,U000001\n")
    df = omr.load_students(path)
    assert df.iloc[0]["Cognom2"] == ""


def test_latin1_encoded_accented_names(tmp_path):
    path = write_csv(
        tmp_path, "latin1.csv",
        "Nom,Cognom1,Cognom2,U_number\nJosé,Núñez,García,U000001\n",
        encoding="latin-1",
    )
    df = omr.load_students(path)
    assert df.iloc[0]["Nom"] == "José"
    assert df.iloc[0]["Cognom1"] == "Núñez"


def test_semicolon_separated_simple_format(tmp_path):
    path = write_csv(tmp_path, "semi.csv",
                      "Nom;Cognom1;Cognom2;U_number\nAlice;A;A;U000001\n")
    df = omr.load_students(path)
    assert len(df) == 1
    assert "Nom" in df.columns


def test_u_number_prefix_and_case_preserved_raw(tmp_path):
    """Normalization (stripping the U prefix, uppercasing) happens at
    lookup time downstream, not inside load_students()."""
    path = write_csv(
        tmp_path, "mixed_case.csv",
        "Nom,Cognom1,Cognom2,U_number\nAlice,A,A, U000001 \nBob,B,B,u000002\n",
    )
    df = omr.load_students(path)
    assert df.iloc[0]["U_number"] == "U000001"
    assert df.iloc[1]["U_number"] == "u000002"
