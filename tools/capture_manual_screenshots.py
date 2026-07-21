"""Regenerates the MANUAL.md review-screen screenshots from the synthetic
example in examples/ (scanned_exam_example.pdf + students_standard_example.csv
+ answers_scan_example.csv), driving the real ReviewScreen widget offscreen
(QT_QPA_PLATFORM=offscreen) and grabbing it with QWidget.grab() -- the same
approach used for the screenshots already in assets/screenshots/ (01, 03,
11), just no longer relying on a real (private) exam for the ones that need
a loaded page.

Run from the project root:
    python tools/capture_manual_screenshots.py

Writes into assets/screenshots/:
    01-start-screen.png
    04-review-screen.png
    05-correction-panel.png
    06-expected-overlay.png
    07-legend.png
    08-export-button.png
    09-export-pdf-pages.png
    10-answer-grid-colours.png
"""
import os
import sys
import tempfile

# Deliberately NOT forcing QT_QPA_PLATFORM=offscreen here (unlike the test
# suite's qapp fixture): the offscreen platform plugin doesn't pick up any
# system fonts on Windows, so every label renders as tofu boxes -- useless
# for a screenshot meant to be read. This script is meant to be run
# interactively on a real desktop session, where the default (native)
# platform renders text normally; it will briefly show/steal focus of a
# real window while it runs.

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication, QSplitter, QLabel, QFileDialog
from PIL import Image

import omr_correct as omr

EXAMPLES_DIR = os.path.join(PROJECT_ROOT, "examples")
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "screenshots")


def settle(screen, app):
    """Pump the event loop until any background QThread a save/render
    started has finished -- mirrors tests/test_review_screen_gui.py's
    helper of the same name."""
    for _ in range(200):
        pending = (list(getattr(screen, "_pending_preview_workers", []))
                   + list(getattr(screen, "_pending_sync_workers", [])))
        if not pending:
            break
        for worker in pending:
            worker.wait(5000)
        app.processEvents()
    else:
        raise AssertionError("settle(): workers still pending after 200 iterations")
    for _ in range(20):
        app.processEvents()


def build_run_state(scratch_dir):
    students_df = omr.load_students(os.path.join(EXAMPLES_DIR, "students_standard_example.csv"))
    correct_answers_by_perm = omr.load_correct_answers(os.path.join(EXAMPLES_DIR, "answers_scan_example.csv"))

    exam_pdf = os.path.join(EXAMPLES_DIR, "scanned_exam_example.pdf")
    dpi = omr.detect_pdf_dpi(exam_pdf)
    from pdf2image import convert_from_path
    pages = convert_from_path(exam_pdf, dpi=dpi)

    all_results = []
    for i, page in enumerate(pages):
        r, _ = omr.process_page(page, i + 1, num_questions=20, num_options=4, source_dpi=dpi)
        all_results.append(r)

    omr.backfill_and_validate_groups(all_results, students_df)

    excel_path = os.path.join(scratch_dir, "results.xlsx")
    omr.write_excel(all_results, students_df, correct_answers_by_perm, excel_path, 20, 4)
    pdf_path = os.path.join(scratch_dir, "annotated_review.pdf")
    omr.write_annotated_pdf(all_results, pdf_path, students_df=students_df)
    cache_path = os.path.join(scratch_dir, "review_cache.pkl")
    omr.save_review_cache(all_results, students_df, correct_answers_by_perm, 20, 4,
                           excel_path, pdf_path, cache_path,
                           exam_pdf_path=exam_pdf, dpi=dpi, exam_type="Final")

    return {
        "all_results": all_results,
        "students_df": students_df,
        "correct_answers_by_perm": correct_answers_by_perm,
        "num_questions": 20,
        "num_options": 4,
        "excel_path": excel_path,
        "pdf_path": pdf_path,
        "cache_path": cache_path,
        "exam_pdf": exam_pdf,
        "dpi": dpi,
        "exam_type": "Final",
    }


def grab(widget, path):
    pix = widget.grab()
    pix.save(path)
    _optimize_png(path)
    print("wrote", path, pix.size().toTuple())


def _optimize_png(path):
    im = Image.open(path)
    im.save(path, optimize=True)


