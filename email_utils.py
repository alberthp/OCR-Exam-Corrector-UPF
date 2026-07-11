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
  - The Gmail address, sender display name, and subject/body templates are
    NOT secret -- cached in a small JSON file.
  - The App Password IS secret -- stored via the `keyring` package, which
    hands it to the OS's native credential store (Windows Credential
    Manager / macOS Keychain / Linux Secret Service), never written to a
    plaintext file.

Both matter more than usual here because this project's folder can live
inside a cloud-sync directory (e.g. Google Drive's "Mi unidad") -- a
plaintext credentials file sitting next to the code would get silently
uploaded to the cloud. The JSON settings file is written to the OS's
per-user local config directory instead of the project folder for the
same reason, and the password never touches disk as plaintext at all.
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

DEFAULT_SUBJECT_TEMPLATE = "Revisio d'examen - {nom} {cognom1}"
DEFAULT_BODY_TEMPLATE = (
    "Hola {nom},\n"
    "\n"
    "T'adjunto la revisio del teu examen (Grup {grup}, Parcial {parcial}, "
    "Permutacio {permutacio}).\n"
    "\n"
    "Salutacions,\n"
)

# Every token fill_template() will substitute, shown in the settings dialog
# so the subject/body templates are self-documenting.
TEMPLATE_FIELDS = [
    'nom', 'cognom1', 'cognom2', 'u_number', 'dni', 'grup', 'parcial', 'permutacio',
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


def load_email_settings():
    """Non-secret settings only (address, sender name, templates). The App
    Password is never in this dict -- see load_app_password().
    """
    defaults = {
        'address': '',
        'sender_name': '',
        'subject_template': DEFAULT_SUBJECT_TEMPLATE,
        'body_template': DEFAULT_BODY_TEMPLATE,
        'cc_self': False,
    }
    path = _settings_path()
    if not os.path.exists(path):
        return defaults
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("settings file did not contain a JSON object")
    except (json.JSONDecodeError, ValueError, OSError):
        # A corrupted or unreadable settings file (interrupted write, manual
        # edit gone wrong, disk issue) used to crash every caller --
        # opening "Email settings..." and clicking "Send by email..." both
        # go through this function. Falling back to defaults just means the
        # user re-enters their settings once, instead of the feature being
        # permanently broken until someone finds and deletes a file most
        # users don't know exists.
        return defaults
    defaults.update(data)
    return defaults


def save_email_settings(settings):
    """Persist the non-secret settings dict (see load_email_settings)."""
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


def template_fields_for_page(r, matched_student):
    """Build the {token: value} dict fill_template() substitutes, from a
    page's result dict and its matched student row (either may be partial;
    every field defaults to '' rather than raising).
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
