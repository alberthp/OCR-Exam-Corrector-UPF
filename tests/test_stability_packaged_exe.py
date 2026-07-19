"""Packaged-.exe stability smoke test -- the highest-leverage remaining
gap in this suite, because it's the *only* place this project has actually
had a real crash: the v1.6 Qt6Core STATUS_STACK_BUFFER_OVERRUN worked fine
from source and only showed up in the frozen executable, root-caused to
PySide6/Qt thread-affinity-sensitive static initialization behaving
differently once bundled by PyInstaller. test_stability_e2e_subprocess.py
drives the real app end-to-end, but only from source -- it cannot catch a
packaging-specific regression (a missing hidden import, a bundled-resource
path that resolves differently once frozen, etc.).

This test does NOT build anything itself -- building takes several minutes
(a fresh venv + full dependency install + PyInstaller freeze) and doesn't
belong in a routine test run. Instead it drives an *already-built* frozen
executable, produced by tests/_e2e_driver.py via a PyInstaller spec that
mirrors "OMR Exam Corrector.spec" (same binaries/datas/hiddenimports) but
freezes tests/_e2e_driver.py instead of omr_gui.py as the entry point, so
the packaged binary can still be scripted through New Exam -> scan ->
Review -> navigate -> close exactly like the source-level e2e test, not
just checked for "does a window open".

Runs against every PDF in testing_dataset/, not just one -- five real
scanned exam batches of very different sizes (11 to 60 pages) exercise the
packaging/threading surface far more than a single small file would. Only
one of them (the Retake exam) has a real roster/answer-key sitting in the
project root; the other four get a synthetic roster + a clean, no-issues
answer key generated on the fly (matching the exam's real question count),
since this test only cares whether the app crashes on these real scans,
not whether the (synthetic) grading is meaningful.

Opt-in only (a dedicated `packaging` marker, excluded from both the
default run and `-m integration`): building the exe is a manual
pre-release step, not something to run on every `pytest -m integration`.
See MANUAL.md / TEST_SUITE.md for how to build it.

Usage:
    pytest -m packaging tests/test_stability_packaged_exe.py \\
        --packaged-exe "C:\\path\\to\\dist\\e2e_driver\\e2e_driver.exe"
"""

import os
import subprocess

import pytest

pytestmark = pytest.mark.packaging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTING_DATASET_DIR = os.path.join(PROJECT_ROOT, "testing_dataset")

# (pdf filename in testing_dataset/, num_questions, num_options, exam_type, page_count)
# page_count sizes each run's timeout -- a cold-started frozen exe plus PDF
# rendering plus per-page OCR legitimately needs more wall-clock time for a
# 60-page batch than a fixed timeout tuned for a small file would allow
# (confirmed by testing: a flat 180s timeout falsely "failed" the 60-page
# MT exam mid-scan, not because anything crashed or hung, just because 180s
# wasn't enough time for a batch that size).
EXAMS = [
    ("LSDS Final Q1 T1 PermAll Test ScanStudents.pdf", 10, 4, "Final", 34),
    ("LSDS Final Q2 T1 PermAll Test ScanStudents.pdf", 10, 4, "Final", 22),
    ("LSDS Final Q3 T1 PermAll Test ScanStudents.pdf", 10, 4, "Final", 52),
    ("LSDS MT Q2 T1 PermAll Test ScanStudents.pdf", 10, 4, "Midterm", 60),
    ("LSDS Retake TAll PermAll Test ScanSudents.pdf", 30, 4, "Retake", 11),
]

# The Retake exam has real matching roster/answer-key files in the project
# root (private, gitignored); reuse them instead of synthetic ones purely
# so this doubles as a sanity check against real grading data too.
REAL_STUDENTS = os.path.join(PROJECT_ROOT, "courseid_91223_participants.csv")
REAL_ANSWERS = os.path.join(PROJECT_ROOT, "LSDS_Retake2026_PermALL_Fixed.csv")


def _make_synthetic_students(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("Nom,Cognom1,Cognom2,U_number\n")
        f.write("Synthetic,Student,One,U000001\n")


def _make_synthetic_answer_key(path, num_questions, num_options):
    opts = "ABCDE"[:num_options]
    lines = ["Perm,QuestionNum," + ",".join(opts)]
    for q in range(1, num_questions + 1):
        row = ["1", str(q)] + ["1" if i == 0 else "0" for i in range(num_options)]
        lines.append(",".join(row))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _available_exams():
    """Only include exams whose PDF actually exists on this machine --
    keeps the parametrized test list itself skip-safe rather than failing
    to collect when testing_dataset/ is absent."""
    return [e for e in EXAMS if os.path.exists(os.path.join(TESTING_DATASET_DIR, e[0]))]


@pytest.mark.skipif(not _available_exams(), reason="testing_dataset/ PDFs not present (gitignored)")
@pytest.mark.parametrize("pdf_name,num_questions,num_options,exam_type,page_count", _available_exams())
def test_packaged_exe_full_lifecycle_exits_cleanly(
        request, tmp_path, pdf_name, num_questions, num_options, exam_type, page_count):
    exe_path = request.config.getoption("--packaged-exe")
    if not exe_path:
        pytest.skip(
            "no --packaged-exe path given -- build one first (see "
            "TEST_SUITE.md's packaged-exe smoke test section) and pass "
            "its path, e.g.:\n"
            "  pytest -m packaging tests/test_stability_packaged_exe.py "
            '--packaged-exe "<sandbox>\\dist\\e2e_driver\\e2e_driver.exe"'
        )
    if not os.path.exists(exe_path):
        pytest.fail(f"--packaged-exe path does not exist: {exe_path}")

    pdf_path = os.path.join(TESTING_DATASET_DIR, pdf_name)
    output_dir = str(tmp_path / "e2e_output")

    if pdf_name.startswith("LSDS Retake") and os.path.exists(REAL_STUDENTS) and os.path.exists(REAL_ANSWERS):
        students_path, answers_path = REAL_STUDENTS, REAL_ANSWERS
    else:
        students_path = str(tmp_path / "synthetic_students.csv")
        answers_path = str(tmp_path / "synthetic_answers.csv")
        _make_synthetic_students(students_path)
        _make_synthetic_answer_key(answers_path, num_questions, num_options)

    driver_timeout_s = max(180, page_count * 6)  # generous margin: cold-start + render + OCR per page

    proc = subprocess.run(
        [exe_path, pdf_path, students_path, answers_path, output_dir,
         str(num_questions), str(num_options), exam_type, str(driver_timeout_s)],
        capture_output=True, text=True, timeout=driver_timeout_s + 60,
    )

    if proc.returncode != 0:
        pytest.fail(
            f"packaged exe exited with code {proc.returncode} for {pdf_name} "
            f"(driver_timeout_s={driver_timeout_s})\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}\n"
        )

    assert "DRIVER: closing" in proc.stdout
    assert os.path.exists(os.path.join(output_dir, "results.xlsx"))
    assert os.path.exists(os.path.join(output_dir, "annotated_review.pdf"))
