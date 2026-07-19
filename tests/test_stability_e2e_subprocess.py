"""End-to-end process-level stability tests.

Two different techniques, both aimed at what unit/GUI tests structurally
cannot catch:

1. A real subprocess launch of the actual app (New Exam -> scan -> Review
   -> navigate -> close), asserting a clean exit code. This is the only
   test technique that can catch a *native* crash (the v1.6 Qt6Core
   STATUS_STACK_BUFFER_OVERRUN) -- those bypass Python's exception
   handling entirely and would just kill an in-process pytest worker along
   with the test, so the crash has to happen in a child process pytest can
   observe the exit code of instead. Mirrors the manual reproduction
   script written (and discarded) for the v1.7 stability fix, promoted to
   permanent coverage.

2. A fast, in-process repeatability regression: process the same real page
   twice and assert identical output. A permanent, cheap version of the
   manual 5-file/3-iteration determinism check already run by hand this
   session against the full testing_dataset/.

Both skip themselves cleanly when the real data they need isn't present
(gitignored, private -- see .gitignore), same pattern as
test_integration_real_data.py.
"""

import os
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTING_DATASET_DIR = os.path.join(PROJECT_ROOT, "testing_dataset")
E2E_PDF = os.path.join(TESTING_DATASET_DIR, "LSDS Retake TAll PermAll Test ScanSudents.pdf")
E2E_STUDENTS = os.path.join(PROJECT_ROOT, "courseid_91223_participants.csv")
E2E_ANSWERS = os.path.join(PROJECT_ROOT, "LSDS_Retake2026_PermALL_Fixed.csv")

skip_no_e2e_files = pytest.mark.skipif(
    not (os.path.exists(E2E_PDF) and os.path.exists(E2E_STUDENTS) and os.path.exists(E2E_ANSWERS)),
    reason="real testing_dataset PDF/roster/answer-key not present (gitignored)",
)


def _grep_recent_application_errors(process_name="python", within_seconds=300):
    """On Windows, check the Application Event Log for a native crash
    (e.g. Application Error / .NET Runtime) from the last few minutes,
    naming the failing module. Best-effort: returns '' if unavailable or
    nothing found, never raises -- this is a diagnostic aid for a failure
    that already happened, not something the test depends on to pass.
    """
    if sys.platform != "win32":
        return ""
    try:
        ps_cmd = (
            f"Get-WinEvent -FilterHashtable @{{LogName='Application'; "
            f"ProviderName='Application Error'; StartTime=(Get-Date).AddSeconds(-{within_seconds})}} "
            f"-ErrorAction SilentlyContinue | Select-Object -First 3 -ExpandProperty Message"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip()
    except Exception:
        return ""


@skip_no_e2e_files
def test_full_app_lifecycle_subprocess_exits_cleanly(tmp_path):
    driver = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_e2e_driver.py")
    output_dir = str(tmp_path / "e2e_output")

    proc = subprocess.run(
        [sys.executable, driver, E2E_PDF, E2E_STUDENTS, E2E_ANSWERS, output_dir],
        capture_output=True, text=True, timeout=240,
        cwd=PROJECT_ROOT,
    )

    if proc.returncode != 0:
        event_log = _grep_recent_application_errors()
        failure_detail = (
            f"driver exited with code {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}\n"
        )
        if event_log:
            failure_detail += f"--- recent Application Error event log ---\n{event_log}\n"
        pytest.fail(failure_detail)

    assert "DRIVER: closing" in proc.stdout
    assert os.path.exists(os.path.join(output_dir, "results.xlsx"))
    assert os.path.exists(os.path.join(output_dir, "annotated_review.pdf"))


@skip_no_e2e_files
def test_processing_same_page_twice_gives_identical_result():
    """Fast, in-process determinism check -- the permanent version of the
    manual 5-file/3-iteration comparison already run against the full
    testing_dataset/ this session (which found zero differences across
    537 page-scans). This keeps a cheap regression guard for that property
    without paying the full multi-file/multi-iteration cost on every run.
    """
    import omr_correct as omr
    from pdf2image import convert_from_path

    dpi = omr.detect_pdf_dpi(E2E_PDF)
    pages = convert_from_path(E2E_PDF, dpi=dpi, first_page=1, last_page=1)
    page = pages[0]

    result_a, _ = omr.process_page(page, 1, num_questions=30, num_options=4, source_dpi=dpi)
    result_b, _ = omr.process_page(page, 1, num_questions=30, num_options=4, source_dpi=dpi)

    def comparable(r):
        return {
            "status": r.get("status"),
            "dni": r.get("dni"),
            "u_number": r.get("u_number"),
            "grup": r.get("grup"),
            "parcial": r.get("parcial"),
            "permut": r.get("permut"),
            "answers": {k: sorted(v.get("marks", [])) for k, v in r.get("answers", {}).items()},
        }

    assert comparable(result_a) == comparable(result_b)


@skip_no_e2e_files
def test_repeated_processing_does_not_leak_memory():
    """Memory-growth regression guard using stdlib tracemalloc (no new
    dependency). Processes the same real page 20 times, discarding each
    result immediately, and asserts traced Python-heap memory after
    warmup stays roughly flat rather than growing unboundedly -- the
    signature of a real leak (e.g. a module-level cache or list someone
    forgot to clear) as opposed to normal one-time allocation.

    Not a substitute for a profiler if this ever fails: it's a coarse
    tripwire sized to catch an actual leak (which grows without bound)
    without being flaky over a generous tolerance for legitimate
    per-call allocation.
    """
    import gc
    import tracemalloc

    import omr_correct as omr
    from pdf2image import convert_from_path

    dpi = omr.detect_pdf_dpi(E2E_PDF)
    pages = convert_from_path(E2E_PDF, dpi=dpi, first_page=1, last_page=1)
    page = pages[0]

    # Warm up: first call may allocate one-time caches (e.g. cv2 internals).
    omr.process_page(page, 1, num_questions=30, num_options=4, source_dpi=dpi)
    gc.collect()

    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()

    for _ in range(20):
        result, corrected = omr.process_page(page, 1, num_questions=30, num_options=4, source_dpi=dpi)
        del result, corrected

    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    growth_mb = (current - baseline) / (1024 * 1024)
    assert growth_mb < 50, (
        f"Traced Python-heap memory grew by {growth_mb:.1f}MB over 20 repeated "
        f"process_page() calls on the same page -- looks like a leak, not normal "
        f"per-call allocation (peak during the run was {peak / (1024*1024):.1f}MB)."
    )
