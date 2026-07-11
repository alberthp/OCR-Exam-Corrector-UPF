"""Dialogs for emailing a student their exported review PDF from the
review screen: one-time Gmail settings, and a per-send preview/confirm
step. See email_utils.py for the actual SMTP send and credential storage.
"""

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QDialogButtonBox, QCheckBox, QMessageBox,
)

import email_utils as emu


class _TestConnectionWorker(QThread):
    """Verifies address/App Password can authenticate, off the UI thread --
    an SMTP handshake can take a few seconds and must not freeze the dialog.
    """
    done = Signal(str)  # '' on success, else an error message

    def __init__(self, address, app_password):
        super().__init__()
        self.address = address
        self.app_password = app_password

    def run(self):
        try:
            emu.test_connection(self.address, self.app_password)
            self.done.emit('')
        except Exception as e:
            self.done.emit(str(e))


class _SendEmailWorker(QThread):
    """Sends the email off the UI thread, for the same reason."""
    done = Signal(str)  # '' on success, else an error message

    def __init__(self, address, app_password, to_email, subject, body,
                 attachment_path, attachment_filename, sender_name, cc_self):
        super().__init__()
        self.args = (address, app_password, to_email, subject, body,
                     attachment_path, attachment_filename)
        self.kwargs = dict(sender_name=sender_name, cc_self=cc_self)

    def run(self):
        try:
            emu.send_email_with_attachment(*self.args, **self.kwargs)
            self.done.emit('')
        except Exception as e:
            self.done.emit(str(e))


