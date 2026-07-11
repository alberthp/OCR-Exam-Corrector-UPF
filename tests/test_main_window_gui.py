"""gui/main_window.py: closeEvent must block closing while a background
save or preview render is still in flight.

Regression test for a confirmed native crash (STATUS_STACK_BUFFER_OVERRUN,
not a catchable Python exception) found during the v1.4 stress-testing
pass: nothing previously waited for review_screen's background QThreads
before the process could exit, and for a save specifically, the same
abrupt exit risked leaving results.xlsx/annotated_review.pdf mid-write.
"""

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def main_window(qapp):
    from gui.main_window import MainWindow
    window = MainWindow()
    yield window
    # Drain out any state the test set so the fixture teardown itself
    # doesn't hit the same in-flight-thread hazard closeEvent guards against.
    window.review_screen._local_busy = False
    window.review_screen._pending_sync_workers = []
    window.review_screen._pending_preview_workers = []


def test_close_allowed_when_idle(main_window):
    from PySide6.QtGui import QCloseEvent
    event = QCloseEvent()
    main_window.closeEvent(event)
    assert event.isAccepted()


def test_close_blocked_while_local_busy(main_window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QCloseEvent

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(1))

    main_window.review_screen._local_busy = True
    event = QCloseEvent()
    main_window.closeEvent(event)

    assert not event.isAccepted()
    assert shown  # user was told why


def test_close_blocked_while_sync_worker_pending(main_window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QCloseEvent

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    main_window.review_screen._pending_sync_workers = [object()]  # sentinel, never run

    event = QCloseEvent()
    main_window.closeEvent(event)
    assert not event.isAccepted()


def test_close_blocked_while_preview_worker_pending(main_window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtGui import QCloseEvent

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    main_window.review_screen._pending_preview_workers = [object()]

    event = QCloseEvent()
    main_window.closeEvent(event)
    assert not event.isAccepted()
