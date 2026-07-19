"""Real-thread lifecycle tests: drive the app's actual QThread workers
(not mocked busy-flags) through start / close-during-busy / rapid-restart /
exception-in-run, on a real qapp event loop.

test_main_window_gui.py already proves closeEvent's *logic* is correct
given a busy flag; these tests prove the busy flags themselves get set and
cleared correctly by a real running thread, and specifically probe the
same "closing while a background QThread is alive risks a native crash"
hazard (see MainWindow.closeEvent's docstring, and the confirmed
STATUS_STACK_BUFFER_OVERRUN crash from the v1.4 stress-testing pass) for
paths that hazard hasn't been checked against before.
"""

import sys
import time

import pytest
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.gui


def _pump_until(condition_fn, timeout=5.0, interval=0.02):
    """Process the Qt event loop until condition_fn() is true or timeout.

    Cross-thread Qt signals only get delivered to the main thread when its
    event loop runs, so a plain `while not done: time.sleep(x)` would never
    see a worker's signal arrive. Returns whether the condition was met.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition_fn():
            return True
        time.sleep(interval)
    QApplication.processEvents()
    return condition_fn()


# ===== A minimal, generic slow/failing QThread double =====
# Exercises the same start/finished/failed contract every real worker in
# this app follows, without needing real files or a real OCR pass -- the
# property under test is Qt thread lifecycle behaviour, not business logic.

class _SlowWorker(QThread):
    done = Signal(str)  # '' on success, error message on failure

    def __init__(self, duration=0.3, should_fail=False):
        super().__init__()
        self.duration = duration
        self.should_fail = should_fail

    def run(self):
        time.sleep(self.duration)
        if self.should_fail:
            try:
                raise RuntimeError("synthetic worker failure")
            except RuntimeError as e:
                self.done.emit(str(e))
                return
        self.done.emit('')


def test_slow_worker_isRunning_true_during_and_false_after(qapp):
    worker = _SlowWorker(duration=0.3)
    worker.start()
    assert worker.isRunning()
    assert _pump_until(lambda: worker.isFinished(), timeout=5.0)
    assert not worker.isRunning()


def test_slow_worker_failure_still_reaches_finished_no_zombie_thread(qapp):
    worker = _SlowWorker(duration=0.1, should_fail=True)
    results = []
    worker.done.connect(lambda msg: results.append(msg))
    worker.start()
    assert _pump_until(lambda: worker.isFinished(), timeout=5.0)
    assert results == ["synthetic worker failure"]
    assert not worker.isRunning()


def test_rapid_restart_second_worker_does_not_interfere_with_first(qapp):
    # Simulates two independent worker instances started back-to-back
    # (e.g. a double-click before the button-disable takes effect) --
    # proves they don't corrupt each other's completion signal.
    results = []
    w1 = _SlowWorker(duration=0.2)
    w2 = _SlowWorker(duration=0.05)
    w1.done.connect(lambda msg, tag="w1": results.append(tag))
    w2.done.connect(lambda msg, tag="w2": results.append(tag))
    w1.start()
    w2.start()
    assert _pump_until(lambda: w1.isFinished() and w2.isFinished(), timeout=5.0)
    assert set(results) == {"w1", "w2"}


# ===== Real AnalysisWorker driven end-to-end against a real MainWindow =====

@pytest.fixture
def main_window(qapp):
    from gui.main_window import MainWindow
    window = MainWindow()
    yield window
    # Drain any state so teardown doesn't hit the same in-flight-thread
    # hazard closeEvent guards against (same pattern as test_main_window_gui.py).
    window.review_screen._local_busy = False
    window.review_screen._pending_sync_workers = []
    window.review_screen._pending_preview_workers = []
    worker = getattr(window.new_exam_screen, "worker", None)
    if worker is not None and worker.isRunning():
        worker.wait(5000)


@pytest.fixture
def fast_analysis_worker(monkeypatch):
    """Monkeypatch AnalysisWorker's dependencies (inside gui.new_exam_screen's
    namespace, where they're imported) so run() completes in a controlled,
    short amount of time without touching real files or the real OCR
    pipeline -- the property under test is thread lifecycle, not OCR
    correctness (already covered elsewhere).
    """
    import pandas as pd
    import gui.new_exam_screen as nes

    students_df = pd.DataFrame({
        "Nom": ["Alice"], "Cognom1": ["Example"], "Cognom2": ["Smith"],
        "U_number": ["U000001"],
    })

    def slow_convert_from_path(*a, **k):
        time.sleep(0.4)
        return [object()]  # one fake "page"

    monkeypatch.setattr(nes.omr, "load_students", lambda path: students_df)
    monkeypatch.setattr(nes.omr, "load_correct_answers", lambda path: {"1": {1: {"A"}}})
    monkeypatch.setattr(nes, "convert_from_path", slow_convert_from_path)
    monkeypatch.setattr(nes.omr, "process_page",
                         lambda page, num, nq, no, source_dpi: ({"page": num, "status": "OK"}, None))
    monkeypatch.setattr(nes.omr, "backfill_and_validate_groups", lambda *a, **k: None)
    monkeypatch.setattr(nes.omr, "write_excel", lambda *a, **k: None)
    monkeypatch.setattr(nes.omr, "write_annotated_pdf", lambda *a, **k: None)
    monkeypatch.setattr(nes.omr, "save_review_cache", lambda *a, **k: None)
    return nes


def _start_real_scan(main_window, fast_analysis_worker, output_dir):
    from gui.new_exam_screen import AnalysisWorker
    worker = AnalysisWorker(
        "fake.pdf", "fake_students.csv", "fake_answers.csv",
        10, 4, str(output_dir), 300, exam_type="Final",
    )
    main_window.new_exam_screen.worker = worker
    worker.start()
    return worker


def test_real_analysis_worker_completes_and_emits_finished_ok(
        qapp, main_window, fast_analysis_worker, tmp_path):
    results = {}
    worker = _start_real_scan(main_window, fast_analysis_worker, tmp_path)
    worker.finished_ok.connect(lambda summary: results.update(summary))
    assert worker.isRunning()
    assert _pump_until(lambda: worker.isFinished(), timeout=5.0)
    assert results.get("total_pages") == 1
    assert not worker.isRunning()


def test_closing_main_window_while_scan_is_running_does_not_destroy_a_live_thread(
        qapp, main_window, fast_analysis_worker, tmp_path, monkeypatch):
    """Stability regression test.

    MainWindow.closeEvent() blocks closing while review_screen has a save
    or preview render in flight (see test_main_window_gui.py) -- that guard
    was added after a confirmed native crash from closing mid-render.
    new_exam_screen's scan worker is the same shape of hazard (a live
    QThread the window doesn't wait for) but was never wired into the same
    guard. This test drives a real, running AnalysisWorker and confirms
    the window will not let a close event destroy it out from under a live
    thread -- accepting a close while `worker.isRunning()` is True would
    surface this as a real gap, not just a theoretical one.
    """
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    worker = _start_real_scan(main_window, fast_analysis_worker, tmp_path)
    assert worker.isRunning()

    event = QCloseEvent()
    main_window.closeEvent(event)

    assert not event.isAccepted(), (
        "closeEvent accepted a close while a scan worker was still running -- "
        "this can destroy a live QThread mid-run, the same hazard that caused "
        "the confirmed native crash review_screen's busy-guard exists to prevent."
    )

    assert _pump_until(lambda: worker.isFinished(), timeout=5.0)

    # Once the worker has actually finished, closing must be allowed again.
    event2 = QCloseEvent()
    main_window.closeEvent(event2)
    assert event2.isAccepted()


def test_back_button_blocked_while_scan_is_running(
        qapp, main_window, fast_analysis_worker, tmp_path, monkeypatch):
    """Regression test for the sibling gap found alongside the close-guard
    bug: clicking "Back to start" while a scan is running used to switch
    the visible screen immediately while the AnalysisWorker kept running
    unattended in the background, then forced a jump to Review once it
    finished regardless of where the user had navigated to since --
    confirmed live via a manual repro before this guard was added.
    """
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    back_fired = []
    main_window.new_exam_screen.back_requested.connect(lambda: back_fired.append(1))

    worker = _start_real_scan(main_window, fast_analysis_worker, tmp_path)
    assert worker.isRunning()

    main_window.new_exam_screen._on_back_clicked()
    assert back_fired == [], "back_requested fired while the scan worker was still running"

    assert _pump_until(lambda: worker.isFinished(), timeout=5.0)

    main_window.new_exam_screen._on_back_clicked()
    assert back_fired == [1], "back navigation should be allowed once the scan has finished"


@pytest.mark.skipif(sys.platform != "win32", reason="msvcrt file locking is Windows-only")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_real_analysis_worker_locked_excel_output_emits_failed_not_crash(
        qapp, main_window, monkeypatch, tmp_path):
    """Regression test for a real environment hazard specific to this app:
    results.xlsx open in Excel (locked for writing) when the user re-runs
    a scan. Confirms the existing top-level try/except in
    AnalysisWorker.run() actually catches that failure and emits `failed`
    with a clear message rather than crashing or hanging. The pure
    write_excel()-level version of this same scenario lives in
    test_stability_malformed_input.py::test_write_excel_to_locked_file_raises_cleanly;
    this is the real-worker, real-thread confirmation that the failure
    actually propagates through the full pipeline safely.
    """
    import msvcrt
    import openpyxl
    import pandas as pd
    import gui.new_exam_screen as nes

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    excel_path = output_dir / "results.xlsx"
    openpyxl.Workbook().save(str(excel_path))

    students_df = pd.DataFrame({
        "Nom": ["Alice"], "Cognom1": ["Example"], "Cognom2": ["Smith"],
        "U_number": ["U000001"],
    })
    monkeypatch.setattr(nes.omr, "load_students", lambda path: students_df)
    monkeypatch.setattr(nes.omr, "load_correct_answers", lambda path: {"1": {1: {"A"}}})
    monkeypatch.setattr(nes, "convert_from_path", lambda *a, **k: [object()])
    monkeypatch.setattr(nes.omr, "process_page",
                         lambda page, num, nq, no, source_dpi: ({"page": num, "status": "OK"}, None))
    monkeypatch.setattr(nes.omr, "backfill_and_validate_groups", lambda *a, **k: None)
    # write_excel is deliberately left real -- it's the failure point under test.

    f = open(excel_path, "r+b")
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        from gui.new_exam_screen import AnalysisWorker
        worker = AnalysisWorker(
            "fake.pdf", "fake_students.csv", "fake_answers.csv",
            10, 4, str(output_dir), 300, exam_type="Final",
        )
        main_window.new_exam_screen.worker = worker
        failures = []
        worker.failed.connect(lambda msg: failures.append(msg))
        worker.start()
        assert _pump_until(lambda: worker.isFinished(), timeout=5.0)
    finally:
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        f.close()

    assert not worker.isRunning()
    assert len(failures) == 1
    assert "permission" in failures[0].lower()