class EmailSettingsDialog(QDialog):
    """One-time (or as-needed) setup: Gmail address + App Password, sender
    display name, and the subject/body templates used to prefill every
    send. The App Password field is left blank on open even if one is
    already saved (see _load_into_form) -- the dialog never redisplays a
    stored secret, only lets you overwrite it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Email settings")
        self.resize(560, 480)
        self._had_saved_password = False
        self._test_worker = None
        self._build_ui()
        self._load_into_form()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("yourname@upf.edu")
        form.addRow("Gmail address:", self.address_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        form.addRow("App Password:", self.password_edit)

        self.sender_name_edit = QLineEdit()
        self.sender_name_edit.setPlaceholderText("e.g. Albert Hernansanz")
        form.addRow("Sender name:", self.sender_name_edit)

        self.cc_self_check = QCheckBox("Send myself a Cc of every email")
        form.addRow("", self.cc_self_check)

        layout.addLayout(form)

        hint = QLabel(
            '<a href="https://myaccount.google.com/apppasswords">'
            "Get an App Password</a> from your Google Account "
            "(Security &rarr; 2-Step Verification &rarr; App passwords). "
            "This requires 2-Step Verification to be turned on, and is a "
            "separate, revocable credential -- not your normal Gmail "
            "password, which Gmail's SMTP rejects outright once 2-Step "
            "Verification is enabled."
        )
        hint.setOpenExternalLinks(True)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        layout.addWidget(QLabel("Subject template:"))
        self.subject_edit = QLineEdit()
        layout.addWidget(self.subject_edit)

        layout.addWidget(QLabel("Body template:"))
        self.body_edit = QTextEdit()
        layout.addWidget(self.body_edit, stretch=1)

        fields_hint = QLabel(
            "Available placeholders: " +
            ", ".join(f"{{{f}}}" for f in emu.TEMPLATE_FIELDS)
        )
        fields_hint.setWordWrap(True)
        fields_hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(fields_hint)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(self.test_btn)
        self.test_status_label = QLabel("")
        test_row.addWidget(self.test_status_label, stretch=1)
        layout.addLayout(test_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._save_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_into_form(self):
        settings = emu.load_email_settings()
        self.address_edit.setText(settings['address'])
        self.sender_name_edit.setText(settings['sender_name'])
        self.subject_edit.setText(settings['subject_template'])
        self.body_edit.setPlainText(settings['body_template'])
        self.cc_self_check.setChecked(bool(settings.get('cc_self')))
        self._had_saved_password = bool(emu.load_app_password(settings['address']))
        self.password_edit.setPlaceholderText(
            "(leave blank to keep the saved password)" if self._had_saved_password
            else "paste the 16-character App Password")

    def _test_connection(self):
        address = self.address_edit.text().strip()
        password = self.password_edit.text().strip() or emu.load_app_password(address)
        if not address or not password:
            QMessageBox.warning(self, "Missing info",
                                 "Enter both the Gmail address and the App Password first.")
            return
        self.test_btn.setEnabled(False)
        self.test_status_label.setText("Testing...")
        self._test_worker = _TestConnectionWorker(address, password)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_done(self, err):
        self.test_btn.setEnabled(True)
        if err:
            self.test_status_label.setText("Failed - see error dialog.")
            QMessageBox.critical(self, "Connection failed", err)
        else:
            self.test_status_label.setText("Connection OK.")

    def _save_and_accept(self):
        address = self.address_edit.text().strip()
        if not address:
            QMessageBox.warning(self, "Missing address", "Enter your Gmail address.")
            return

        password = self.password_edit.text().strip()
        if not password and not self._had_saved_password:
            QMessageBox.warning(
                self, "Missing App Password",
                "Enter an App Password (see the link above), or leave the "
                "field blank only if one is already saved for this address.")
            return

        settings = {
            'address': address,
            'sender_name': self.sender_name_edit.text().strip(),
            'subject_template': self.subject_edit.text(),
            'body_template': self.body_edit.toPlainText(),
            'cc_self': self.cc_self_check.isChecked(),
        }
        emu.save_email_settings(settings)
        if password:
            emu.save_app_password(address, password)
        self.accept()


class EmailPreviewDialog(QDialog):
    """Shown before every send: recipient/subject/body are all editable
    (pre-filled from the saved templates), so nothing goes out without a
    look -- this is the "lowest risk of sending the wrong PDF to the wrong
    student" step called out when this feature was scoped.
    """

    def __init__(self, to_email, subject, body, attachment_filename,
                 address, app_password, sender_name, cc_self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send review PDF by email")
        self.resize(560, 440)
        self.address = address
        self.app_password = app_password
        self.sender_name = sender_name
        self.cc_self = cc_self
        self.attachment_path = None  # set by the caller before exec()
        self._send_worker = None
        self._sent_ok = False
        self._build_ui(to_email, subject, body, attachment_filename)

    def _build_ui(self, to_email, subject, body, attachment_filename):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.to_edit = QLineEdit(to_email)
        form.addRow("To:", self.to_edit)
        self.subject_edit = QLineEdit(subject)
        form.addRow("Subject:", self.subject_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Body:"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlainText(body)
        layout.addWidget(self.body_edit, stretch=1)

        attach_label = QLabel(f"Attachment: {attachment_filename}")
        attach_label.setStyleSheet("color: #888;")
        layout.addWidget(attach_label)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.send_btn)
        layout.addLayout(btn_row)

    def _send(self):
        to_email = self.to_edit.text().strip()
        if not to_email:
            QMessageBox.warning(self, "Missing recipient", "Enter a recipient email address.")
            return
        if self.attachment_path is None:
            QMessageBox.critical(self, "No attachment", "No PDF was generated to attach.")
            return

        self.send_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Sending...")

        self._send_worker = _SendEmailWorker(
            self.address, self.app_password, to_email,
            self.subject_edit.text(), self.body_edit.toPlainText(),
            self.attachment_path, os.path.basename(self.attachment_path),
            self.sender_name, self.cc_self,
        )
        self._send_worker.done.connect(self._on_send_done)
        self._send_worker.start()

    def _on_send_done(self, err):
        if err:
            self.send_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            self.status_label.setText("Send failed - see error dialog.")
            QMessageBox.critical(self, "Send failed", err)
            return
        self._sent_ok = True
        self.accept()
