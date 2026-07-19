"""Shared fixtures for the OMR Exam Corrector test suite.

All fixture data here is synthetic (fake names, fake U-numbers) -- the
real exam PDF / student rosters / answer key in the project root are
gitignored as private student data (see .gitignore) and are only used by
the opt-in integration tests in test_integration_real_data.py, which skip
themselves when those files aren't present on disk.
"""

import os
import sys

import pandas as pd
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import omr_correct as omr  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--packaged-exe", action="store", default=None,
        help="Path to a frozen e2e_driver.exe for test_stability_packaged_exe.py "
             "(see that file's module docstring for how to build one)",
    )


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test session -- PySide6 forbids
    creating more than one per process. Uses the offscreen platform so the
    suite runs without a real display (CI, headless dev boxes); this is
    fine for the logic-level assertions the GUI tests make (widget state,
    text content, column counts) since none of them compare rendered pixels.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def simple_students_csv(tmp_path):
    """Standard Nom/Cognom1/Cognom2/U_number format, 3 synthetic students."""
    path = tmp_path / "students.csv"
    path.write_text(
        "Nom,Cognom1,Cognom2,U_number\n"
        "Alice,Example,Smith,U000001\n"
        "Bob,Sample,Jones,U000002\n"
        "Carol,Test,Brown,U000003\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def upf_export_csv(tmp_path):
    """UPF official export format: course-title line, then real headers."""
    path = tmp_path / "upf_export.csv"
    path.write_text(
        "LSDS2025\n"
        "IDUSUARI;NIA;NIP;COGNOM1;COGNOM2;NOM\n"
        "u000001;10001;20001;Example;Smith;Alice\n"
        "u000002;10002;20002;Sample;Jones;Bob\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def moodle_participants_csv(tmp_path):
    """Moodle 'participants' export format: Cognoms/Numero ID/Grups."""
    path = tmp_path / "participants.csv"
    path.write_text(
        'Nom,Cognoms,"Número ID",Grups\n'
        'Alice,"Example Smith",u000001,201-7\n'
        'Bob,"Sample Jones",u000002,101-1\n',
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def simple_answer_key_csv(tmp_path):
    """A clean 2-permutation, 2-question, 4-option answer key."""
    path = tmp_path / "answers.csv"
    path.write_text(
        "Perm,QuestionNum,A,B,C,D\n"
        "1,1,1,0,0,0\n"
        "1,2,0,1,1,0\n"
        "2,1,0,1,0,0\n"
        "2,2,1,0,0,1\n",
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def sample_result():
    """One synthetic page-result dict shaped like process_page()'s output,
    with a real (small) numpy image so GUI code paths that touch
    r['_corrected'].shape don't need a special case.
    """
    import numpy as np
    return {
        "page": 1,
        "status": "OK",
        "_corrected": np.zeros((100, 100, 3), dtype="uint8"),
        "u_number": "000001",
        "u_status": "OK",
        "dni": "11111111",
        "parcial": "1",
        "permut": "1",
        "grup": "1",
        "answers": {
            1: {"marks": {"A"}},
            2: {"marks": {"B", "C"}},
        },
    }


@pytest.fixture
def sample_students_df():
    return pd.DataFrame({
        "Nom": ["Alice", "Bob"],
        "Cognom1": ["Example", "Sample"],
        "Cognom2": ["Smith", "Jones"],
        "U_number": ["U000001", "U000002"],
    })


@pytest.fixture
def sample_correct_answers():
    return {"1": {1: {"A"}, 2: {"B", "C"}}}
