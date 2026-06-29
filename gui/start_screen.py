"""Landing screen: choose between evaluating a new exam or reviewing existing results."""

import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox,
)

import omr_correct as omr

# Bump this with each meaningful change to the app.
APP_VERSION = "1.1"
APP_AUTHOR = "Albert Hernansanz (with Claude)"
APP_EMAIL = "albert.hernansanz@upf.edu"

# sys._MEIPASS is where PyInstaller extracts bundled data at runtime (set for
# both --onefile and --onedir); falling back to the source tree when not
# frozen. Project root is two levels up from this file (gui/start_screen.py).
_PROJECT_ROOT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGO_PATH = os.path.join(_PROJECT_ROOT, 'assets', 'upf_logo.png')


class StartScreen(QWidget):
    """First screen the user sees: evaluate a new exam, or review/edit a past run."""

    new_exam_requested = Signal()
    review_requested = Signal(dict)  # run_state, loaded from a review_cache.pkl
    exit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addStretch()

        title = QLabel("OMR Exam Corrector")
        title.setStyleSheet("font-size: 26px; font-weight: 600; color: #aaaaaa;")
        layout.addWidget(title, alignment=Qt.AlignHCenter)

        new_btn = QPushButton("Evaluate new exam...")
        new_btn.setMinimumHeight(64)
        new_btn.setMinimumWidth(420)
        self._bump_font_size(new_btn, 1.5)
        new_btn.clicked.connect(self.new_exam_requested.emit)
        layout.addWidget(new_btn, alignment=Qt.AlignHCenter)

        review_btn = QPushButton("Review / edit existing results...")
        review_btn.setMinimumHeight(64)
        review_btn.setMinimumWidth(420)
        self._bump_font_size(review_btn, 1.5)
        review_btn.clicked.connect(self._open_previous_results)
        layout.addWidget(review_btn, alignment=Qt.AlignHCenter)

        layout.addStretch()

        logo_pixmap = QPixmap(LOGO_PATH)
        if not logo_pixmap.isNull():
            logo_label = QLabel()
            # Modest size: cap the height, scale width to match (logo is wide
            # and white-on-transparent, designed for a dark background).
            scaled = logo_pixmap.scaledToHeight(70, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled)
            logo_label.setContentsMargins(0, 0, 0, 16)
            layout.addWidget(logo_label, alignment=Qt.AlignHCenter)

        footer = QLabel(f"v{APP_VERSION}  -  {APP_AUTHOR}  -  {APP_EMAIL}")
        footer.setStyleSheet("font-size: 11px; color: #888888;")
        layout.addWidget(footer, alignment=Qt.AlignHCenter)

        exit_btn = QPushButton("Exit")
        exit_btn.setMinimumWidth(120)
        exit_btn.clicked.connect(self.exit_requested.emit)
        layout.addWidget(exit_btn, alignment=Qt.AlignHCenter)
        layout.setContentsMargins(0, 0, 0, 16)

    @staticmethod
    def _bump_font_size(widget, factor):
        font = widget.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * factor)
        else:
            # Some platforms report fonts in pixel size instead of points.
            font.setPixelSize(max(1, round(font.pixelSize() * factor)))
        widget.setFont(font)

    def _open_previous_results(self):
        cache_path, _ = QFileDialog.getOpenFileName(
            self, "Select review_cache.pkl from a previous run", "",
            "Review cache (review_cache.pkl);;All files (*)")
        if not cache_path:
            return
        try:
            run_state = omr.load_review_cache(cache_path)
        except Exception as e:
            QMessageBox.critical(self, "Could not open results", str(e))
            return
        if not os.path.exists(run_state['excel_path']) or not os.path.exists(run_state['pdf_path']):
            QMessageBox.warning(
                self, "Missing files",
                "results.xlsx and/or annotated_review.pdf were not found next to "
                "the selected review_cache.pkl. Make sure all three files are "
                "still together in the same folder.")
            return
        self.review_requested.emit(run_state)
