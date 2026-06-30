"""New-evaluation screen: pick input files/params and run the OMR pipeline."""

import os
import traceback

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QSpinBox, QCheckBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QTextEdit, QMessageBox,
    QGroupBox, QHeaderView,
)

from pdf2image import convert_from_path
import omr_correct as omr


class AnalysisWorker(QThread):
    """Runs the full OMR pipeline in a background thread so the UI stays responsive.

    Emits page_done after each page so the table updates live, and either
    finished_ok (with the complete run_state dict) or failed (with an error
    string) at the end.
    """

    log = Signal(str)
    page_done = Signal(int, int, dict)   # (current_page, total_pages, page_info)
    finished_ok = Signal(dict)           # run_state dict consumed by ReviewScreen.load()
    failed = Signal(str)                 # human-readable error + traceback

    def __init__(self, exam_pdf, students_path, answers_path,
                 num_questions, num_options, output_dir, dpi):
        super().__init__()
        self.exam_pdf = exam_pdf
        self.students_path = students_path
        self.answers_path = answers_path
        self.num_questions = num_questions
        self.num_options = num_options
        self.output_dir = output_dir
        self.dpi = dpi  # 0 = auto-detect

    def run(self):
        try:
            os.makedirs(self.output_dir, exist_ok=True)

            self.log.emit(f"Loading students from {self.students_path}...")
            students_df = omr.load_students(self.students_path)
            self.log.emit(f"  {len(students_df)} students loaded")

            self.log.emit(f"Loading correct answers from {self.answers_path}...")
            correct_answers_by_perm = omr.load_correct_answers(self.answers_path)
            perm_names = ', '.join(sorted(correct_answers_by_perm.keys()))
            self.log.emit(f"  {len(correct_answers_by_perm)} permutation(s) loaded: {perm_names}")

            dpi = self.dpi
            if dpi <= 0:
                self.log.emit("Auto-detecting source DPI...")
                dpi = omr.detect_pdf_dpi(self.exam_pdf)
                self.log.emit(f"  Detected: {dpi} DPI")

            self.log.emit(f"Rendering {self.exam_pdf} at {dpi} DPI...")
            pages = convert_from_path(self.exam_pdf, dpi=dpi)
            total = len(pages)
            self.log.emit(f"  {total} pages rendered")

            # Build a U-number lookup to show student names in the live table.
            student_lookup = {}
            for _, row in students_df.iterrows():
                u = str(row.get('U_number', '')).strip().upper().replace('U', '')
                if u:
                    student_lookup[u] = row

            all_results = []
            for i, page in enumerate(pages):
                try:
                    r, _corrected = omr.process_page(
                        page, i + 1, self.num_questions, self.num_options, source_dpi=dpi)
                except Exception as e:
                    # Per-page exceptions are non-fatal; mark and continue so one
                    # bad scan doesn't abort the whole exam batch.
                    r = {'page': i + 1, 'status': 'EXCEPTION', 'error': str(e)}
                all_results.append(r)

                u_clean = str(r.get('u_number', '') or '').split('|')[0]
                student_row = student_lookup.get(u_clean)
                if student_row is not None:
                    name = f"{student_row.get('Nom', '')} {student_row.get('Cognom1', '')} {student_row.get('Cognom2', '') or ''}".strip()
                else:
                    name = ''
                n_answered = sum(1 for a in r.get('answers', {}).values() if a.get('marks'))

                info = {
                    'page': i + 1,
                    'status': r.get('status', '?'),
                    'u_number': u_clean or '-',
                    'name': name or '(no match)',
                    'dni': r.get('dni', '') or '-',
                    'permut': '' if r.get('permut') is None else str(r.get('permut')),
                    'n_answered': n_answered,
                }
                self.page_done.emit(i + 1, total, info)

            excel_path = os.path.join(self.output_dir, 'results.xlsx')
            self.log.emit(f"\nWriting Excel to {excel_path}...")
            omr.write_excel(all_results, students_df, correct_answers_by_perm, excel_path,
                             self.num_questions, self.num_options)

            pdf_path = os.path.join(self.output_dir, 'annotated_review.pdf')
            self.log.emit(f"Writing annotated PDF to {pdf_path}...")
            omr.write_annotated_pdf(all_results, pdf_path, students_df=students_df)

            cache_path = os.path.join(self.output_dir, 'review_cache.pkl')
            self.log.emit(f"Saving review cache to {cache_path}...")
            omr.save_review_cache(all_results, students_df, correct_answers_by_perm,
                                   self.num_questions, self.num_options,
                                   excel_path, pdf_path, cache_path,
                                   exam_pdf_path=self.exam_pdf, dpi=dpi)

            n_processed = sum(1 for r in all_results if r.get('answers'))
            n_matched = sum(1 for r in all_results if r.get('u_number'))
            self.log.emit("\nDONE")
            self.finished_ok.emit({
                'total_pages': total,
                'n_processed': n_processed,
                'u_detected': n_matched,
                'excel_path': excel_path,
                'pdf_path': pdf_path,
                'output_dir': self.output_dir,
                # Pass the full in-memory results to the review screen so it
                # can redraw single PDF pages on correction without re-running OCR.
                # The cache file lets the same session be reopened after restart.
                'all_results': all_results,
                'students_df': students_df,
                'correct_answers_by_perm': correct_answers_by_perm,
                'num_questions': self.num_questions,
                'num_options': self.num_options,
                'cache_path': cache_path,
                # Needed by the review screen's "Rescan this page" action.
                'exam_pdf': self.exam_pdf,
                'dpi': dpi,
            })
        except Exception as e:
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")


