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

All four student-list files describe the **same 12 fake students**
(Alice Example, Bob Sample, Carol Test, ... — same U-numbers throughout),
just exported in each of the four formats `load_students()` accepts, so you
can compare them side by side. See [`INSTALL.md` §3.1](../INSTALL.md#31-students-list-csv-or-excel)
or [`MANUAL.md` §2.2](../MANUAL.md#22-students-list-csv-or-excel) for the
full format reference.

There's deliberately **no example scanned exam PDF** here — a synthetic
bubble-sheet scan isn't something these files can fake convincingly, so
that piece is added separately.

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

Once you have a real (or your own invented) scanned exam PDF, a full run
looks like:

```bash
python omr_correct.py your_scan.pdf examples/students_standard_example.csv examples/answers_example.csv --questions 10 --num-options 4
```

These files are also exercised by the automated test suite
(`tests/test_examples.py`) so they can't silently go stale or stop
matching what `load_students()`/`load_correct_answers()` actually expect.
