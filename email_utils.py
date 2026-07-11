#!/usr/bin/env python3
"""
Email sending for student review-PDF exports, via Gmail SMTP.
================================================================

Lets the review screen attach a student's exported review PDF to an email
and send it straight from the app, using the same Gmail account the user
already reads in a browser (smtp.gmail.com accepts App Password auth for
any Gmail/Google Workspace account with 2-Step Verification enabled --
no separate email-sending service or OAuth app registration needed).

Credential storage is split deliberately:
  - The Gmail address, sender display name, and subject template are NOT
    secret -- cached in a small JSON file.
  - The body template is also not secret, but lives in its OWN plain .txt
    file rather than inside the JSON blob -- so it can be opened and
    edited directly with any text editor (Notepad, etc.), not just through
    the settings dialog's text box. Both paths write the same file, so
    whichever one was used last wins.
  - The App Password IS secret -- stored via the `keyring` package, which
    hands it to the OS's native credential store (Windows Credential
    Manager / macOS Keychain / Linux Secret Service), never written to a
    plaintext file.

Both matter more than usual here because this project's folder can live
inside a cloud-sync directory (e.g. Google Drive's "Mi unidad") -- a
plaintext credentials file sitting next to the code would get silently
uploaded to the cloud. The JSON settings file and the body-template .txt
file are both written to the OS's per-user local config directory instead
of the project folder for the same reason, and the password never touches
disk as plaintext at all.
"""

import os
import re
import sys
import json
import smtplib
import ssl
from email.message import EmailMessage

APP_NAME = "OMRExamCorrector"
KEYRING_SERVICE = "omr_exam_corrector_gmail"

# The exam session a run belongs to -- set once per run (New exam screen)
# or corrected later (Review screen), and substituted into the email via
# the {exam_type} placeholder. Not tied to any specific PARCIAL numbering
# since different courses number their parts differently.
EXAM_TYPES = ['Midterm', 'Final', 'Retake']

DEFAULT_SUBJECT_TEMPLATE = "{exam_type} exam review - {nom} {cognom1}"
DEFAULT_BODY_TEMPLATE = (
    "Dear {nom} {cognom1},\n"
    "\n"
    "Please find attached the review of your {exam_type} exam "
    "(U-Number: U{u_number}, Group: {grup}).\n"
    "\n"
    "Best regards,\n"
)

# Every token fill_template() will substitute, shown in the settings dialog
# so the subject/body templates are self-documenting.
TEMPLATE_FIELDS = [
    'nom', 'cognom1', 'cognom2', 'u_number', 'dni', 'grup', 'parcial',
    'permutacio', 'exam_type',
]


def _config_dir():
    """OS-appropriate per-user local config directory -- deliberately NOT
    derived from the project's own location, since that may be inside a
    cloud-synced folder (see module docstring).
    """
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def _settings_path():
    return os.path.join(_config_dir(), 'email_settings.json')


def _body_template_path():
    return os.path.join(_config_dir(), 'email_body_template.txt')


def load_body_template():
    """The email body template, read from its own plain .txt file.

    Kept separate from email_settings.json specifically so it can be
    opened and edited directly in Notepad/TextEdit/etc. (see
    open_body_template_file()), not just through the settings dialog.
    """
    path = _body_template_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except OSError:
            pass
    return DEFAULT_BODY_TEMPLATE


def save_body_template(text):
    with open(_body_template_path(), 'w', encoding='utf-8') as f:
        f.write(text)


def open_body_template_file():
    """Opens the body-template .txt file in the OS's default text editor,
    creating it from the current template first if it doesn't exist yet
    (otherwise there would be nothing to open on a fresh machine).
    """
    path = _body_template_path()
    if not os.path.exists(path):
        save_body_template(load_body_template())
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        import subprocess
        subprocess.Popen(['open', path])
    else:
        import subprocess
        subprocess.Popen(['xdg-open', path])
    return path


def load_email_settings():
    """Non-secret settings (address, sender name, subject template, and the
    body template read from its .txt file -- see load_body_template()). The
    App Password is never in this dict -- see load_app_password().
    """
    defaults = {
        'address': '',
        'sender_name': '',
        'subject_template': DEFAULT_SUBJECT_TEMPLATE,
        'cc_self': False,
    }
    path = _settings_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("settings file did not contain a JSON object")
            defaults.update(data)
        except (json.JSONDecodeError, ValueError, OSError):
            # A corrupted or unreadable settings file (interrupted write,
            # manual edit gone wrong, disk issue) used to crash every
            # caller -- opening "Email settings..." and clicking "Send by
            # email..." both go through this function. Falling back to
            # defaults just means the user re-enters their settings once,
            # instead of the feature being permanently broken until someone
            # finds and deletes a file most users don't know exists.
            pass
    # Legacy migration: versions before the .txt file existed stored
    # body_template inside this JSON blob. If a stale copy is still there
    # and no .txt file has been written yet, seed the .txt file from it
    # once so an existing custom template isn't silently dropped.
    legacy_body = defaults.pop('body_template', None)
    if legacy_body and not os.path.exists(_body_template_path()):
        save_body_template(legacy_body)
    defaults['body_template'] = load_body_template()
    return defaults


