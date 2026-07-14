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

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

# Deliberately NOT "from gui.main_window import MainWindow" here at module
# level -- that one import statement transitively pulls in cv2, numpy,
# pandas, scipy, pdf2image, reportlab, and openpyxl, which on a fresh
# machine (cold disk cache, antivirus/EDR deep-scanning an unfamiliar
# multi-DLL executable the first time) can take a long while. Doing that
# before QApplication/the splash even exist means the app can look dead --
# no window, nothing in the taskbar -- for however long that takes. See
# gui/startup_splash.py and gui/app_info.py's docstrings for the rest of
# why this is split out like this.


class _StartupImportWorker(QThread):
    """Runs the slow *non-GUI* library imports off the main thread.

    A plain sequence of `import` calls on the main thread -- even split
    into stages with processEvents() between them -- still leaves the
    window frozen (and liable to be marked "(Not Responding)" by Windows)
    for however long any *single* import call blocks, since nothing pumps
    the event loop *during* one. Running them here instead means the main
    thread's event loop never stops running, so the splash stays
    genuinely responsive the whole time, not just between stages.

    Deliberately does NOT import gui.main_window (or anything else that
    touches PySide6.QtWidgets) here, even though that's pure class
    *definitions*, not widget construction. An earlier version of this
    code did exactly that reasoning it was safe -- it wasn't: two packaged
    (.exe) crashes in the wild both faulted in Qt6Core.dll at the same
    offset, well after startup had already finished (mid-scan, mid-review),
    consistent with PySide6/Qt doing thread-affinity-sensitive static
    initialization the *first* time one of its submodules is touched --
    if that first touch happens on a worker thread instead of the main
    thread, it can silently corrupt Qt's internal bookkeeping without
    crashing immediately, only to fail unpredictably later. cv2/numpy/
    pandas/scipy/pdf2image/reportlab have no such risk (no Qt dependency
    at all), so only those run here; gui.main_window is imported back on
    the main thread in main()'s _on_done, right before it's instantiated.
    """

    stage = Signal(str)
    done = Signal()
    failed = Signal(str)

    def run(self):
        try:
            self.stage.emit("Loading image processing libraries (cv2, numpy, scipy)...")
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            from scipy import ndimage, signal  # noqa: F401

            self.stage.emit("Loading PDF/Excel libraries...")
            import pandas  # noqa: F401
            import openpyxl  # noqa: F401
            import pdf2image  # noqa: F401
            import reportlab  # noqa: F401

            self.done.emit()
        except Exception as e:
            import traceback
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")


def main():
    app = QApplication(sys.argv)

    from gui.startup_splash import StartupSplash

    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    logo_path = os.path.join(base_dir, 'assets', 'upf_logo.png')
    splash = StartupSplash(logo_path)
    splash.show()
    splash.log("Starting OMR Exam Corrector...")

    # Visible proof the window is alive, not frozen, while a slow import
    # stage is running in the background -- a dot appended once a second
    # to the current line.
    heartbeat = QTimer(splash)
    heartbeat.setInterval(1000)
    heartbeat.timeout.connect(splash.tick)
    heartbeat.start()

    worker = _StartupImportWorker()
    worker.stage.connect(splash.log)

    def _on_done():
        heartbeat.stop()
        splash.log("Loading application...")
        app.processEvents()
        # Imported here, on the main thread, deliberately -- see
        # _StartupImportWorker's docstring for why this specifically must
        # not happen on the worker thread.
        from gui.main_window import MainWindow

        splash.log("Building interface...")
        app.processEvents()
        # Parented to `app` so the reference survives after this closure
        # returns -- otherwise nothing else in main() holds onto it and it
        # would be garbage-collected out from under the running window.
        app.main_window = MainWindow()
        splash.log("Ready.")
        app.main_window.show()
        splash.close()

    def _on_failed(message):
        heartbeat.stop()
        splash.log("Failed to start:")
        splash.log(message)

    worker.done.connect(_on_done)
    worker.failed.connect(_on_failed)
    worker.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
