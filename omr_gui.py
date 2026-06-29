#!/usr/bin/env python3
"""
OMR Exam Corrector - Desktop GUI (PySide6)
===========================================

Loads a scanned exam PDF, a students list, and an answers file (with
permutations), runs the OMR pipeline from omr_correct.py in a background
thread, and shows live per-page progress while it runs. Once done, switches
straight into review mode to fix any mismatches.

Usage:
    python omr_gui.py
"""

import os
import sys


def _add_bundled_poppler_to_path():
    """Make the bundled poppler binaries (pdftoppm/pdfinfo/pdfimages, see
    poppler_bin/) discoverable via PATH -- pdf2image and
    omr_correct.detect_pdf_dpi() both expect to just find these by name.

    Without this, the packaged .exe would only work on a machine that
    happens to already have poppler installed and on PATH. getattr(sys,
    '_MEIPASS', ...) is how PyInstaller exposes the bundle's root directory
    at runtime (both --onefile and --onedir); it's absent when running from
    source, where this resolves to the project folder instead -- so the
    bundled binaries are used in both cases, not just the packaged build.
    """
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    poppler_dir = os.path.join(base_dir, 'poppler_bin')
    if os.path.isdir(poppler_dir):
        os.environ['PATH'] = poppler_dir + os.pathsep + os.environ.get('PATH', '')


_add_bundled_poppler_to_path()

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
