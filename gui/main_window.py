"""Top-level window: a QStackedWidget hosting the start/new-exam/review screens.

Navigation is signal-driven: each child screen emits a signal when it wants
to switch to another screen, and MainWindow wires those signals to
QStackedWidget.setCurrentWidget() calls.  No child screen needs to know
about the others.
"""

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from gui.start_screen import StartScreen
from gui.new_exam_screen import NewExamScreen
from gui.review_screen import ReviewScreen


class MainWindow(QMainWindow):
    """Application shell.  Owns the three screens and the navigation between them."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OMR Exam Corrector")
        self.resize(1300, 850)

        self.start_screen = StartScreen()
        self.new_exam_screen = NewExamScreen()
        self.review_screen = ReviewScreen()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.new_exam_screen)
        self.stack.addWidget(self.review_screen)
        self.setCentralWidget(self.stack)

        # Start → New exam
        self.start_screen.new_exam_requested.connect(
            lambda: self.stack.setCurrentWidget(self.new_exam_screen))
        # Start → Review (loading a saved review_cache.pkl)
        self.start_screen.review_requested.connect(self._go_to_review)
        self.start_screen.exit_requested.connect(self.close)

        # New exam → Start (cancel)
        self.new_exam_screen.back_requested.connect(
            lambda: self.stack.setCurrentWidget(self.start_screen))
        # New exam → Review (pipeline finished successfully)
        self.new_exam_screen.finished_run.connect(self._go_to_review)

        # Review → Start
        self.review_screen.back_requested.connect(
            lambda: self.stack.setCurrentWidget(self.start_screen))

        self.stack.setCurrentWidget(self.start_screen)

    def _go_to_review(self, run_state):
        """Load run_state into the review screen and switch to it.

        Called both after a fresh OMR run (run_state built by AnalysisWorker)
        and when reopening a saved session (run_state loaded from review_cache.pkl).
        """
        self.review_screen.load(run_state)
        self.stack.setCurrentWidget(self.review_screen)

    def closeEvent(self, event):
        """Block closing while a save, preview render, or exam scan is still in flight.

        Nothing previously waited for review_screen's background QThreads
        (_SaveWorker / _PreviewRenderWorker) before the process could exit.
        Confirmed by testing: closing mid-render can hard-crash the process
        (a native STATUS_STACK_BUFFER_OVERRUN, not a catchable Python
        exception) -- and for a save specifically, that same abrupt exit
        happens while results.xlsx/annotated_review.pdf may be mid-write,
        risking a corrupted output file, not just a crash. Simplest safe
        fix: refuse to close while any of that is running and say so: these
        operations normally finish in well under a second (a save) to a
        few seconds (a page render), so asking the user to try again a
        moment later is a minor inconvenience next to the alternative.

        new_exam_screen's AnalysisWorker is the same shape of hazard (a
        live QThread the window doesn't otherwise wait for) and was
        missing from this guard entirely -- a stability test driving a
        real running AnalysisWorker confirmed closing was never blocked
        during a scan, until this check was added.
        """
        rs = self.review_screen
        busy = rs._local_busy or bool(rs._pending_sync_workers) or bool(rs._pending_preview_workers)
        scan_worker = getattr(self.new_exam_screen, 'worker', None)
        scanning = scan_worker is not None and scan_worker.isRunning()
        if busy or scanning:
            QMessageBox.information(
                self, "Please wait",
                "A save, preview render, or exam scan is still finishing. "
                "Please wait a moment and try closing again.")
            event.ignore()
            return
        event.accept()
