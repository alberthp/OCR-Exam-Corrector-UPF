# OMR Exam Corrector — Installation & Technical Reference

## 1. System prerequisites

In addition to Python 3.10+, you need **Poppler** (the PDF rendering library).

### macOS

```bash
brew install poppler
```

### Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y poppler-utils
```

### Windows

Download the pre-built Poppler binaries from
<https://github.com/oschwartz10612/poppler-windows/releases>
and add the `bin\` subfolder to your `PATH` environment variable.

> The packaged `.exe` already bundles Poppler — you only need this step when
> running from source.

---

## 2. Create a virtual environment and install dependencies

```bash
# 1. Create the venv
python3 -m venv omr_env

# 2. Activate it
# macOS / Linux:
source omr_env/bin/activate
# Windows (PowerShell):
omr_env\Scripts\Activate.ps1

# 3. Install all dependencies
pip install -r requirements.txt
```

`requirements.txt` installs both the OMR engine (`omr_correct.py`) and the
desktop GUI (`omr_gui.py`, PySide6-based), plus legacy `.xls` support via
`xlrd`.

> **Note on portability**: a virtual environment is not portable between
> machines — it contains absolute paths to the original Python interpreter
> and OS-specific compiled packages. If you move to a different machine,
> recreate the environment from scratch with the steps above. Poppler must
> be installed separately on each machine.

### Verify the installation

```bash
python -c "import cv2, numpy, pandas, openpyxl, pdf2image, reportlab, PySide6; print('OK')"
```

---

## 3. Input file formats

### 3.1 Students list (CSV or Excel)

Four formats are accepted; the app auto-detects which one from the column
headers.

**Standard format** — columns `Nom`, `Cognom1`, `Cognom2`, `U_number`:

| Nom   | Cognom1 | Cognom2 | U_number |
|-------|---------|---------|----------|
| Alice | Example | Smith   | U000001  |
| Bob   | Sample  | Jones   | U000002  |
| Carol | Test    | Brown   | U000003  |

**UPF official export** (`.xls` or `;`-separated CSV) — first row contains
the course code, second row contains the column headers
`IDUSUARI;NIA;NIP;COGNOM1;COGNOM2;NOM`. The app auto-detects this format
and discards the NIA/NIP columns.

```text
LSDS2025
IDUSUARI;NIA;NIP;COGNOM1;COGNOM2;NOM
u000001;00001;00001;EXAMPLE;SMITH;ALICE
u000002;00002;00002;SAMPLE;JONES;BOB
```

**Moodle "participants" export** (e.g. `courseid_NNNNN_participants.csv`) —
columns `Nom`, `Cognoms` (both surnames in one field — split on the first
space into Cognom1/the rest; imperfect for 3+-word compound surnames, but
only affects display), `Número ID` (U-number, typically lowercase
`u123456` — the leading `U`/`u` is stripped the same way as any other
format), and `Grups` encoding theory group + seminar subgroup as
`<group><nn>-<subgroup>` (e.g. `201-7`). Only the leading digit (the theory
group, always 1 or 2 in exports seen so far) is used — there's no bubble
field on the exam sheet for the seminar subgroup.

```text
Nom,Cognoms,"Número ID",Grups
ALICE,"EXAMPLE SMITH",u000001,201-7
BOB,"SAMPLE JONES",u000002,101-1
```

**UPF `llistatGGiA` export** (e.g. `llistatGGiA (N).xls`) — same two-row
layout as the official export, with two extra columns: `EMAIL` (kept as-is
in `results.xlsx`, not used for grading) and `PRACTICA` (e.g. `102`; same
leading-digit-as-theory-group parsing as `Grups` above).

```text
LSDS2025
IDUSUARI;NIA;COGNOM1;COGNOM2;NOM;EMAIL;PRACTICA
u000001;00001;EXAMPLE;SMITH;ALICE;alice.example@estudiant.upf.edu;102
```

Both of the last two formats populate a `TheoryGroup` per student, which
`backfill_and_validate_groups()` cross-checks against each scanned page's
GRUP bubble (backfilling it when unreadable, flagging a mismatch
otherwise) — see [section 5](#5-output-files) and the `GRUP`/`GRUP_Check`
columns below.

### 3.2 Answer key (CSV or Excel) — with permutations

The file **must** have a `Perm` column: one row per (permutation, question)
pair, with one column per answer option (`A`, `B`, `C`, `D`, …) holding `1`
(correct) or `0` (incorrect). Multiple correct options per question are
supported (multi-answer questions with partial credit).

| Perm | QuestionNum | A | B | C | D |
|------|-------------|---|---|---|---|
| 0    | 1           | 0 | 1 | 0 | 0 |
| 0    | 2           | 1 | 1 | 0 | 0 |
| 1    | 1           | 0 | 0 | 1 | 0 |
| 1    | 2           | 0 | 1 | 0 | 1 |
| 2    | 1           | 1 | 0 | 0 | 0 |

Each scanned sheet declares its own permutation via the **PERMUT** bubble on
the form. The app reads it and grades that sheet with the matching key
automatically — no manual sorting needed.

**Validation before grading**: the file is checked for a `QuestionNum`
missing or duplicated within a permutation — a common copy/paste slip that
otherwise grades silently wrong (a missing question is just excluded from
that permutation's max score; a duplicate lets the last row win). The GUI
shows a dialog with each issue and, when the cause looks like a `Perm`
value copy/pasted one row too early, a one-click fix (see MANUAL.md's
[Answer-key validation](MANUAL.md#5-answer-key-validation-v14) section).
The CLI runs the same check and refuses to proceed by default — see
`--ignore-answer-key-warnings` below.

---

## 4. Command-line usage

### Basic call

```bash
python omr_correct.py exams.pdf students.csv answers.csv --questions 10
```

### Full options

```bash
python omr_correct.py \
    exams.pdf \          # multi-page PDF of scanned answer sheets
    students.csv \       # student list (CSV or Excel)
    answers.csv \        # answer key with Perm column
    --questions 10 \     # number of questions to grade (required)
    --num-options 5 \    # options per question (default 5; range 2–10)
    --output-dir ./out \ # output folder (default ./output)
    --dpi 0 \            # 0 = auto-detect (300 or 600); override with e.g. 300
    --verbose \          # extra debug output
    --ignore-answer-key-warnings   # proceed despite missing/duplicate answer-key rows (v1.4)
