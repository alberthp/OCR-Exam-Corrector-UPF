# Example input files

**Every name, U-number, email, and grade pattern in this folder is
invented.** There are no real students here — this is a synthetic dataset
shaped exactly like the real thing, so you can see every supported input
format actually load and try the tool without needing real exam data.

(The real exam PDF / rosters / answer key used during development are
gitignored — see the note in `.gitignore` — precisely so this folder could
be the sanitized, shareable substitute.)

## What's here

| File | Demonstrates |
|---|---|
| `students_standard_example.csv` | The plain `Nom / Cognom1 / Cognom2 / U_number` format |
| `students_upf_official_example.csv` | The UPF official export format: a course-title row, then `IDUSUARI;NIA;NIP;COGNOM1;COGNOM2;NOM` |
| `students_moodle_example.csv` | The Moodle "participants" export: `Nom / Cognoms / "Número ID" / Grups` (theory group parsed from the leading digit of `Grups`, e.g. `101-3` → group 1) |
| `students_llistatGGiA_example.xlsx` | The `llistatGGiA` export: course-title row + `IDUSUARI;NIA;COGNOM1;COGNOM2;NOM;EMAIL;PRACTICA` |
| `answers_example.csv` | The answer-key format: `Perm,QuestionNum,A,B,C,D`, two permutations, 10 questions, a mix of single- and multi-correct-answer questions |
| `scanned_exam_example.pdf` | A single-page, invented, filled-in scan of the real UPF bubble-sheet template (see [below](#the-scanned-exam-example)) |
| `answers_scan_example.csv` | The matching answer key for `scanned_exam_example.pdf`: `Perm,QuestionNum,A,B,C,D`, one permutation, 20 questions |

All four student-list files describe the **same 13 fake students**
(Alice Example, Bob Sample, Carol Test, ... Laura Taylor, plus Albert
Einstein — same U-numbers throughout), just exported in each of the four
formats `load_students()` accepts, so you can compare them side by side.
See [`INSTALL.md` §3.1](../INSTALL.md#31-students-list-csv-or-excel)
or [`MANUAL.md` §2.2](../MANUAL.md#22-students-list-csv-or-excel) for the
full format reference.

## The scanned exam example

`scanned_exam_example.pdf` is an invented student ("Albert Einstein", DNI
`21566429`, U-number `U237958`, group 1, permutation 1) filling in a real,
blank UPF bubble-sheet template by hand — the one piece the other example
files couldn't fake, since it has to actually pass the OCR pipeline's
geometric detection (border, alignment markers, bubble positions) to be
useful as an example.

It's deliberately filled in to exercise every partial-credit scoring case
at once against `answers_scan_example.csv` (20 questions, options A-D) —
see [MANUAL.md §5.1](../MANUAL.md#51-partial-credit-worked-examples) for
the full walkthrough of what each question demonstrates, including
question 11, where the student also filled bubble **E** — an option that
doesn't exist in this exam's 4-option key. Run with `--num-options 4`
(matching the key) that extra mark is simply never read; run with
`--num-options 5` (matching the sheet's generic 5-row template but not the
key) it's read and scored as always-wrong, which is the exact
misconfiguration [MANUAL.md §5](../MANUAL.md#5-answer-key-validation-v14)
warns about — this file reproduces that warning for real if you try it.

## Try it

Loading each format directly:

```bash
python -c "import omr_correct as omr; print(omr.load_students('examples/students_standard_example.csv'))"
python -c "import omr_correct as omr; print(omr.load_correct_answers('examples/answers_example.csv'))"
```

Or a real (if PDF-less) run of the answer-key validator:

```bash
python -c "
import omr_correct as omr
issues = omr.validate_answer_key('examples/answers_example.csv', expected_num_questions=10, expected_num_options=4)
print('issues:', issues)
"
```

A full run against your own scanned exam PDF looks like:

```bash
python omr_correct.py your_scan.pdf examples/students_standard_example.csv examples/answers_example.csv --questions 10 --num-options 4
```

...and since `scanned_exam_example.pdf` is a real (if invented) scan, that
same command works end to end with the files already in this folder:

```bash
python omr_correct.py examples/scanned_exam_example.pdf examples/students_standard_example.csv examples/answers_scan_example.csv --questions 20 --num-options 4
```

This is the only combination in `examples/` that produces a full
`results.xlsx` / `annotated_review.pdf` pair with a matched, graded page —
everything else here demonstrates one input format in isolation.

These files are also exercised by the automated test suite
(`tests/test_examples.py`) so they can't silently go stale or stop
matching what `load_students()`/`load_correct_answers()` actually expect.