def stack_images_vertically(paths, out_path, gap=16, bg=(255, 255, 255)):
    imgs = [Image.open(p) for p in paths]
    width = max(im.width for im in imgs)
    height = sum(im.height for im in imgs) + gap * (len(imgs) - 1)
    canvas = Image.new("RGB", (width, height), bg)
    y = 0
    for im in imgs:
        canvas.paste(im, ((width - im.width) // 2, y))
        y += im.height + gap
    canvas.save(out_path)
    print("wrote", out_path, canvas.size)


def stack_images_horizontally(paths, out_path, gap=16, bg=(255, 255, 255)):
    imgs = [Image.open(p) for p in paths]
    height = max(im.height for im in imgs)
    width = sum(im.width for im in imgs) + gap * (len(imgs) - 1)
    canvas = Image.new("RGB", (width, height), bg)
    x = 0
    for im in imgs:
        canvas.paste(im, (x, (height - im.height) // 2))
        x += im.width + gap
    canvas.save(out_path)
    print("wrote", out_path, canvas.size)


def main():
    app = QApplication.instance() or QApplication([])

    os.makedirs(OUT_DIR, exist_ok=True)

    # ----- 01: start screen (mainly so the version in the footer can't go stale) -----
    from gui.start_screen import StartScreen
    start = StartScreen()
    start.resize(1300, 850)
    start.show()
    app.processEvents()
    grab(start, os.path.join(OUT_DIR, "01-start-screen.png"))
    start.close()

    from gui.review_screen import ReviewScreen

    scratch_dir = tempfile.mkdtemp(prefix="omr_screenshots_")
    run_state = build_run_state(scratch_dir)

    screen = ReviewScreen()
    screen.resize(1300, 850)
    screen.load(run_state)
    settle(screen, app)
    screen.show()
    app.processEvents()

    os.makedirs(OUT_DIR, exist_ok=True)

    splitter = screen.findChild(QSplitter)
    table_panel, preview_panel, edit_panel = (splitter.widget(i) for i in range(3))

    # ----- 04: full review screen, overlay off -----
    screen.expected_btn.setChecked(False)
    app.processEvents()
    grab(screen, os.path.join(OUT_DIR, "04-review-screen.png"))

    # ----- 05: correction panel close-up -----
    grab(edit_panel, os.path.join(OUT_DIR, "05-correction-panel.png"))

    # ----- 06: same page, expected-answers overlay on -----
    screen.expected_btn.setChecked(True)
    app.processEvents()
    grab(screen, os.path.join(OUT_DIR, "06-expected-overlay.png"))
    screen.expected_btn.setChecked(False)
    app.processEvents()

    # ----- 07: legend crop -----
    legend = None
    for lbl in preview_panel.findChildren(QLabel):
        if "Manual edit" in lbl.text():
            legend = lbl
            break
    assert legend is not None, "could not find the colour legend QLabel"
    grab(legend, os.path.join(OUT_DIR, "07-legend.png"))

    # ----- 08: export button + the save dialog it opens -----
    r = screen._current_result()
    default_name = screen._default_review_export_name(r)
    btn_shot = os.path.join(scratch_dir, "_export_btn.png")
    grab(edit_panel, btn_shot)

    dialog_start_dir = os.path.join(scratch_dir, "save_dialog_demo")
    os.makedirs(dialog_start_dir, exist_ok=True)
    dlg = QFileDialog(screen, "Export student review PDF",
                       os.path.join(dialog_start_dir, default_name), "PDF files (*.pdf)")
    dlg.setOption(QFileDialog.DontUseNativeDialog, True)
    dlg.setAcceptMode(QFileDialog.AcceptSave)
    dlg.resize(640, 480)
    dlg.show()
    app.processEvents()
    dlg_shot = os.path.join(scratch_dir, "_export_dialog.png")
    grab(dlg, dlg_shot)
    dlg.close()

    out08 = os.path.join(OUT_DIR, "08-export-button.png")
    stack_images_vertically([btn_shot, dlg_shot], out08)
    _optimize_png(out08)

    # ----- 09: exported 2-page student review PDF, both pages side by side -----
    export_pdf_path = os.path.join(scratch_dir, default_name)
    omr.export_student_review_pdf(r, export_pdf_path, screen.students_df,
                                   correct_answers_by_perm=screen.correct_answers_by_perm)

    from pdf2image import convert_from_path
    export_pages = convert_from_path(export_pdf_path, dpi=100)
    page_paths = []
    for i, pg in enumerate(export_pages):
        p = os.path.join(scratch_dir, f"_export_page{i + 1}.png")
        pg.save(p)
        page_paths.append(p)
    out09 = os.path.join(OUT_DIR, "09-export-pdf-pages.png")
    stack_images_horizontally(page_paths, out09)
    _optimize_png(out09)

    # ----- 10: answer grid colour states (plain / orange / purple / dark grey) -----
    # Question 5's key is D only; the student marked B (auto-detected, wrong).
    # Toggle C on, apply+save (-> becomes a persisted "purple" manual mark),
    # reload, then toggle A on too (a fresh, unsaved "orange" toggle) so the
    # same row shows all four states at once: A orange, B plain, C purple, D
    # dark grey (expected-correct, unmarked).
    # Widen the edit panel so columns A-D + Score are all visible at once
    # (the default 3-way split only fits ~3 answer columns).
    screen.resize(1700, 850)
    splitter.setSizes([200, 400, 900])
    app.processEvents()

    q5_row = 4  # 0-indexed: question 5
    screen.answers_table.cellClicked.emit(q5_row, 2)  # C
    app.processEvents()
    screen._apply_correction()
    settle(screen, app)
    screen._load_page(screen.current_index)
    app.processEvents()
    screen.answers_table.cellClicked.emit(q5_row, 0)  # A
    app.processEvents()

    # Crop to a few rows around Q5 rather than the whole (20-row) grid.
    table = screen.answers_table
    top = table.rowViewportPosition(max(q5_row - 1, 0))
    bottom = table.rowViewportPosition(min(q5_row + 2, table.rowCount() - 1)) + table.rowHeight(0) + table.horizontalHeader().height()
    full_pix = table.grab()
    cropped = full_pix.copy(0, 0, full_pix.width(), min(bottom, full_pix.height()))
    out10 = os.path.join(OUT_DIR, "10-answer-grid-colours.png")
    cropped.save(out10)
    _optimize_png(out10)
    print("wrote", out10, cropped.size().toTuple())

    print("\nAll screenshots written to", OUT_DIR)


if __name__ == "__main__":
    main()
