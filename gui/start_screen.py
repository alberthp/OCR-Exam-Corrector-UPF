"""Landing screen: choose between evaluating a new exam or reviewing existing results."""

import os
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox,
)

import omr_correct as omr
from gui.app_info import APP_VERSION, APP_AUTHOR, APP_EMAIL

# sys._MEIPASS is set by PyInstaller to the bundle's extraction directory at
# runtime (both --onefile and --onedir); it's absent when running from source,
# so we fall back to the project root two levels above this file.
_PROJECT_ROOT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGO_PATH = os.path.join(_PROJECT_ROOT, 'assets', 'upf_logo.png')


class StartScreen(QWidget):
    """First screen the user sees: evaluate a new exam, or review/edit a past run."""

    new_exam_requested = Signal()
    review_requested = Signal(dict)  # emits the run_state dict loaded from review_cache.pkl
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
            # Modest fixed height; the logo is wide and designed for dark backgrounds.
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
        """Scale a widget's font by factor, handling both point-size and pixel-size fonts."""
        font = widget.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * factor)
        else:
            # Some platforms (notably some Linux themes) report fonts in pixel size.
            font.setPixelSize(max(1, round(font.pixelSize() * factor)))
        widget.setFont(font)

    def _open_previous_results(self):
        """Open a file dialog to pick a review_cache.pkl from a previous session."""
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
        # The cache stores only filenames for excel/pdf (so it survives the
        # output folder being renamed), but they must still live next to it.
        if not os.path.exists(run_state['excel_path']) or not os.path.exists(run_state['pdf_path']):
            QMessageBox.warning(
                self, "Missing files",
                "results.xlsx and/or annotated_review.pdf were not found next to "
                "the selected review_cache.pkl. Make sure all three files are "
                "still together in the same folder.")
            return
        self.review_requested.emit(run_state)
