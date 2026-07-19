"""read_digit_marker_anchored(): single-column digit-bubble detection.

Regression tests for a real-data bug (LSDS Retake Juliol2026 scan, page 1):
the printed header artwork sitting just above row 0 of every ID column falls
inside the vertical strip the function scans (y_margin extends 80% of a row
above id_rows[0]). With the old 70%-of-median_sp row-alignment tolerance,
that artwork's peak was close enough to id_rows[0] to be accepted as a
"digit 0" mark -- and on the real page it was even taller than the actual
student mark, so it won outright and silently misread the digit as 0 instead
of 1 (u_number decoded as "049700" instead of the correct "149700"). The fix
tightened the tolerance to 45% and made peak selection fall through to the
next-strongest row-aligned peak instead of giving up when the top peak
doesn't line up with a real row.
"""

import numpy as np

import omr_correct as omr

MEDIAN_SP = 50
ID_ROWS = np.array([100 + i * MEDIAN_SP for i in range(10)])
H = 650
W = 200
CX = 100


def _make_mask():
    return np.zeros((H, W), dtype=np.uint8)


def _draw_band(mask, cx, y_center, fill_frac, half_height=8, half_width=12):
    x1 = cx - half_width
    n_filled_cols = int(2 * half_width * fill_frac)
    mask[y_center - half_height:y_center + half_height, x1:x1 + n_filled_cols] = 255


def test_single_clean_mark_returns_correct_digit_not_ambiguous():
    mask = _make_mask()
    _draw_band(mask, CX, ID_ROWS[3], fill_frac=1.0)

    digit, fill, ambiguous = omr.read_digit_marker_anchored(mask, CX, ID_ROWS, MEDIAN_SP, W)

    assert digit == 3
    assert ambiguous is False
    assert fill > 0.9


def test_no_mark_returns_none():
    mask = _make_mask()

    digit, fill, ambiguous = omr.read_digit_marker_anchored(mask, CX, ID_ROWS, MEDIAN_SP, W)

    assert digit is None
    assert ambiguous is False


def test_two_genuine_marks_in_different_rows_flagged_ambiguous():
    mask = _make_mask()
    _draw_band(mask, CX, ID_ROWS[1], fill_frac=0.6)
    _draw_band(mask, CX, ID_ROWS[8], fill_frac=1.0)

    digit, fill, ambiguous = omr.read_digit_marker_anchored(mask, CX, ID_ROWS, MEDIAN_SP, W)

    assert digit == 8  # stronger of the two marks wins
    assert ambiguous is True


def test_artifact_peak_above_row_0_does_not_mask_real_mark_in_row_1():
    """Regression test: printed header artwork above row 0, real scan bug.

    The artifact sits inside the scanned strip (within 80% of a row above
    id_rows[0]) but outside the 45% row-alignment tolerance, and is drawn
    *stronger* than the real mark -- exactly the real-page situation where
    the artifact used to win and misread the digit as 0.
    """
    mask = _make_mask()
    artifact_y = int(ID_ROWS[0] - MEDIAN_SP * 0.6)  # dist 30px > 22.5px tolerance
    _draw_band(mask, CX, artifact_y, fill_frac=1.0)
    _draw_band(mask, CX, ID_ROWS[1], fill_frac=0.6)

    digit, fill, ambiguous = omr.read_digit_marker_anchored(mask, CX, ID_ROWS, MEDIAN_SP, W)

    assert digit == 1
    assert ambiguous is False


def test_weak_peak_below_fill_threshold_is_ignored():
    mask = _make_mask()
    _draw_band(mask, CX, ID_ROWS[5], fill_frac=0.1)

    digit, fill, ambiguous = omr.read_digit_marker_anchored(
        mask, CX, ID_ROWS, MEDIAN_SP, W, fill_threshold=0.35)

    assert digit is None
    assert ambiguous is False
