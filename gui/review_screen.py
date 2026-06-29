"""Review/correction screen: step through annotated pages and fix mismatches."""

import os
import shutil
import tempfile
import time

from PySide6.QtCore import QEvent, Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QFileDialog,
    QGroupBox, QHeaderView, QSplitter, QScrollArea, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QApplication,
)

from pdf2image import convert_from_path
import omr_correct as omr


def _copy_with_retry(src, dst, attempts=5, base_delay=1.0):
    """shutil.copy2 with exponential backoff.

    Cloud-sync clients (Google Drive, OneDrive, ...) can hold a transient
    lock on a destination file while uploading it, or briefly fail a write
    right after one finishes. A short retry loop rides that out instead of
    surfacing a spurious "could not save" error.
    """
    last_err = None
    for attempt in range(attempts):
        try:
            shutil.copy2(src, dst)
            return
        except OSError as e:
            last_err = e
            time.sleep(base_delay * (2 ** attempt))
    raise last_err


class _SaveWorker(QThread):
    """Writes results.xlsx, patches one annotated-PDF page, and updates the
    review cache -- all against local scratch copies -- then publishes the
    results back to their real (possibly cloud-synced) location.

    patch_annotated_pdf_page() rewrites the *entire* PDF file (pypdf has no
    in-place page replacement). Doing that repeatedly straight against a
    file inside a Google Drive/OneDrive-synced folder can stall for minutes:
    the sync client may hold a lock on it mid-upload, or have evicted it to
    a cloud-only placeholder that has to be re-downloaded first. Working
    against a local temp copy keeps every edit's heavy lifting on local
    disk; only the final, already-finished file touches the synced path.

    Also runs off the UI thread so the review screen stays responsive while
    any of this -- especially the cloud copy-back -- is happening.

    Emits two signals rather than one: `local_done` fires as soon as the
    local write/patch/cache-update finishes, so the review screen can show
    the new annotation right away; `synced` fires later once the (possibly
    slow) copy back to the cloud-synced path finishes, and only updates the
    status line. Without this split, a slow Drive upload would delay the
    on-screen feedback for an edit that was, in fact, already saved.
    """

    local_done = Signal(str)  # error message, or '' once the local save succeeds
    synced = Signal(str)      # error message, or '' once the copy-back to the synced path succeeds

    def __init__(self, all_results, students_df, correct_answers_by_perm,
                 num_questions, num_options, excel_path, pdf_path, result,
                 pdf_idx, cache_path, exam_pdf_path, dpi,
                 synced_excel_path, synced_pdf_path, synced_cache_path):
        super().__init__()
        self.all_results = all_results
        self.students_df = students_df
        self.correct_answers_by_perm = correct_answers_by_perm
        self.num_questions = num_questions
        self.num_options = num_options
        self.excel_path = excel_path
        self.pdf_path = pdf_path
        self.result = result
        self.pdf_idx = pdf_idx
        self.cache_path = cache_path
        self.exam_pdf_path = exam_pdf_path
        self.dpi = dpi
        self.synced_excel_path = synced_excel_path
        self.synced_pdf_path = synced_pdf_path
        self.synced_cache_path = synced_cache_path

    def run(self):
        try:
            omr.write_excel(self.all_results, self.students_df,
                             self.correct_answers_by_perm, self.excel_path,
                             self.num_questions, self.num_options)
            if self.pdf_idx is not None:
                omr.patch_annotated_pdf_page(self.pdf_path, self.result,
                                              self.students_df, self.pdf_idx)
            if self.cache_path:
                omr.save_review_cache(self.all_results, self.students_df,
                                       self.correct_answers_by_perm,
                                       self.num_questions, self.num_options,
                                       self.excel_path, self.pdf_path, self.cache_path,
                                       exam_pdf_path=self.exam_pdf_path, dpi=self.dpi)
        except Exception as e:
            self.local_done.emit(str(e))
            self.synced.emit(str(e))
            return

        self.local_done.emit('')

        try:
            _copy_with_retry(self.excel_path, self.synced_excel_path)
            _copy_with_retry(self.pdf_path, self.synced_pdf_path)
            if self.cache_path and self.synced_cache_path:
                _copy_with_retry(self.cache_path, self.synced_cache_path)
            self.synced.emit('')
        except Exception as e:
            self.synced.emit(str(e))


