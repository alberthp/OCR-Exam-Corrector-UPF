"""Startup splash window shown while the slow first-time imports run.

Only PySide6 + gui.app_info -- see gui/app_info.py's docstring for why
that matters here specifically.
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit

from gui.app_info import APP_VERSION, APP_AUTHOR, APP_EMAIL


class StartupSplash(QWidget):
    """Shown from the moment QApplication exists until MainWindow is ready.

    Without this, the first launch of the packaged .exe on a new machine
    (antivirus/EDR deep-scanning an unfamiliar multi-DLL executable, cold
    disk cache for cv2/numpy/pandas/scipy/PySide6) can take a long time
    with *no window at all on screen* -- nothing in the taskbar, nothing
    to tell the user the app isn't just dead. This shows something
    immediately and updates its log as each slow import stage finishes.

    No close/minimize/maximize buttons: this window is meant to close
    itself once startup finishes. If the user could close it early, doing
    so while it's still the only open top-level window would quit the
    whole app via Qt's default quitOnLastWindowClosed -- confusing, since
    from the user's side it looks like clicking X on a splash, not on the
    application itself.
    """

    def __init__(self, logo_path=None):
        super().__init__()
        self.setWindowTitle("OMR Exam Corrector — Starting…")
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.resize(480, 340)

        layout = QVBoxLayout(self)

        if logo_path and os.path.exists(logo_path):
            logo_label = QLabel()
            logo_label.setPixmap(QPixmap(logo_path).scaledToHeight(60, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)

        title = QLabel("OMR Exam Corrector")
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        info = QLabel(f"v{APP_VERSION}  ·  {APP_AUTHOR}  ·  {APP_EMAIL}")
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        info.setStyleSheet("color: #888;")
        layout.addWidget(info)

        subtitle = QLabel(
            "Starting up — first launch on a new machine can take a "
            "while. This window will close automatically."
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, stretch=1)

    def log(self, message):
        self.log_edit.append(message)
        self.log_edit.ensureCursorVisible()

    def tick(self):
        """Appends one '.' to the end of the current line (no new line) --
        a heartbeat so the user can see the window is still alive and
        making progress during a long-running stage, not frozen. Meant to
        be driven by a QTimer on the main thread while the actual slow
        work happens elsewhere (see omr_gui.py's _StartupImportWorker) --
        appending it here alone doesn't keep a window responsive, only a
        genuinely free event loop does.
        """
        cursor = self.log_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(".")
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()
