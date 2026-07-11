"""email_utils.py: template substitution, settings persistence, and
keyring-backed credential storage.

Every test isolates itself from the REAL settings file
(%APPDATA%/OMRExamCorrector/email_settings.json) and the real OS keyring
entry via monkeypatching -- this suite must never read or overwrite the
user's actual configured Gmail address/App Password, whether or not
they've been set up yet.

Includes permanent regression tests for two bugs found during the v1.4
stress-testing pass: fill_template() crashed on a stray brace, and a
corrupted settings file crashed the whole email feature.
"""

import json
import os

import pytest

import email_utils as emu


@pytest.fixture
def isolated_email_config(tmp_path, monkeypatch):
    """Redirects settings-file and keyring-service lookups into a
    throwaway location for the duration of one test."""
    monkeypatch.setattr(emu, "_config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(emu, "KEYRING_SERVICE", "omr_test_service_isolated")
    return tmp_path


# ----- fill_template -----

def test_fill_template_substitutes_known_fields():
    result = emu.fill_template("Hola {nom}, grup {grup}", {"nom": "Alice", "grup": "1"})
    assert result == "Hola Alice, grup 1"


def test_fill_template_leaves_unknown_token_as_literal():
    result = emu.fill_template("Hola {nom} {unknown_field}", {"nom": "Alice"})
    assert result == "Hola Alice {unknown_field}"


def test_fill_template_unbalanced_open_brace_does_not_crash():
    """Regression test: str.format_map() raised ValueError on '{nom'
    (missing closing brace) -- very plausible in free text a
    non-programmer edits in a dialog box."""
    result = emu.fill_template("Note: {nom", {"nom": "Alice"})
    assert result == "Note: {nom"


def test_fill_template_unbalanced_close_brace_does_not_crash():
    result = emu.fill_template("score} for {nom}", {"nom": "Alice"})
    assert result == "score} for Alice"


def test_fill_template_positional_field_does_not_crash():
    result = emu.fill_template("{0} {nom}", {"nom": "Alice"})
    assert result == "{0} Alice"


def test_fill_template_does_not_evaluate_attribute_access():
    """str.format_map() would evaluate {nom.__class__} as real attribute
    access; the regex-based implementation must not."""
    result = emu.fill_template("{nom.__class__}", {"nom": "Alice"})
    assert result == "{nom.__class__}"


def test_fill_template_empty_template():
    assert emu.fill_template("", {"nom": "Alice"}) == ""


def test_fill_template_unicode_and_emoji():
    result = emu.fill_template("Hola {nom}", {"nom": "José 😀"})
    assert result == "Hola José 😀"


# ----- template_fields_for_page -----

def test_template_fields_for_page_empty_inputs():
    fields = emu.template_fields_for_page({}, None)
    assert fields == {
        "nom": "", "cognom1": "", "cognom2": "", "u_number": "",
        "dni": "", "grup": "", "parcial": "", "permutacio": "", "exam_type": "",
    }


def test_template_fields_for_page_permut_zero_is_not_blanked():
    """permut=0 is a real, falsy-but-valid permutation value -- must render
    as '0', not be treated as missing and become ''."""
    fields = emu.template_fields_for_page({"permut": 0}, {})
    assert fields["permutacio"] == "0"


def test_template_fields_for_page_pulls_from_matched_student():
    r = {"u_number": "000001", "dni": "1", "grup": "1", "parcial": "1", "permut": 2}
    student = {"Nom": "Alice", "Cognom1": "Example", "Cognom2": "Smith"}
    fields = emu.template_fields_for_page(r, student)
    assert fields["nom"] == "Alice"
    assert fields["permutacio"] == "2"


def test_template_fields_for_page_includes_exam_type():
    fields = emu.template_fields_for_page({}, None, exam_type="Retake")
    assert fields["exam_type"] == "Retake"


def test_exam_types_constant():
    assert emu.EXAM_TYPES == ["Midterm", "Final", "Retake"]


# ----- Settings persistence -----

def test_load_settings_defaults_when_no_file_exists(isolated_email_config):
    settings = emu.load_email_settings()
    assert settings["address"] == ""
    assert settings["subject_template"] == emu.DEFAULT_SUBJECT_TEMPLATE


def test_save_and_load_settings_round_trip(isolated_email_config):
    settings = emu.load_email_settings()
    settings["address"] = "test@upf.edu"
    settings["sender_name"] = "Test Sender"
    emu.save_email_settings(settings)

    reloaded = emu.load_email_settings()
    assert reloaded["address"] == "test@upf.edu"
    assert reloaded["sender_name"] == "Test Sender"


def test_corrupted_settings_file_falls_back_to_defaults(isolated_email_config):
    """Regression test: a corrupted/unreadable settings file (interrupted
    write, manual edit gone wrong) used to raise JSONDecodeError
    unhandled, permanently breaking both 'Email settings...' and
    'Send by email...' until someone found and deleted a file most users
    don't know exists."""
    settings_path = isolated_email_config / "email_settings.json"
    settings_path.write_text("{not valid json!!!", encoding="utf-8")

    settings = emu.load_email_settings()
    assert settings["address"] == ""  # fell back to defaults, didn't raise


def test_settings_file_wrong_json_type_falls_back_to_defaults(isolated_email_config):
    settings_path = isolated_email_config / "email_settings.json"
    settings_path.write_text("[1, 2, 3]", encoding="utf-8")

    settings = emu.load_email_settings()
    assert settings["address"] == ""


# ----- Body template .txt file -----

def test_load_body_template_defaults_when_no_file_exists(isolated_email_config):
    assert emu.load_body_template() == emu.DEFAULT_BODY_TEMPLATE


def test_save_and_load_body_template_round_trip(isolated_email_config):
    emu.save_body_template("Custom body {nom}")
    assert emu.load_body_template() == "Custom body {nom}"


def test_body_template_is_a_plain_txt_file_not_inside_the_json(isolated_email_config):
    """The whole point of splitting it out: it must be directly editable
    with a plain text editor, not buried in a JSON blob."""
    emu.save_body_template("Custom body {nom}")
    txt_path = isolated_email_config / "email_body_template.txt"
    assert txt_path.exists()
    assert txt_path.read_text(encoding="utf-8") == "Custom body {nom}"


def test_save_email_settings_does_not_duplicate_body_template_into_json(isolated_email_config):
    settings = emu.load_email_settings()
    settings["body_template"] = "Custom body {nom}"
    emu.save_email_settings(settings)

    settings_path = isolated_email_config / "email_settings.json"
    on_disk = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "body_template" not in on_disk

    reloaded = emu.load_email_settings()
    assert reloaded["body_template"] == "Custom body {nom}"


def test_legacy_json_body_template_migrates_to_txt_file(isolated_email_config):
    """Versions before the .txt file existed stored body_template inside
    email_settings.json -- a settings file left over from one of those
    must not silently lose its custom template the first time this newer
    code reads it."""
    settings_path = isolated_email_config / "email_settings.json"
    settings_path.write_text(
        json.dumps({"address": "test@upf.edu", "body_template": "Old-style {nom}"}),
        encoding="utf-8")

    settings = emu.load_email_settings()
    assert settings["body_template"] == "Old-style {nom}"
    assert (isolated_email_config / "email_body_template.txt").read_text(encoding="utf-8") == "Old-style {nom}"


def test_open_body_template_file_creates_default_file_if_missing(isolated_email_config, monkeypatch):
    monkeypatch.setattr(os, "startfile", lambda p: None, raising=False)
    path = emu.open_body_template_file()
    assert os.path.exists(path)
    assert emu.load_body_template() == emu.DEFAULT_BODY_TEMPLATE


def test_config_dir_is_never_the_project_folder():
    """The real (non-monkeypatched) _config_dir() must resolve outside the
    project tree -- this project can live inside a cloud-synced directory
    (Google Drive's "Mi unidad"), so a settings/credentials file written
    next to the code would get silently uploaded to the cloud."""
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(emu.__file__)))
    assert not emu._config_dir().startswith(project_root)


# ----- keyring-backed App Password storage -----

def test_password_round_trip(isolated_email_config):
    emu.save_app_password("test@upf.edu", "fake-app-password-1234")
    assert emu.load_app_password("test@upf.edu") == "fake-app-password-1234"


def test_password_special_characters_round_trip(isolated_email_config):
    pw = "pw-with-!@#$%^&*()_+={}[]|:;\"'<>,.?/~`"
    emu.save_app_password("test+tag@upf.edu", pw)
    assert emu.load_app_password("test+tag@upf.edu") == pw


def test_password_lookup_for_unknown_address_returns_none(isolated_email_config):
    assert emu.load_app_password("never-saved@upf.edu") is None


def test_password_lookup_empty_address_returns_none(isolated_email_config):
    assert emu.load_app_password("") is None


def test_delete_nonexistent_password_does_not_raise(isolated_email_config):
    emu.delete_app_password("never-saved@upf.edu")  # must not raise


def test_delete_password_removes_it(isolated_email_config):
    emu.save_app_password("test@upf.edu", "pw")
    emu.delete_app_password("test@upf.edu")
    assert emu.load_app_password("test@upf.edu") is None