class FileRow(QWidget):
    """A QLineEdit + "Browse..." button pair used for every file/folder picker.

    dialog_fn is a zero-argument callable that opens a file dialog and returns
    the chosen path (or '' if cancelled).
    """

    def __init__(self, dialog_fn):
        super().__init__()
        self._dialog_fn = dialog_fn
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(self.edit)
        layout.addWidget(browse_btn)

    def _browse(self):
        path = self._dialog_fn()
        if path:
            self.edit.setText(path)

    def text(self):
        return self.edit.text().strip()

    def setText(self, value):
        self.edit.setText(value)


class NewExamScreen(QWidget):
    """Input form + live progress/log for running the OMR pipeline on a new exam PDF.

    On success, emits finished_run with the run-state dict so MainWindow can
    switch straight into the review screen — no extra click needed.  On
    failure the error stays visible so the user can fix inputs and retry.
    """

    finished_run = Signal(dict)
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.output_dir = "./output"
        self._build_ui()

    # ----- UI construction -----

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        back_btn = QPushButton("<< Back to start")
        back_btn.clicked.connect(self.back_requested.emit)
        top_row.addWidget(back_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        layout.addWidget(self._build_inputs_group())
        layout.addWidget(self._build_params_group())

        self.run_btn = QPushButton("Run Analysis")
        self.run_btn.setMinimumHeight(36)
        self.run_btn.clicked.connect(self._run_analysis)
        layout.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Idle")
        layout.addWidget(self.progress_label)

        layout.addWidget(self._build_table_group(), stretch=2)
        layout.addWidget(self._build_log_group(), stretch=1)

        out_row = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open output folder")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        out_row.addWidget(self.open_folder_btn)
        out_row.addStretch()
        layout.addLayout(out_row)

    def _build_inputs_group(self):
        group = QGroupBox("Input files")
        form = QFormLayout()

        self.pdf_row = FileRow(lambda: QFileDialog.getOpenFileName(
            self, "Select scanned exam PDF", "", "PDF files (*.pdf)")[0])
        form.addRow("Scanned exam PDF:", self.pdf_row)

        self.students_row = FileRow(lambda: QFileDialog.getOpenFileName(
            self, "Select students list", "", "Spreadsheets (*.csv *.xls *.xlsx)")[0])
        form.addRow("Students list:", self.students_row)

        self.answers_row = FileRow(lambda: QFileDialog.getOpenFileName(
            self, "Select answers file", "", "Spreadsheets (*.csv *.xlsx)")[0])
        form.addRow("Answers (Perm,QuestionNum,A,B,...):", self.answers_row)

        self.output_row = FileRow(lambda: QFileDialog.getExistingDirectory(
            self, "Select output directory"))
        self.output_row.setText("./output")
        form.addRow("Output directory:", self.output_row)

        group.setLayout(form)
        return group

    def _build_params_group(self):
        group = QGroupBox("Exam parameters")
        form = QFormLayout()

        self.questions_spin = QSpinBox()
        # 100 max: the bubble sheet has 5 answer columns × 20 rows; beyond
        # that there are no bubbles to read, and read_answers() would crash.
        self.questions_spin.setRange(1, 100)
        self.questions_spin.setValue(10)
        form.addRow("Number of questions:", self.questions_spin)

        self.options_spin = QSpinBox()
        self.options_spin.setRange(2, 10)
        self.options_spin.setValue(4)
        form.addRow("Options per question:", self.options_spin)

        dpi_row = QWidget()
        dpi_layout = QHBoxLayout(dpi_row)
        dpi_layout.setContentsMargins(0, 0, 0, 0)
        self.dpi_auto_check = QCheckBox("Auto-detect")
        self.dpi_auto_check.setChecked(True)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setEnabled(False)
        # Auto-detect is almost always right; manual override is a fallback.
        self.dpi_auto_check.toggled.connect(lambda checked: self.dpi_spin.setEnabled(not checked))
        dpi_layout.addWidget(self.dpi_auto_check)
        dpi_layout.addWidget(self.dpi_spin)
        form.addRow("Source DPI:", dpi_row)

        group.setLayout(form)
        return group

    def _build_table_group(self):
        group = QGroupBox("Per-page results")
        layout = QVBoxLayout()
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Page", "Status", "U-Number", "Student", "DNI", "Perm", "Answered"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        group.setLayout(layout)
        return group

    def _build_log_group(self):
        group = QGroupBox("Log")
        layout = QVBoxLayout()
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit)
        group.setLayout(layout)
        return group

    # ----- Actions -----

    def _run_analysis(self):
        pdf = self.pdf_row.text()
        students = self.students_row.text()
        answers = self.answers_row.text()
        output_dir = self.output_row.text() or "./output"

        if not pdf or not os.path.exists(pdf):
            QMessageBox.warning(self, "Missing file", "Please select a valid exam PDF.")
            return
        if not students or not os.path.exists(students):
            QMessageBox.warning(self, "Missing file", "Please select a valid students list.")
            return
        if not answers or not os.path.exists(answers):
            QMessageBox.warning(self, "Missing file", "Please select a valid answers file.")
            return

        self.output_dir = output_dir
        self.table.setRowCount(0)
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.run_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.progress_label.setText("Starting...")

        self.worker = AnalysisWorker(
            pdf, students, answers,
            self.questions_spin.value(), self.options_spin.value(),
            output_dir, 0 if self.dpi_auto_check.isChecked() else self.dpi_spin.value(),
        )
        self.worker.log.connect(self._on_log)
        self.worker.page_done.connect(self._on_page_done)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_log(self, msg):
        self.log_edit.append(msg)

    def _on_page_done(self, current, total, info):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(
            f"Processing page {current}/{total}: U={info['u_number']} {info['name']}")

        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [info['page'], info['status'], info['u_number'], info['name'],
                  info['dni'], info['permut'], info['n_answered']]
        for col, value in enumerate(values):
            self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.scrollToBottom()

    def _on_finished(self, summary):
        self.run_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self.progress_label.setText(
            f"Done: {summary['n_processed']}/{summary['total_pages']} pages processed, "
            f"{summary['u_detected']} U-numbers detected. Opening review..."
        )
        self._on_log(f"Results: {summary['excel_path']}")
        self._on_log(f"Annotated PDF: {summary['pdf_path']}")
        self.finished_run.emit(summary)

    def _on_failed(self, err):
        self.run_btn.setEnabled(True)
        self._on_log(f"\nERROR:\n{err}")
        QMessageBox.critical(self, "Analysis failed", err.split('\n')[0])

    def _open_output_folder(self):
        """Open the output directory in Windows Explorer."""
        path = os.path.abspath(self.output_dir)
        if os.path.isdir(path):
            os.startfile(path)
        else:
            QMessageBox.warning(self, "Not found", f"Output directory not found:\n{path}")
