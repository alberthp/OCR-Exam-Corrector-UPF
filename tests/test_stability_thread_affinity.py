"""Static regression guard for the v1.6 native crash class: touching
PySide6.QtWidgets (or any gui.* module that itself pulls in QtWidgets)
from inside a QThread.run() body.

Root cause (see omr_gui.py's _StartupImportWorker docstring): PySide6/Qt
does thread-affinity-sensitive static initialization the *first* time one
of its submodules is touched. If that first touch happens on a worker
thread instead of the main thread, it can silently corrupt Qt's internal
bookkeeping without crashing immediately -- the packaged .exe crashed
later, mid-scan or mid-review, with a Qt6Core.dll STATUS_STACK_BUFFER_OVERRUN
that gave no indication the actual mistake was an import at startup. This
test turns "Qt widget construction must happen on the main thread" from a
docstring warning on one file into an enforced rule checked against every
QThread subclass in the app, so this exact mistake can't silently
reappear in a different worker later.

Deliberately static (source/AST inspection, no qapp needed): the whole
point is to catch the mistake before a worker thread ever runs, not to
prove today's specific instance is fine -- proving that is what the actual
crash-fix reproduction covered.
"""

import ast
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORKER_FILES = [
    "omr_gui.py",
    os.path.join("gui", "new_exam_screen.py"),
    os.path.join("gui", "review_screen.py"),
    os.path.join("gui", "email_dialogs.py"),
]

# Anything under these is unsafe to first-touch off the main thread.
UNSAFE_PREFIXES = ("PySide6.QtWidgets", "gui.main_window", "gui.new_exam_screen",
                    "gui.review_screen", "gui.start_screen", "gui.email_dialogs",
                    "gui.startup_splash")


def _find_qthread_subclass_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
                if base_name == "QThread":
                    names.add(node.name)
    return names


def _find_run_methods_in_qthread_subclasses(tree):
    """Yield the AST body of every run(self) method defined directly on a
    class that inherits from QThread."""
    qthread_classes = _find_qthread_subclass_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in qthread_classes:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "run":
                    yield node.name, item


def _imported_names(func_node):
    """All module names referenced by import/from-import statements
    anywhere in this function body (including nested try/except/if)."""
    names = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_qthread_run_method_imports_qtwidgets_or_gui_modules():
    violations = []
    for rel_path in WORKER_FILES:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        with open(full_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=rel_path)

        for class_name, run_node in _find_run_methods_in_qthread_subclasses(tree):
            for imported in _imported_names(run_node):
                if any(imported == prefix or imported.startswith(prefix + ".")
                       for prefix in UNSAFE_PREFIXES):
                    violations.append(f"{rel_path}: {class_name}.run() imports '{imported}'")

    assert violations == [], (
        "QThread.run() body imports a GUI-widget-touching module -- this is "
        "the exact mistake that caused the v1.6 native crash (Qt thread-"
        "affinity corruption from first-touching PySide6.QtWidgets off the "
        "main thread). Move the import to the main thread instead:\n  "
        + "\n  ".join(violations)
    )


def test_worker_files_actually_contain_at_least_one_qthread_subclass():
    """Sanity check on the test itself: if this app's worker files ever get
    restructured such that none of WORKER_FILES contain a QThread subclass
    anymore, the test above would trivially and silently pass with nothing
    to check. Fails loudly instead so WORKER_FILES gets updated.
    """
    total = 0
    for rel_path in WORKER_FILES:
        full_path = os.path.join(PROJECT_ROOT, rel_path)
        with open(full_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=rel_path)
        total += len(_find_qthread_subclass_names(tree))
    assert total >= 6, (
        f"Expected at least 6 QThread subclasses across {WORKER_FILES}, found {total}. "
        "If worker classes moved to a new file, add it to WORKER_FILES above."
    )