class _PreviewRenderWorker(QThread):
    """Renders one page of the annotated PDF to a QImage off the UI thread.

    convert_from_path() spawns a poppler subprocess and blocks until it
    exits. Doing that on the GUI thread freezes the window for the render's
    duration (Windows shows the busy cursor over it) -- which adds up fast
    when browsing through many pages, since each newly-visited page pays
    that cost once before being cached.
    """

    done = Signal(int, object, str)  # pdf_idx, QImage or None, error message

    def __init__(self, pdf_path, pdf_idx, dpi):
        super().__init__()
        self.pdf_path = pdf_path
        self.pdf_idx = pdf_idx
        self.dpi = dpi

    def run(self):
        try:
            pages = convert_from_path(
                self.pdf_path, dpi=self.dpi, first_page=self.pdf_idx + 1, last_page=self.pdf_idx + 1)
            pil_img = pages[0].convert('RGB')
            # QImage (unlike QPixmap) is safe to build off the GUI thread;
            # the QPixmap conversion happens back on the main thread.
            qimage = QImage(pil_img.tobytes(), pil_img.width, pil_img.height,
                             pil_img.width * 3, QImage.Format_RGB888).copy()
            self.done.emit(self.pdf_idx, qimage, '')
        except Exception as e:
            self.done.emit(self.pdf_idx, None, str(e))


