"""Top-level window: a QStackedWidget hosting the start/new-exam/review screens."""

from PySide6.QtWidgets import QMainWindow, QStackedWidget

from gui.start_screen import StartScreen
from gui.new_exam_screen import NewExamScreen
from gui.review_screen import ReviewScreen


class MainWindow(QMainWindow):
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

        self.start_screen.new_exam_requested.connect(
            lambda: self.stack.setCurrentWidget(self.new_exam_screen))
        self.start_screen.review_requested.connect(self._go_to_review)
        self.start_screen.exit_requested.connect(self.close)

        self.new_exam_screen.back_requested.connect(
            lambda: self.stack.setCurrentWidget(self.start_screen))
        self.new_exam_screen.finished_run.connect(self._go_to_review)

        self.review_screen.back_requested.connect(
            lambda: self.stack.setCurrentWidget(self.start_screen))

        self.stack.setCurrentWidget(self.start_screen)

    def _go_to_review(self, run_state):
        self.review_screen.load(run_state)
        self.stack.setCurrentWidget(self.review_screen)