```

`--ignore-answer-key-warnings` (v1.4): by default the tool refuses to grade
if the answer key has a question missing or duplicated for some permutation
(see [section 3.2](#32-answer-key-csv-or-excel--with-permutations) above)
and prints the same diagnostics the GUI's validation dialog shows. Pass this
flag to grade anyway — only do so once you understand exactly what's wrong
and accept the consequence for that permutation's grades.

### Examples

```bash
# 25-question exam with 4 options
python omr_correct.py exam.pdf students.csv answers.csv -q 25 -n 4

# Two separate exams into separate output folders
python omr_correct.py midterm.pdf students.csv answers_mid.csv -q 10 -o output_midterm
python omr_correct.py final.pdf   students.csv answers_fin.csv -q 15 -o output_final

# Proceed despite a known, accepted answer-key gap
python omr_correct.py exam.pdf students.csv answers.csv -q 30 --ignore-answer-key-warnings
```

---

## 5. Output files

### `results.xlsx`

One sheet per detected permutation (`Perm 0`, `Perm 1`, …) plus:

- **`No_Perm_Detected`** — pages where the PERMUT bubble was not readable or
  does not match any known permutation. Grades are blank.
- **`T1`, `T2`** (v1.4) — a flat DNI/U_Number/Score roster per theory group
  (see `_write_group_sheet()` in `omr_correct.py`), pulled from every page
  regardless of permutation, since GRUP and PERMUT are independent fields.
  Only students with a resolvable theory group (scanned or roster-backfilled)
  appear on either tab.
- **`Summary`** — totals: pages processed, U-numbers matched, pages per
  permutation.

Each permutation sheet contains:

- Student identification: U-number, Name / Surname1 / Surname2 (looked up
  from the students list), Email (v1.4, when the students list provides
  one), DNI, PARCIAL, PERMUT, GRUP, and `GRUP_Check` (v1.4: `OK` /
  `FROM_ROSTER` / a `MISMATCH (...)` message / blank — see
  `backfill_and_validate_groups()`).
- Per-question answer columns (1 = marked, 0 = not marked) and a per-question
  score (1.0 = fully correct; partial credit if applicable; 0 otherwise).
- Total score and grade on a 0–10 scale.
- Problem-flag codes for pages that need attention.

### `annotated_review.pdf`

One page per successfully processed sheet:

- Perspective-corrected scan as background.
- Header bar (green / yellow / red) with page number, status, U-number,
  student name, and quality metrics.
- Coloured vector overlays on every answer bubble:
  - **Green** — fully correct answer.
  - **Yellow** — partially correct (some correct options marked, no wrong ones).
  - **Red** — incorrect (wrong option marked, or correct option missed).
  - **Blue rectangle** — cancel-row mark (student crossed the bubble out).
  - **Purple circle** — answer mark added by the reviewer.
  - **Purple cross** — answer mark removed by the reviewer.
- Orange boxes around detected ID field areas with a green value label —
  except the GRUP field, whose label is **teal** when backfilled from the
  student roster or **red** when it disagrees with the roster (v1.4).
- Purple pill badges for any manually-edited identification fields.

### `review_cache.pkl`

Binary session file used by the GUI to reopen a session without re-running
OCR. Keep it next to `results.xlsx` and `annotated_review.pdf`.

---

## 6. Partial-credit scoring formula

For each question with **G** correct options out of **N** total:

- Each **correct** option marked: `+1/G`
- Each **incorrect** option marked: `−1/(N−G)`
- Question score capped at 0 (no negative per-question contribution)

Leaving a question completely blank scores 0.

---

## 7. Troubleshooting

### All pages fail with `CORNER_ERROR`

The app cannot detect the outer border of the form. Likely causes:

- Wrong exam template (the form must have the UPF bubble-sheet layout with
  alignment markers on the left margin).
- Very dark or very light scan — adjust scanner brightness/contrast.
- Large black border from the scanner lid — crop the PDF before processing.

### Some pages fail with `MARKER_ERROR`

The border was found but the alignment-marker strip could not be located:

- The sheet was placed too far to one side in the scanner.
- Part of the marker strip is torn, folded, or obscured.
- Re-scan and use **Rescan this page** in the review screen.

### "Killed" during processing

Insufficient RAM. Workarounds:

- Close other applications.
- Process the PDF in smaller batches (split with a PDF tool first).
- Use `--dpi 300` instead of 600 — quality is almost identical at lower cost.

### U-number not detected

- The student may have filled the wrong bubbles (a common mistake is filling
  a row instead of a column).
- Correct manually in the review screen's **U-Number** field.

### First `.exe` launch is very slow

Antivirus software deep-scans unfamiliar unsigned executables on first run.
Wait 1–2 minutes; subsequent launches are much faster. On managed corporate
machines, ask IT to whitelist the app folder.
