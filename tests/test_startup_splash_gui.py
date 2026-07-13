"""gui/startup_splash.py: the startup splash shown while the slow
first-time imports run in omr_gui.py -- see that module's docstring for
why the imports are staged the way they are.
"""

import pytest

pytestmark = pytest.mark.gui


def test_splash_constructs_without_a_logo_path(qapp):
    from gui.startup_splash import StartupSplash
    splash = StartupSplash(logo_path=None)
    assert "OMR Exam Corrector" in splash.windowTitle()


def test_splash_constructs_with_a_missing_logo_path(qapp):
    """A logo path that doesn't exist (e.g. a stripped-down dev checkout)
    must not crash the splash -- it's meant to reassure the user the app
    is starting, not become one more thing that can fail during startup."""
    from gui.startup_splash import StartupSplash
    splash = StartupSplash(logo_path="Z:/does/not/exist.png")
    assert splash is not None


def test_splash_has_no_close_button(qapp):
    """Closing the splash early (while it's the only open top-level
    window) would quit the whole app via Qt's default
    quitOnLastWindowClosed -- the window must not offer a close button."""
    from PySide6.QtCore import Qt
    from gui.startup_splash import StartupSplash
    splash = StartupSplash(logo_path=None)
    assert not (splash.windowFlags() & Qt.WindowCloseButtonHint)


def test_splash_log_appends_and_is_visible_in_the_text_widget(qapp):
    from gui.startup_splash import StartupSplash
    splash = StartupSplash(logo_path=None)
    splash.log("Loading image processing libraries...")
    splash.log("Loading PDF/Excel libraries...")
    text = splash.log_edit.toPlainText()
    assert "Loading image processing libraries..." in text
    assert "Loading PDF/Excel libraries..." in text


def test_splash_tick_appends_to_the_same_line(qapp):
    """tick() is the once-a-second heartbeat dot -- it must extend the
    current line, not start a new one, or the log would fill up with
    blank-looking lines during a long-running stage."""
    from gui.startup_splash import StartupSplash
    splash = StartupSplash(logo_path=None)
    splash.log("Loading")
    splash.tick()
    splash.tick()
    text = splash.log_edit.toPlainText()
    assert text.rstrip("\n") == "Loading.."
    assert text.count("\n") <= 1


def test_app_info_module_source_has_no_heavy_imports():
    """gui.app_info must be importable without pulling in omr_correct or
    any of its heavy dependencies -- that's the entire point of splitting
    it out of gui.start_screen (see gui/app_info.py's docstring): the
    splash needs the version string *before* those slow imports run.

    Checked via static source inspection rather than diffing sys.modules
    around the import: by the time this test runs, other test files in
    the same pytest process (conftest.py itself imports omr_correct) have
    almost certainly already imported cv2/numpy/pandas/omr_correct, which
    would make a sys.modules-diff check pass regardless of what
    gui.app_info itself imports.
    """
    import gui.app_info
    with open(gui.app_info.__file__, encoding="utf-8") as f:
        import_lines = [
            line for line in f
            if line.strip().startswith(("import ", "from "))
        ]
    assert import_lines == []
