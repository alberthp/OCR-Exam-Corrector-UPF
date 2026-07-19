"""Standalone driver, launched as a subprocess (not collected by pytest --
its name doesn't match test_*.py) by test_stability_e2e_subprocess.py.

Runs the real app end-to-end in a real OS process: New Exam -> scan ->
Review -> navigate a few pages -> close. This is the only test technique
that can catch a *native* crash (e.g. the v1.6 Qt6Core STATUS_STACK_BUFFER_OVERRUN)
since those bypass Python's exception handling entirely and would just
kill an in-process pytest worker along with the test if run any other way.

Usage: python _e2e_driver.py <pdf> <students> <answers> <output_dir>
                              [num_questions] [num_options] [exam_type]
                              [timeout_seconds] [nav_mode] [nav_sweeps]
num_questions/num_options/exam_type default to 30/4/Retake for backward
compatibility; pass explicitly for exams with a different question count.
timeout_seconds (default 180) is a hard safety net, not an expected
runtime -- a large multi-dozen-page batch through a cold-started frozen
exe legitimately needs longer than a small one; pass a bigger value for
those rather than treating the default as universal.

nav_mode (default "light") controls review-page navigation once the scan
finishes:
  - "light":  the original behaviour -- next, next, prev (3 calls total).
  - "stress": sweeps forward through every page then back through every
    page, nav_sweeps times (default 1), firing each _go_next()/_go_prev()
    back-to-back via zero-delay QTimer chaining rather than waiting for
    each page's preview render to finish first. Navigation is only gated
    by _local_busy (which guards saves), NOT by pending preview renders --
    so this can spawn many concurrent _PreviewRenderWorker threads, each
    launching its own poppler subprocess against the same PDF file. This
    targets the exact code path active when a STATUS_STACK_BUFFER_OVERRUN
    was observed once during "navigating review pages" (see TEST_SUITE.md).

Exit code 0 = completed cleanly. Anything else = the parent test reports
this script's stdout/stderr as the failure detail.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    pdf_path, students_path, answers_path, output_dir = sys.argv[1:5]
    extra = sys.argv[5:11]
    num_questions = int(extra[0]) if len(extra) > 0 else 30
    num_options = int(extra[1]) if len(extra) > 1 else 4
    exam_type = extra[2] if len(extra) > 2 else "Retake"
    timeout_seconds = int(extra[3]) if len(extra) > 3 else 180
    nav_mode = extra[4] if len(extra) > 4 else "light"
    nav_sweeps = int(extra[5]) if len(extra) > 5 else 1
    os.makedirs(output_dir, exist_ok=True)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication([])

    from gui.main_window import MainWindow
    window = MainWindow()
    nes = window.new_exam_screen

    def start_scan():
        print("DRIVER: starting scan", flush=True)
        nes.pdf_row.setText(pdf_path)
        nes.students_row.setText(students_path)
        nes.answers_row.setText(answers_path)
        nes.output_row.setText(output_dir)
        idx = nes.exam_type_combo.findText(exam_type)
        nes.exam_type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        nes.questions_spin.setValue(num_questions)
        nes.options_spin.setValue(num_options)
        nes._run_analysis()

    def do_review_steps(summary):
        print(f"DRIVER: scan finished, total_pages={summary.get('total_pages')}", flush=True)
        QTimer.singleShot(200, navigate_review)

    def navigate_review():
        rs = window.review_screen
        if nav_mode == "stress":
            total = len(rs.all_results)
            print(f"DRIVER: stress-navigating {total} pages x{nav_sweeps} sweep(s) "
                  f"(forward+back each)", flush=True)
            stress_sweep(rs, total, nav_sweeps)
        elif nav_mode == "stress-forward-only":
            total = min(len(rs.all_results), nav_sweeps) if nav_sweeps > 0 else len(rs.all_results)
            print(f"DRIVER: stress-navigating {total} pages (of {len(rs.all_results)}), "
                  f"FORWARD ONLY", flush=True)
            stress_forward_only(rs, total, 1)
        else:
            print("DRIVER: navigating review pages", flush=True)
            try:
                rs._go_next()
                rs._go_next()
                rs._go_prev()
            except Exception as e:
                print(f"DRIVER: navigation raised (non-fatal to this smoke test): {e}", flush=True)
            QTimer.singleShot(200, wait_then_close)

    def stress_forward_only(rs, total, passes_remaining, step=0):
        if passes_remaining <= 0:
            print("DRIVER: forward-only stress complete", flush=True)
            QTimer.singleShot(200, wait_then_close)
            return
        try:
            rs._go_next()
        except Exception as e:
            print(f"DRIVER: forward-only step raised (non-fatal): {e}", flush=True)
        step += 1
        if step < total:
            QTimer.singleShot(0, lambda: stress_forward_only(rs, total, passes_remaining, step))
        else:
            # back to page 0 (no worker spawned, already cached/current), then next pass
            rs._load_page(0)
            QTimer.singleShot(0, lambda: stress_forward_only(rs, total, passes_remaining - 1, 0))

    def stress_sweep(rs, total, sweeps_remaining, direction="forward", step=0):
        # Fires each nav call back-to-back via zero-delay QTimer chaining --
        # deliberately does NOT wait for each page's preview render to
        # finish, so consecutive calls can spawn overlapping
        # _PreviewRenderWorker threads (see module docstring).
        if sweeps_remaining <= 0:
            print("DRIVER: stress navigation complete", flush=True)
            QTimer.singleShot(200, wait_then_close)
            return
        try:
            if direction == "forward":
                rs._go_next()
            else:
                rs._go_prev()
        except Exception as e:
            print(f"DRIVER: stress nav step raised (non-fatal): {e}", flush=True)

        step += 1
        if step < total:
            QTimer.singleShot(0, lambda: stress_sweep(rs, total, sweeps_remaining, direction, step))
        elif direction == "forward":
            QTimer.singleShot(0, lambda: stress_sweep(rs, total, sweeps_remaining, "backward", 0))
        else:
            QTimer.singleShot(0, lambda: stress_sweep(rs, total, sweeps_remaining - 1, "forward", 0))

    def wait_then_close():
        # A real user would see "please wait" and try again; poll the same
        # busy state closeEvent checks instead of racing a pending preview
        # render (calling window.close() while busy pops a *modal*
        # QMessageBox.information, which would hang forever with no user
        # around to dismiss it in this headless driver).
        rs = window.review_screen
        scan_worker = getattr(window.new_exam_screen, 'worker', None)
        busy = (rs._local_busy or bool(rs._pending_sync_workers)
                or bool(rs._pending_preview_workers)
                or (scan_worker is not None and scan_worker.isRunning()))
        if busy:
            QTimer.singleShot(100, wait_then_close)
            return
        do_close()

    def do_close():
        print("DRIVER: closing", flush=True)
        window.close()
        app.quit()

    def on_failed(msg):
        print(f"DRIVER: scan FAILED: {msg}", file=sys.stderr, flush=True)
        app.exit(2)

    def timeout_abort():
        print("DRIVER: TIMEOUT, aborting", file=sys.stderr, flush=True)
        os._exit(3)

    nes.finished_run.connect(do_review_steps)
    # finished_run only fires via MainWindow's wiring after AnalysisWorker.finished_ok;
    # also watch the worker's own failed signal once it exists.
    QTimer.singleShot(100, start_scan)

    def hook_failed_signal():
        if nes.worker is not None:
            nes.worker.failed.connect(on_failed)
        else:
            QTimer.singleShot(50, hook_failed_signal)
    QTimer.singleShot(150, hook_failed_signal)

    QTimer.singleShot(timeout_seconds * 1000, timeout_abort)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