def save_email_settings(settings):
    """Persist the non-secret settings dict (see load_email_settings).

    body_template is split out and written to its own .txt file (see
    save_body_template()) rather than into the JSON blob.
    """
    settings = dict(settings)
    body_template = settings.pop('body_template', None)
    if body_template is not None:
        save_body_template(body_template)
    with open(_settings_path(), 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def load_app_password(address):
    """Returns the stored App Password for `address`, or None if nothing's
    saved yet for that address (a fresh machine, or the address changed).
    """
    if not address:
        return None
    import keyring
    return keyring.get_password(KEYRING_SERVICE, address)


def save_app_password(address, app_password):
    import keyring
    keyring.set_password(KEYRING_SERVICE, address, app_password)


def delete_app_password(address):
    import keyring
    import keyring.errors
    try:
        keyring.delete_password(KEYRING_SERVICE, address)
    except keyring.errors.PasswordDeleteError:
        pass  # nothing was stored for this address -- fine


_PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')


def fill_template(template, fields):
    """Replace every {token} in `template` with fields[token]; a token not
    in `fields` is left as literal text instead of raising.

    Deliberately a plain regex substitution, not str.format_map(): the
    subject/body templates are free text a non-programmer edits in a
    dialog box, and str.format()'s mini-language treats any stray '{' or
    '}' typed for an unrelated reason (emphasis, a literal set like
    "{A,B,C}") as a syntax error -- confirmed by testing: "{nom" or "nom}"
    alone crash format_map() with ValueError, and "{0}" crashes it with
    "Format string contains positional fields". Regex substitution just
    doesn't match text that isn't exactly {word}, so none of that can
    happen; as a side benefit it also can't evaluate {token.attr}-style
    attribute access the way format_map() would.
    """
    def repl(m):
        key = m.group(1)
        return str(fields[key]) if key in fields else m.group(0)
    return _PLACEHOLDER_RE.sub(repl, template)


def template_fields_for_page(r, matched_student, exam_type=''):
    """Build the {token: value} dict fill_template() substitutes, from a
    page's result dict and its matched student row (either may be partial;
    every field defaults to '' rather than raising).

    exam_type is not part of the page/student data -- it's a whole-run
    setting (see EXAM_TYPES), passed in separately by the caller.
    """
    matched_student = matched_student if matched_student is not None else {}
    permut_val = r.get('permut')
    return {
        'nom': str(matched_student.get('Nom', '') or ''),
        'cognom1': str(matched_student.get('Cognom1', '') or ''),
        'cognom2': str(matched_student.get('Cognom2', '') or ''),
        'u_number': str(r.get('u_number') or '').split('|')[0],
        'dni': str(r.get('dni') or ''),
        'grup': str(r.get('grup') or ''),
        'parcial': str(r.get('parcial') or ''),
        'permutacio': '' if permut_val is None else str(permut_val),
        'exam_type': str(exam_type or ''),
    }


def send_email_with_attachment(address, app_password, to_email, subject, body,
                                attachment_path, attachment_filename,
                                sender_name=None, cc_self=False):
    """Send one email via Gmail SMTP (smtp.gmail.com:587, STARTTLS) with a
    single file attached.

    `app_password` must be a Google Account "App Password" (a 16-character,
    single-purpose, independently revocable credential -- Settings > Security
    > 2-Step Verification > App passwords), not the account's normal login
    password: Gmail's SMTP rejects the real password outright once 2-Step
    Verification is on, and an app password is a much smaller blast radius
    to store/leak than the account's actual password.

    Raises on any failure (bad credentials, network error, etc.) -- the
    caller is expected to catch and show it, not swallow it silently.
    """
    msg = EmailMessage()
    msg['From'] = f"{sender_name} <{address}>" if sender_name else address
    msg['To'] = to_email
    if cc_self:
        msg['Cc'] = address
    msg['Subject'] = subject
    msg.set_content(body)

    with open(attachment_path, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='pdf',
                            filename=attachment_filename)

    context = ssl.create_default_context()
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
        server.starttls(context=context)
        server.login(address, app_password)
        server.send_message(msg)


def test_connection(address, app_password):
    """Verifies the address/App Password combination can actually
    authenticate, without sending anything -- used by the settings
    dialog's "Test connection" button so a typo'd password is caught
    immediately instead of on the next real send.
    """
    context = ssl.create_default_context()
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
        server.starttls(context=context)
        server.login(address, app_password)
