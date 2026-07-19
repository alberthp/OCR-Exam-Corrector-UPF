"""Crash-resistance tests: feed the pipeline's entry points garbage and
pathological input, and assert a clean failure (a normal return or a
caught exception) rather than a hang or an unhandled crash.

This is a different axis from the rest of the suite: TEST_SUITE.md's
existing coverage targets *correctness* (does a well-formed but tricky
file parse to the right value); these tests target *survival* (does a
malformed or adversarial file bring the process down or wedge it). None
of this needs real student data -- every fixture here is synthetic
garbage generated on the fly.
"""

import concurrent.futures
import os
import sys

import numpy as np
import pytest
from PIL import Image

import omr_correct as omr

CALL_TIMEOUT = 15  # seconds; a hang here is a bug, not a slow-but-fine result


def _call_with_timeout(fn, *args, **kwargs):
    """Run fn in a worker thread with a hard timeout.

    A pathological input (e.g. a crafted image that sends an OpenCV loop
    into a huge iteration count) should fail the test via TimeoutError
    rather than hang the whole suite indefinitely.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn, *args, **kwargs)
        return future.result(timeout=CALL_TIMEOUT)


# ===== process_page(): pathological PIL images =====

def _run_process_page(img, num_questions=10, num_options=4):
    return _call_with_timeout(
        omr.process_page, img, 1, num_questions, num_options, source_dpi=300)


def test_process_page_solid_black_image_does_not_crash():
    img = Image.new("RGB", (2550, 3300), color=(0, 0, 0))
    result, corrected = _run_process_page(img)
    assert result["status"] in ("CORNER_ERROR", "MARKER_ERROR", "EXCEPTION", "OK")


def test_process_page_solid_white_image_does_not_crash():
    img = Image.new("RGB", (2550, 3300), color=(255, 255, 255))
    result, corrected = _run_process_page(img)
    assert result["status"] in ("CORNER_ERROR", "MARKER_ERROR", "EXCEPTION", "OK")


def test_process_page_tiny_1x1_image_does_not_crash():
    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    result, corrected = _run_process_page(img)
    assert result["status"] != "OK"


def test_process_page_extreme_aspect_ratio_does_not_crash():
    # 20px tall, very wide -- nothing resembling a bubble sheet
    img = Image.new("RGB", (5000, 20), color=(255, 255, 255))
    result, corrected = _run_process_page(img)
    assert result["status"] != "OK"


def test_process_page_random_noise_image_does_not_crash():
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, size=(3300, 2550, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    result, corrected = _run_process_page(img)
    assert result["status"] in ("CORNER_ERROR", "MARKER_ERROR", "EXCEPTION", "OK")


def test_process_page_zero_questions_does_not_crash():
    img = Image.new("RGB", (2550, 3300), color=(255, 255, 255))
    result, corrected = _run_process_page(img, num_questions=0)
    assert isinstance(result, dict)


# ===== detect_pdf_dpi(): malformed / missing PDFs =====

def test_detect_pdf_dpi_nonexistent_file_returns_default(tmp_path):
    missing = tmp_path / "does_not_exist.pdf"
    dpi = _call_with_timeout(omr.detect_pdf_dpi, str(missing))
    assert dpi == 300


def test_detect_pdf_dpi_not_actually_a_pdf_returns_default(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"this is not a pdf file, just plain text bytes\x00\x01\x02")
    dpi = _call_with_timeout(omr.detect_pdf_dpi, str(fake))
    assert dpi == 300


def test_detect_pdf_dpi_empty_file_returns_default(tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    dpi = _call_with_timeout(omr.detect_pdf_dpi, str(empty))
    assert dpi == 300


def test_detect_pdf_dpi_truncated_pdf_header_only_returns_default(tmp_path):
    truncated = tmp_path / "truncated.pdf"
    truncated.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")  # header, nothing else
    dpi = _call_with_timeout(omr.detect_pdf_dpi, str(truncated))
    assert dpi == 300


# ===== load_students(): malformed roster files =====

def test_load_students_empty_csv_raises_cleanly(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_students, str(path))


def test_load_students_binary_garbage_csv_raises_cleanly(tmp_path):
    path = tmp_path / "garbage.csv"
    path.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_students, str(path))


def test_load_students_single_column_csv_raises_cleanly(tmp_path):
    path = tmp_path / "single_col.csv"
    path.write_text("just_one_column\nvalue1\nvalue2\n", encoding="utf-8")
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_students, str(path))


def test_load_students_nonexistent_file_raises_cleanly(tmp_path):
    missing = tmp_path / "nope.csv"
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_students, str(missing))


def test_load_students_corrupt_xlsx_raises_cleanly(tmp_path):
    path = tmp_path / "corrupt.xlsx"
    # Valid zip magic bytes but not a real xlsx -- exercises the
    # openpyxl/xlrd error path rather than a plain "file not found".
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_students, str(path))


# ===== load_correct_answers(): malformed answer-key files =====

def test_load_correct_answers_empty_csv_raises_cleanly(tmp_path):
    path = tmp_path / "empty_answers.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_correct_answers, str(path))


def test_load_correct_answers_binary_garbage_raises_cleanly(tmp_path):
    path = tmp_path / "garbage_answers.csv"
    path.write_bytes(os.urandom(500))
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_correct_answers, str(path))


def test_load_correct_answers_nonexistent_file_raises_cleanly(tmp_path):
    missing = tmp_path / "nope_answers.csv"
    with pytest.raises(Exception):
        _call_with_timeout(omr.load_correct_answers, str(missing))


def test_load_correct_answers_missing_required_columns_raises_or_flags(tmp_path):
    path = tmp_path / "wrong_columns.csv"
    path.write_text("Foo,Bar\n1,2\n3,4\n", encoding="utf-8")
    # Either raises, or returns something that isn't a usable answer-key dict.
    try:
        result = _call_with_timeout(omr.load_correct_answers, str(path))
        assert not result
    except Exception:
        pass


# ===== write_excel(): output path locked by another process =====
# A real, realistic environment hazard for this specific app: the user
# has results.xlsx open in Excel (which locks it for writing) and re-runs
# a scan. AnalysisWorker.run() already wraps the whole pipeline in a
# single try/except and emits `failed` rather than crashing (see
# test_stability_threading.py's real-AnalysisWorker version of this same
# scenario) -- this is the pure-function-level confirmation that the
# exception this depends on catching actually happens.

@pytest.fixture
def locked_xlsx_path(tmp_path):
    """A real .xlsx file exclusively locked the same way Excel locks an
    open workbook (a plain open() handle on Windows does NOT block
    another process/handle from rewriting the file -- confirmed by
    testing; an explicit byte-range lock via msvcrt does).
    """
    import openpyxl
    path = tmp_path / "locked_results.xlsx"
    openpyxl.Workbook().save(str(path))

    if sys.platform == "win32":
        import msvcrt
        f = open(path, "r+b")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        yield str(path)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        f.close()
    else:
        import fcntl
        f = open(path, "r+b")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield str(path)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_write_excel_to_locked_file_raises_cleanly(locked_xlsx_path):
    # openpyxl's own abandoned-ZipFile __del__ hits the same lock during
    # garbage collection and logs a PermissionError of its own -- harmless
    # noise from forcing this exact failure mode, not a real issue here.
    with pytest.raises(Exception):
        _call_with_timeout(
            omr.write_excel, [], None, {}, locked_xlsx_path, 10, 4)


# ===== email_utils._config_dir(): the per-user config directory can't be created =====

def test_config_dir_falls_back_when_primary_location_is_not_writable(monkeypatch, tmp_path):
    """Regression test: _config_dir() used to call os.makedirs() with no
    try/except at all, and every caller (opening the Email settings
    dialog, "Send by email") called it with no try/except either --
    confirmed by testing that a makedirs failure raised a raw,
    unhandled PermissionError straight out of those GUI actions, unlike
    the rest of this app's convention of catching risky calls and
    showing a friendly dialog. Now falls back to a directory under the
    system temp folder instead of raising.
    """
    import email_utils as emu

    real_makedirs = os.makedirs

    def fail_for_primary_location_only(path, *a, **k):
        if "OMRExamCorrector" in path and str(tmp_path) not in path:
            raise PermissionError(f"simulated: cannot create {path}")
        return real_makedirs(path, *a, **k)

    monkeypatch.setattr(os, "makedirs", fail_for_primary_location_only)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    resolved = _call_with_timeout(emu._config_dir)
    assert resolved == str(tmp_path / "OMRExamCorrector")
    assert os.path.isdir(resolved)
