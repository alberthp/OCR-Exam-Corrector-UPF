# TODO for Albert — invented scan + data needed

## Why

`examples/` currently has 4 synthetic student-list files and 1 synthetic
answer key (all invented — see `examples/README.md`), but **no scanned
exam PDF**. Two things are blocked on that:

1. `examples/` can't ship a full, runnable example (roster + answer key +
   scan) the way it's supposed to.
2. `MANUAL.md`'s remaining 5 screenshots (05, 07, 08, 09, 10 — the
   correction panel, the colour legend, the export button, an exported
   review PDF, and the answer-grid colour states) can only be captured
   from a *loaded page*, and the only PDF available right now is your
   real exam scan. I generated those 5 once already and then deleted
   them — `04-review-screen.png` and `06-expected-overlay.png` (captured
   earlier in this project) turned out to show a real student's actual
   name, DNI, and U-number in plain text, which contradicts "don't push
   real data." I don't want to keep compounding that, and I can't
   reliably synthesize a fake scan myself (see below) — so this needs you.

## Why I can't just invent the scan myself

The OCR pipeline validates a scan against ~12 scan-tuned geometric
constants (marker spacing/height, digit fill-ratio thresholds, red-ink
hue ranges, bubble pitch — see `REF_DNI_X`, `REF_ANS_X`, `detect_markers`,
`detect_id_boxes` in `omr_correct.py`). Drawing a fake page that actually
passes `CORNER_ERROR`/`MARKER_ERROR` detection and reads back the right
invented values isn't something I can guarantee working without your
real blank template as a starting point — and there isn't one checked
into the repo.

## What I need from you

**A multi-page PDF, scanned or exported at 300 or 600 DPI, using the
real blank exam template, filled in with entirely invented answers and
identities.** Concretely:

1. Take the blank UPF bubble-sheet template (the one used for
   `LSDS_Retake2026_PermALL_Fixed.csv` etc.) — blank, unfilled.
2. Fill in **3–5 pages** by hand (or however you generate the real ones),
   using **fake identities that match the existing `examples/` roster**
   so everything cross-references cleanly:
   - U-numbers `U900001`–`U900012` (pick any subset) — see
     `examples/students_standard_example.csv` for the full invented
     roster (Alice Example, Bob Sample, Carol Test, ... Laura Taylor).
   - Any invented DNI (8 digits, doesn't need to be a valid check digit).
   - GRUP `1` or `2`, PERMUT `1` or `2` (matching `examples/answers_example.csv`,
     which only has permutations 1 and 2).
   - PARCIAL: whatever value your template expects (`1`, `2`, ...).
3. Fill in answer bubbles using **`examples/answers_example.csv`** as the
   key (10 questions, 4 options A–D) — mix it up: make one page fully
   correct, one partially correct, one with a couple of wrong answers,
   and one with a question left blank, so the screenshots actually show
   the different colour states (green/yellow/red/blank).
4. Save it as **`examples/scanned_exam_example.pdf`**.

## What happens after you provide it

Once that file exists, I'll:
- Run the real pipeline on it against `examples/students_standard_example.csv`
  and `examples/answers_example.csv` to produce a fully synthetic
  `results.xlsx` / `annotated_review.pdf` / `review_cache.pkl`.
- Capture all 11 `MANUAL.md` screenshots fresh from that synthetic data
  (replacing the 6 that currently contain real student PII).
- Extend `tests/test_examples.py` to cover the new example PDF.
- Update `examples/README.md` to mention the scan is now included.

## One more thing worth doing regardless

The 6 *existing* screenshots in `assets/screenshots/` (`01`, `02`, `03`,
`04`, `06`, `11`) were captured from real exam data earlier in this
session — `04-review-screen.png` and `06-expected-overlay.png` in
particular show a real student's actual name/DNI/U-number. I did **not**
touch or delete these, since that's a judgment call for you, not me —
let me know if you want them deleted/regenerated once the synthetic PDF
above is in place (recommended), or handled differently.