class ReviewScreen(QWidget):
    """Page-by-page review/correction screen.

    Lets the user step through the annotated PDF, fix identification fields
    and individual answer marks for the page being reviewed, and have
    results.xlsx and annotated_review.pdf updated immediately -- keyed by
    page number, with no need to search the spreadsheet for the student.

    The screen is built once and reused across run-state loads: call
    `load(run_state)` each time a new analysis finishes or a previous
    review_cache.pkl is opened, rather than constructing a new instance.
    """

    back_requested = Signal()

    # Shown on "Apply correction" while a save/sync triggered by Apply,
    # Revert, or Rescan hasn't fully reached the output folder yet.
    UNSAVED_STYLE = "background-color: orange; color: black;"

    PREVIEW_DPI = 200  # rendered once per page; zoom rescales this cached pixmap
    ZOOM_MIN = 0.25
    ZOOM_MAX = 4.0
    ZOOM_STEP = 1.25

    # Bounds the rendered-page pixmap cache (per pdf page index) so browsing a
    # very long exam can't grow memory unboundedly; oldest entry evicted first.
    PREVIEW_CACHE_SIZE = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_pixmap = None
        self._zoom = 1.0
        self._preview_cache = {}
        # Middle-button drag-to-pan state for the preview panel.
        self._pan_dragging = False
        self._pan_last_pos = None
        # Local writes (to the scratch copy) are serialized via this flag so
        # two _SaveWorkers can never patch the same local PDF concurrently.
        # The (possibly slow) cloud copy-back is NOT serialized against it --
        # _pending_sync_workers just keeps a strong reference to each worker
        # still finishing its sync so Python can't garbage-collect a running
        # QThread out from under itself.
        self._local_busy = False
        self._pending_sync_workers = []
        # Set when a copy-back to the output folder fails, so the "Apply
        # correction" button stays flagged as unpersisted instead of
        # reverting to its default color on the next sync attempt's outcome.
        self._sync_failed = False
        # True while the form has unapplied edits the user made since the
        # page was last loaded/saved -- distinct from _local_busy/
        # _pending_sync_workers, which track an already-applied edit that's
        # still being written/synced to disk.
        self._form_dirty = False
        # Guards _load_edit_form()/_load_answers_grid() programmatically
        # populating the form from `r`, so that doesn't itself look like a
        # user edit (QLineEdit.setText() fires textChanged either way).
        self._loading_form = False
        self._scratch_dir = None
        # Tracks which pdf page index the visible preview was last asked to
        # show, so a render that finishes after the user has already
        # navigated elsewhere doesn't clobber the (now wrong) preview.
        self._preview_request_idx = None
        self._pending_preview_workers = []
        self.all_results = []
        self.students_df = None
        self.correct_answers_by_perm = {}
        self.num_questions = 0
        self.num_options = 0
        # self.excel_path / self.pdf_path / self.cache_path point at the LOCAL
        # scratch copies that all reads/writes during the session use; the
        # synced_* counterparts are the real (possibly cloud-synced) files
        # those get copied back to after each save. See _setup_local_scratch.
        self.excel_path = None
        self.pdf_path = None
        self.cache_path = None
        self.synced_excel_path = None
        self.synced_pdf_path = None
        self.synced_cache_path = None
        self.exam_pdf_path = None
        self.source_dpi = None
        self.student_lookup = {}
        self.pdf_page_index = {}
        self.current_index = 0
        self._build_ui()

    # ----- Loading a run state -----

    def load(self, run_state):
        self.all_results = run_state['all_results']
        self.students_df = run_state['students_df']
        self.correct_answers_by_perm = run_state['correct_answers_by_perm']
        self.num_questions = run_state['num_questions']
        self.num_options = run_state['num_options']
        self.synced_excel_path = run_state['excel_path']
        self.synced_pdf_path = run_state['pdf_path']
        self.synced_cache_path = run_state.get('cache_path')
        # Note: deliberately NOT clearing _pending_sync_workers here -- a
        # previous session's sync may still be finishing in the background,
        # and dropping the only Python reference to that running QThread
        # would risk it being garbage-collected mid-run.
        self._local_busy = False
        self._sync_failed = False
        self._update_persist_indicator()
        self.exam_pdf_path = run_state.get('exam_pdf')
        self.source_dpi = run_state.get('dpi')
        self._preview_cache = {}
        self._setup_local_scratch()

        self.student_lookup = {}
        if self.students_df is not None:
            for _, row in self.students_df.iterrows():
                u = str(row.get('U_number', '')).strip().upper().replace('U', '')
                if u:
                    self.student_lookup[u] = row

        self._recompute_pdf_page_index()

        self.answers_table.setHorizontalHeaderLabels(omr.OPTION_LABELS[:self.num_options])

        self.table.setRowCount(0)
        for r in self.all_results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._fill_table_row(row, r)

        self.current_index = 0
        self._load_page(0)

    def _setup_local_scratch(self):
        """Copy the synced excel/pdf/cache files into a local temp folder and
        point self.excel_path/pdf_path/cache_path at those copies.

        See _SaveWorker's docstring for why: every correction rewrites the
        whole annotated PDF, and doing that directly against a cloud-synced
        file can stall for minutes. Working against a local copy avoids
        that; _SaveWorker copies the finished result back to the synced
        path after each save.
        """
        if self._scratch_dir is not None:
            shutil.rmtree(self._scratch_dir, ignore_errors=True)
        self._scratch_dir = tempfile.mkdtemp(prefix='omr_review_')

        self.pdf_path = os.path.join(self._scratch_dir, os.path.basename(self.synced_pdf_path))
        shutil.copy2(self.synced_pdf_path, self.pdf_path)

        self.excel_path = os.path.join(self._scratch_dir, os.path.basename(self.synced_excel_path))
        shutil.copy2(self.synced_excel_path, self.excel_path)

        if self.synced_cache_path and os.path.exists(self.synced_cache_path):
            self.cache_path = os.path.join(self._scratch_dir, os.path.basename(self.synced_cache_path))
            shutil.copy2(self.synced_cache_path, self.cache_path)
        else:
            self.cache_path = None

    def _recompute_pdf_page_index(self):
        """Map each result's position in all_results to its real page index
        inside annotated_review.pdf. Pages that failed processing have no
        '_corrected' image, so they never got a page written into the PDF --
        the two indices can drift apart once any page fails (or a rescan
        flips a page between failed/succeeded).
        """
        self.pdf_page_index = {}
        pdf_idx = 0
        for i, r in enumerate(self.all_results):
            if r.get('_corrected') is not None:
                self.pdf_page_index[i] = pdf_idx
                pdf_idx += 1

    # ----- UI construction -----

    def _build_ui(self):
        outer = QVBoxLayout(self)

        top_row = QHBoxLayout()
        back_btn = QPushButton("<< Back to start")
        back_btn.clicked.connect(self.back_requested.emit)
        top_row.addWidget(back_btn)
        top_row.addStretch()
        outer.addLayout(top_row)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter)
        splitter.addWidget(self._build_table_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_edit_panel())
        splitter.setSizes([280, 650, 350])

    def _build_table_panel(self):
        group = QGroupBox("Pages")
        layout = QVBoxLayout(group)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Page", "Status", "U-Number", "Student", "DNI", "Perm", "Manual"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_table_row_selected)
        layout.addWidget(self.table)
        return group

    def _fill_table_row(self, row, r):
        u_clean = str(r.get('u_number', '') or '').split('|')[0]
        student = self.student_lookup.get(u_clean)
        name = ''
        if student is not None:
            name = (f"{student.get('Nom', '')} {student.get('Cognom1', '')} "
                     f"{student.get('Cognom2', '') or ''}").strip()
        permut_val = r.get('permut')
        values = [
            r.get('page'),
            r.get('status', ''),
            u_clean or '-',
            name or '(no match)',
            r.get('dni', '') or '-',
            '' if permut_val is None else str(permut_val),
            'Y' if r.get('_manual_edit') else '',
        ]
        for col, value in enumerate(values):
            self.table.setItem(row, col, QTableWidgetItem(str(value)))

    def _build_preview_panel(self):
        group = QGroupBox("Annotated page")
        layout = QVBoxLayout(group)

        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("<< Prev")
        self.prev_btn.clicked.connect(self._go_prev)
        self.page_label = QLabel("Page 1 / 1")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_btn = QPushButton("Next >>")
        self.next_btn.clicked.connect(self._go_next)
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.page_label, stretch=1)
        nav_row.addWidget(self.next_btn)
        layout.addLayout(nav_row)

        zoom_row = QHBoxLayout()
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedWidth(30)
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setFixedWidth(55)
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(30)
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        self.zoom_fit_btn = QPushButton("Fit to page")
        self.zoom_fit_btn.clicked.connect(self._zoom_fit)
        zoom_row.addWidget(self.zoom_out_btn)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(self.zoom_in_btn)
        zoom_row.addWidget(self.zoom_fit_btn)
        zoom_row.addStretch()
        layout.addLayout(zoom_row)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_label = QLabel("No preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setWidget(self.preview_label)
        # Ctrl+wheel zooms the preview instead of scrolling it; middle-button
        # drag pans it.
        self.preview_scroll.viewport().installEventFilter(self)
        layout.addWidget(self.preview_scroll)
        return group

    def eventFilter(self, obj, event):
        if obj is not self.preview_scroll.viewport():
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self._zoom_in()
            else:
                self._zoom_out()
            return True

        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.MiddleButton:
            self._pan_dragging = True
            self._pan_last_pos = event.position().toPoint()
            self.preview_scroll.viewport().setCursor(Qt.ClosedHandCursor)
            return True

        if event.type() == QEvent.MouseMove and self._pan_dragging:
            pos = event.position().toPoint()
            delta = pos - self._pan_last_pos
            self._pan_last_pos = pos
            hbar = self.preview_scroll.horizontalScrollBar()
            vbar = self.preview_scroll.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
            return True

        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.MiddleButton:
            self._pan_dragging = False
            self.preview_scroll.viewport().unsetCursor()
            return True

        return super().eventFilter(obj, event)

    def _build_edit_panel(self):
        group = QGroupBox("Correct this page")
        layout = QVBoxLayout(group)

        form = QFormLayout()
        self.edit_u_number = QLineEdit()
        self.edit_dni = QLineEdit()
        self.edit_parcial = QLineEdit()
        self.edit_permut = QLineEdit()
        self.edit_grup = QLineEdit()
        form.addRow("U-Number:", self.edit_u_number)
        form.addRow("DNI:", self.edit_dni)
        form.addRow("PARCIAL:", self.edit_parcial)
        form.addRow("PERMUT:", self.edit_permut)
        form.addRow("GRUP:", self.edit_grup)
        layout.addLayout(form)

        self.matched_student_label = QLabel("Matched student: -")
        self.matched_student_label.setWordWrap(True)
        layout.addWidget(self.matched_student_label)
        self.edit_u_number.textChanged.connect(self._update_matched_student_preview)
        for field in (self.edit_u_number, self.edit_dni, self.edit_parcial,
                      self.edit_permut, self.edit_grup):
            field.textChanged.connect(self._mark_dirty)

        layout.addWidget(QLabel("Answers (click a letter to toggle mark):"))
        self.answers_table = QTableWidget(0, 10)
        self.answers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.answers_table.cellClicked.connect(self._toggle_answer_cell)
        layout.addWidget(self.answers_table, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.apply_btn = QPushButton("Apply correction")
        self.apply_btn.clicked.connect(self._apply_correction)
        layout.addWidget(self.apply_btn)

        btn_row = QHBoxLayout()
        self.revert_btn = QPushButton("Revert to original")
        self.revert_btn.setEnabled(False)
        self.revert_btn.clicked.connect(self._revert_to_original)
        self.rescan_btn = QPushButton("Rescan this page")
        self.rescan_btn.clicked.connect(self._rescan_page)
        btn_row.addWidget(self.revert_btn)
        btn_row.addWidget(self.rescan_btn)
        layout.addLayout(btn_row)
        return group

    # ----- Page loading -----

    def _current_result(self):
        return self.all_results[self.current_index]

    def _load_page(self, index):
        self.current_index = index
        r = self._current_result()
        total = len(self.all_results)
        self.page_label.setText(f"Page {r.get('page', index + 1)} / {total}")
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < total - 1)

        self.table.blockSignals(True)
        self.table.selectRow(index)
        self.table.blockSignals(False)

        self._render_preview(r)
        self._load_edit_form(r)

    def _render_preview(self, r):
        pdf_idx = self.pdf_page_index.get(self.current_index)
        self._base_pixmap = None
        self.zoom_out_btn.setEnabled(pdf_idx is not None)
        self.zoom_in_btn.setEnabled(pdf_idx is not None)
        self.zoom_fit_btn.setEnabled(pdf_idx is not None)
        if pdf_idx is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(
                f"No annotated PDF page available "
                f"(processing failed: {r.get('status', '?')})")
            self.zoom_label.setText("-")
            self._preview_request_idx = None
            return

        cached = self._preview_cache.get(pdf_idx)
        if cached is not None:
            self.preview_label.setText('')
            self._base_pixmap = cached
            self._preview_request_idx = None
            self._zoom_fit()
            return

        # Not cached: render off the UI thread (see _PreviewRenderWorker) so
        # browsing to a not-yet-seen page doesn't block the window while
        # poppler renders it.
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Loading preview...")
        self.zoom_label.setText("-")
        self._preview_request_idx = pdf_idx

        worker = _PreviewRenderWorker(self.pdf_path, pdf_idx, self.PREVIEW_DPI)
        worker.done.connect(self._on_preview_rendered)
        self._pending_preview_workers.append(worker)
        worker.start()

    def _on_preview_rendered(self, pdf_idx, qimage, err):
        if worker_sender := self.sender():
            if worker_sender in self._pending_preview_workers:
                self._pending_preview_workers.remove(worker_sender)

        # The user may have navigated to a different page while this was
        # rendering -- discard a result that no longer matches what's asked.
        if pdf_idx != self._preview_request_idx:
            return

        if err:
            self.preview_label.setText(f"Could not render preview:\n{err}")
            return

        pixmap = QPixmap.fromImage(qimage)
        if len(self._preview_cache) >= self.PREVIEW_CACHE_SIZE:
            self._preview_cache.pop(next(iter(self._preview_cache)))
        self._preview_cache[pdf_idx] = pixmap

        self.preview_label.setText('')
        self._base_pixmap = pixmap
        self._zoom_fit()

    # ----- Zoom controls -----

    def _apply_zoom(self):
        if self._base_pixmap is None or self._base_pixmap.isNull():
            return
        self._zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom))
        w = max(1, round(self._base_pixmap.width() * self._zoom))
        h = max(1, round(self._base_pixmap.height() * self._zoom))
        scaled = self._base_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.preview_label.setMinimumSize(scaled.size())
        self.zoom_label.setText(f"{round(self._zoom * 100)}%")

    def _zoom_in(self):
        self._zoom *= self.ZOOM_STEP
        self._apply_zoom()

    def _zoom_out(self):
        self._zoom /= self.ZOOM_STEP
        self._apply_zoom()

    def _zoom_fit(self):
        if self._base_pixmap is None or self._base_pixmap.isNull():
            return
        viewport = self.preview_scroll.viewport().size()
        if viewport.width() > 1 and viewport.height() > 1:
            self._zoom = min(viewport.width() / self._base_pixmap.width(),
                              viewport.height() / self._base_pixmap.height())
        else:
            self._zoom = 1.0
        self._apply_zoom()

    def _load_edit_form(self, r):
        editable = r.get('_corrected') is not None

        # setText()/setItem() below are programmatic, not user edits -- this
        # guard keeps them from tripping _mark_dirty() via textChanged.
        self._loading_form = True
        self.edit_u_number.setText(str(r.get('u_number') or ''))
        self.edit_dni.setText(str(r.get('dni') or ''))
        self.edit_parcial.setText(str(r.get('parcial') or ''))
        permut_val = r.get('permut')
        self.edit_permut.setText('' if permut_val is None else str(permut_val))
        self.edit_grup.setText(str(r.get('grup') or ''))
        for w in (self.edit_u_number, self.edit_dni, self.edit_parcial,
                  self.edit_permut, self.edit_grup):
            w.setEnabled(editable)

        self._update_matched_student_preview()
        self._load_answers_grid(r)
        self._loading_form = False
        self._form_dirty = False

        self.answers_table.setEnabled(editable)
        self._refresh_action_buttons()
        self._update_persist_indicator()

        if editable:
            self.status_label.setText("")
        else:
            self.status_label.setText(
                f"This page failed processing (status: {r.get('status', '?')}) "
                f"and has no bubble data to correct.")

    def _load_answers_grid(self, r):
        answers = r.get('answers', {})
        self.answers_table.setColumnCount(self.num_options)
        self.answers_table.setHorizontalHeaderLabels(omr.OPTION_LABELS[:self.num_options])
        self.answers_table.setRowCount(self.num_questions)
        self.answers_table.setVerticalHeaderLabels(
            [f"Q{q}" for q in range(1, self.num_questions + 1)])
        opts = omr.OPTION_LABELS[:self.num_options]
        for qi, q in enumerate(range(1, self.num_questions + 1)):
            marks = answers.get(q, {}).get('marks', set())
            for oi, opt in enumerate(opts):
                item = QTableWidgetItem(opt if opt in marks else '')
                item.setTextAlignment(Qt.AlignCenter)
                self.answers_table.setItem(qi, oi, item)

    def _update_matched_student_preview(self):
        u_clean = self.edit_u_number.text().strip().upper().replace('U', '')
        student = self.student_lookup.get(u_clean)
        if student is not None:
            name = (f"{student.get('Nom', '')} {student.get('Cognom1', '')} "
                     f"{student.get('Cognom2', '') or ''}").strip()
            self.matched_student_label.setText(f"Matched student: {name} (U{u_clean})")
        elif u_clean:
            self.matched_student_label.setText("Matched student: (no match)")
        else:
            self.matched_student_label.setText("Matched student: -")

    # ----- Answer grid editing -----

    def _toggle_answer_cell(self, row, col):
        item = self.answers_table.item(row, col)
        opt = omr.OPTION_LABELS[col]
        item.setText('' if item.text() == opt else opt)
        self._mark_dirty()

    def _collect_marks_from_grid(self):
        marks_by_q = {}
        opts = omr.OPTION_LABELS[:self.num_options]
        for qi, q in enumerate(range(1, self.num_questions + 1)):
            marks = set()
            for oi, opt in enumerate(opts):
                item = self.answers_table.item(qi, oi)
                if item is not None and item.text() == opt:
                    marks.add(opt)
            marks_by_q[q] = marks
        return marks_by_q

    # ----- Navigation -----

    def _go_prev(self):
        if self.current_index > 0:
            self._load_page(self.current_index - 1)

    def _go_next(self):
        if self.current_index < len(self.all_results) - 1:
            self._load_page(self.current_index + 1)

    def _on_table_row_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._load_page(rows[0].row())

    # ----- Apply correction -----

    def _snapshot_pre_edit(self, r):
        """Capture the as-read OCR state the first time this page is edited.

        Backs both the purple "manually changed" highlighting in the
        annotated PDF (omr_correct._is_manually_edited) and the "Revert to
        original" button -- and survives saving/reloading the review cache
        since it's just another key in the result dict.
        """
        if '_pre_edit' in r:
            return
        r['_pre_edit'] = {
            'u_number': r.get('u_number'),
            'u_status': r.get('u_status'),
            'dni': r.get('dni'),
            'parcial': r.get('parcial'),
            'permut': r.get('permut'),
            'grup': r.get('grup'),
            'answers_marks': {q: set(a.get('marks', set()))
                               for q, a in r.get('answers', {}).items()},
        }

    def _apply_correction(self):
        r = self._current_result()
        if r.get('_corrected') is None:
            return

        self._snapshot_pre_edit(r)

        u_clean = self.edit_u_number.text().strip().upper().replace('U', '')
        r['u_number'] = u_clean or None
        r['u_status'] = 'MANUAL'
        r['dni'] = self.edit_dni.text().strip()
        parcial = self.edit_parcial.text().strip()
        r['parcial'] = parcial or None
        permut = self.edit_permut.text().strip()
        r['permut'] = permut or None
        r['grup'] = self.edit_grup.text().strip() or None

        answers = r.setdefault('answers', {})
        for q, marks in self._collect_marks_from_grid().items():
            q_data = answers.setdefault(q, {})
            q_data['marks'] = marks
            q_data['status'] = 'OK'

        r['_manual_edit'] = True
        self._save_async(r)

    def _revert_to_original(self):
        r = self._current_result()
        pre = r.get('_pre_edit')
        if not pre:
            return

        reply = QMessageBox.question(
            self, "Revert to original",
            "Discard manual corrections on this page and restore the "
            "original OCR reading? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        r['u_number'] = pre['u_number']
        r['u_status'] = pre['u_status']
        r['dni'] = pre['dni']
        r['parcial'] = pre['parcial']
        r['permut'] = pre['permut']
        r['grup'] = pre['grup']
        answers = r.setdefault('answers', {})
        for q, marks in pre['answers_marks'].items():
            q_data = answers.setdefault(q, {})
            q_data['marks'] = set(marks)
            q_data['status'] = 'OK'

        r['_manual_edit'] = False
        del r['_pre_edit']
        self._save_async(r)

    # ----- Background save (write_excel + patch PDF page + cache) -----

    def _refresh_action_buttons(self):
        """Re-derive Apply/Revert/Rescan enabled-state for whichever page is
        currently displayed.

        Used both by _load_edit_form() and by save-completion handlers that
        may fire for a page other than the one on screen -- in the latter
        case, this updates the *visible* page's buttons without touching its
        form fields or dirty flag (see _on_local_save_done).
        """
        r = self._current_result()
        editable = r.get('_corrected') is not None
        # _local_busy is global (it guards the shared local scratch files,
        # not a single page), so Apply/Revert stay disabled for every page
        # while any save is in flight, not just the page that triggered it.
        self.apply_btn.setEnabled(editable and not self._local_busy)
        self.revert_btn.setEnabled(editable and bool(r.get('_pre_edit')) and not self._local_busy)
        self.rescan_btn.setEnabled(not self._local_busy)

    def _update_persist_indicator(self):
        """Orange = something Apply/Revert/Rescan touched hasn't fully
        reached the output folder yet (local save and/or cloud sync still
        in flight). Default styling = everything is persisted.
        """
        pending = (self._local_busy or bool(self._pending_sync_workers)
                   or self._sync_failed or self._form_dirty)
        self.apply_btn.setStyleSheet(self.UNSAVED_STYLE if pending else "")

    def _mark_dirty(self):
        if self._loading_form:
            return
        self._form_dirty = True
        self._update_persist_indicator()

    def _save_async(self, r):
        if self._local_busy:
            QMessageBox.information(
                self, "Save in progress",
                "A previous save is still running. Please wait a moment and try again.")
            return

        page_index = self.current_index
        pdf_idx = self.pdf_page_index.get(page_index)
        self._local_busy = True
        self._update_persist_indicator()
        self._refresh_action_buttons()  # disables Apply/Revert/Rescan globally
        self.status_label.setText("Saving...")

        worker = _SaveWorker(self.all_results, self.students_df, self.correct_answers_by_perm,
                              self.num_questions, self.num_options, self.excel_path, self.pdf_path,
                              r, pdf_idx, self.cache_path, self.exam_pdf_path, self.source_dpi,
                              self.synced_excel_path, self.synced_pdf_path, self.synced_cache_path)
        worker.local_done.connect(lambda err: self._on_local_save_done(err, page_index, pdf_idx))
        worker.synced.connect(lambda err, w=worker: self._on_synced(err, w))
        self._pending_sync_workers.append(worker)
        worker.start()

    def _on_local_save_done(self, err, page_index, pdf_idx):
        # The slow part (copying back to the cloud-synced path) is still
        # running on `worker`, but the local save this UI update reflects is
        # already durable on disk -- so it's safe to unblock editing now
        # rather than make the user wait for the cloud upload too.
        self._local_busy = False
        if pdf_idx is not None:
            self._preview_cache.pop(pdf_idx, None)

        # IMPORTANT: only touch the edit form (and the status line driven by
        # it) when the page that just finished saving is still the one on
        # screen. The user may have navigated to a different page and
        # started an unrelated, unsaved edit there while this save was
        # running in the background -- unconditionally reloading the form
        # here would silently discard that in-progress edit and clear its
        # "unsaved changes" indicator. _refresh_action_buttons() still
        # re-derives button state for whichever page IS showing, since those
        # were blanket-disabled for every page while _local_busy was True.
        if page_index != self.current_index:
            self._refresh_action_buttons()
            self._update_persist_indicator()
            if err:
                QMessageBox.critical(self, "Could not save correction", err)
            else:
                r = self.all_results[page_index]
                self._fill_table_row(page_index, r)
            return

        if err:
            QMessageBox.critical(self, "Could not save correction", err)
            self._load_edit_form(self._current_result())
            self.status_label.setText("Save failed - see error dialog.")
            return

        r = self.all_results[page_index]
        self._fill_table_row(page_index, r)
        self._render_preview(r)
        # _load_edit_form() resets the status line (e.g. to "" for an
        # editable page), so it must run BEFORE the "syncing" message below,
        # not after -- otherwise it immediately clobbers it.
        self._load_edit_form(self._current_result())
        self.status_label.setText("Correction saved. Syncing to output folder...")

    def _on_synced(self, err, worker):
        if worker in self._pending_sync_workers:
            self._pending_sync_workers.remove(worker)
        self._sync_failed = bool(err)
        self._update_persist_indicator()

        if err:
            self.status_label.setText(
                "Saved locally, but syncing to the output folder failed: " + err)
            return
        # Only overwrite the status line if it's still showing this same
        # save's "syncing..." message -- the user may have already made and
        # seen the result of another edit by the time this arrives.
        if self.status_label.text().startswith("Correction saved. Syncing"):
            self.status_label.setText("Correction saved and synced.")

    # ----- Rescan -----

    def _rescan_page(self):
        if self._local_busy:
            QMessageBox.information(
                self, "Save in progress",
                "A previous save is still running. Please wait a moment and try again.")
            return

        r = self._current_result()
        page_num = r.get('page')
        if page_num is None:
            return

        if not self.exam_pdf_path or not os.path.exists(self.exam_pdf_path):
            path, _ = QFileDialog.getOpenFileName(
                self, "Select the original scanned exam PDF", "", "PDF files (*.pdf)")
            if not path:
                return
            self.exam_pdf_path = path

        reply = QMessageBox.question(
            self, "Rescan page",
            f"Re-run OCR on page {page_num} from the original scan?\n"
            "Any manual corrections made to this page will be discarded.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.status_label.setText("Rescanning...")
        self._local_busy = True  # blocks a concurrent Apply/Revert/Rescan for the duration
        self._refresh_action_buttons()
        QApplication.processEvents()
        try:
            dpi = self.source_dpi or omr.detect_pdf_dpi(self.exam_pdf_path)
            pages = convert_from_path(self.exam_pdf_path, dpi=dpi,
                                       first_page=page_num, last_page=page_num)
            new_r, _ = omr.process_page(pages[0], page_num, self.num_questions,
                                         self.num_options, source_dpi=dpi)
        except Exception as e:
            self._local_busy = False
            self._refresh_action_buttons()
            QMessageBox.critical(self, "Rescan failed", str(e))
            self.status_label.setText("Rescan failed - see error dialog.")
            return

        page_index = self.current_index
        had_pdf_page = self.pdf_page_index.get(page_index) is not None
        has_pdf_page = new_r.get('_corrected') is not None
        self.all_results[page_index] = new_r
        self._fill_table_row(page_index, new_r)
        if page_index == self.current_index:
            self._load_edit_form(new_r)

        if has_pdf_page == had_pdf_page:
            # Common case: same set of pages inside annotated_review.pdf, so
            # the usual single-page background save applies unchanged.
            # _save_async() re-checks _local_busy itself; release it first so
            # that check (and the save it guards) can actually proceed.
            self._local_busy = False
            self._save_async(new_r)
            self.status_label.setText("Page rescanned, saving...")
            return

        # Rare case: the set of pages inside annotated_review.pdf changes
        # (a page that used to fail now succeeds, or vice versa), so every
        # page's index inside it has to be remapped, not just this one --
        # cheapest correct fix is a full local regeneration before
        # publishing back to the synced path. _local_busy is already True
        # from above, so a concurrent Apply/Revert/Rescan can't race this.
        try:
            omr.write_excel(self.all_results, self.students_df, self.correct_answers_by_perm,
                             self.excel_path, self.num_questions, self.num_options)
            omr.write_annotated_pdf(self.all_results, self.pdf_path, students_df=self.students_df)
            self._recompute_pdf_page_index()
            self._preview_cache.clear()
            if self.cache_path:
                omr.save_review_cache(self.all_results, self.students_df, self.correct_answers_by_perm,
                                       self.num_questions, self.num_options,
                                       self.excel_path, self.pdf_path, self.cache_path,
                                       exam_pdf_path=self.exam_pdf_path, dpi=self.source_dpi)
            _copy_with_retry(self.excel_path, self.synced_excel_path)
            _copy_with_retry(self.pdf_path, self.synced_pdf_path)
            if self.cache_path and self.synced_cache_path:
                _copy_with_retry(self.cache_path, self.synced_cache_path)
        except Exception as e:
            self._local_busy = False
            self._sync_failed = True
            self._update_persist_indicator()
            self._refresh_action_buttons()
            QMessageBox.critical(self, "Could not save rescanned page", str(e))
            self.status_label.setText("Save failed - see error dialog.")
            return

        self._local_busy = False
        self._sync_failed = False
        self._update_persist_indicator()
        self._refresh_action_buttons()
        if page_index == self.current_index:
            self._render_preview(new_r)
        self.status_label.setText("Page rescanned.")
