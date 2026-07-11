"""decode_identifier(): U-number recovery from an 8-bubble IDENTIFIER read.

Includes a permanent regression test for the wrong-digit bug found and
fixed in the v1.4 stress-testing pass: the 7-non-null branch used to infer
leading/trailing padding from "is the boundary digit a 0" rather than
"which bubble position is actually missing", and could silently return a
different student's U-number.
"""

import omr_correct as omr


def test_exactly_6_digits_is_ok():
    digits = [2, 3, 4, 5, 6, 7, None, None]
    val, status = omr.decode_identifier(digits)
    assert (val, status) == ("234567", "OK")


def test_all_missing_is_missing():
    val, status = omr.decode_identifier([None] * 8)
    assert (val, status) == (None, "MISSING")


def test_fewer_than_6_is_incomplete():
    val, status = omr.decode_identifier([2, 3, 4, None, None, None, None, None])
    assert status == "INCOMPLETE"


def test_8_digits_trailing_pad_ok():
    digits = [2, 3, 4, 5, 6, 7, 0, 0]
    val, status = omr.decode_identifier(digits)
    assert (val, status) == ("234567", "OK_PADDED")


def test_8_digits_leading_pad_ok():
    digits = [0, 0, 2, 3, 4, 5, 6, 7]
    val, status = omr.decode_identifier(digits)
    assert (val, status) == ("234567", "OK_PADDED")


def test_8_digits_ambiguous_when_neither_pad_is_zero():
    # Both ends non-zero: genuinely ambiguous which 6 are the real ID.
    digits = [1, 2, 3, 4, 5, 6, 7, 8]
    val, status = omr.decode_identifier(digits)
    assert status == "AMBIGUOUS"
    assert "|" in val


def test_7_digits_legit_trailing_pad_only_last_slot_missing():
    # Position 7 (the second pad slot) is the one that didn't register;
    # position 6 genuinely is the pad zero -> safe to recover.
    digits = [2, 3, 4, 5, 6, 7, 0, None]
    val, status = omr.decode_identifier(digits)
    assert (val, status) == ("234567", "OK_PADDED")


def test_7_digits_legit_leading_pad_only_first_slot_missing():
    digits = [None, 0, 2, 3, 4, 5, 6, 7]
    val, status = omr.decode_identifier(digits)
    assert (val, status) == ("234567", "OK_PADDED")


def test_7_digits_real_digit_missing_trailing_variant_does_not_guess_wrong():
    """Regression test for the confirmed bug: a real (non-pad) digit
    missing, with both intended pad zeros still present, used to be
    silently misread as a trailing-pad case and return the WRONG 6-digit
    ID ("234670" instead of recognizing the loss). It must now refuse to
    guess a specific ID and return WARNING with the raw 7-digit read.
    """
    digits = [2, 3, 4, None, 6, 7, 0, 0]
    val, status = omr.decode_identifier(digits)
    assert status == "WARNING"
    assert val != "234670"  # the old, wrong, silently-returned value
    assert val == "2346700"  # raw read: nothing was silently discarded


def test_7_digits_real_digit_missing_leading_variant_does_not_guess_wrong():
    digits = [0, 0, 2, 3, 4, None, 6, 7]
    val, status = omr.decode_identifier(digits)
    assert status == "WARNING"
    assert val == "0023467"


def test_7_digits_pad_slot_present_but_not_actually_zero_does_not_guess():
    # Position 7 is missing (looks like trailing-pad shape), but position 6
    # isn't 0 -- so it's NOT actually a valid pad slot. Must not guess.
    digits = [2, 3, 4, 5, 6, 7, 9, None]
    val, status = omr.decode_identifier(digits)
    assert status == "WARNING"
