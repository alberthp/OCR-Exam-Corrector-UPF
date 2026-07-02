# OMR Exam Corrector — User Manual

**Version 1.3** · Albert Hernansanz ([albert.hernansanz@upf.edu](mailto:albert.hernansanz@upf.edu))

---

## Table of contents

1. [Overview](#1-overview)
2. [Before you start — input files](#2-before-you-start--input-files)
3. [Start screen](#3-start-screen)
4. [Evaluating a new exam](#4-evaluating-a-new-exam)
5. [Review screen — navigating results](#5-review-screen--navigating-results)
6. [Review screen — correcting a page](#6-review-screen--correcting-a-page)
7. [Expected-answers overlay (v1.2)](#7-expected-answers-overlay-v12)
8. [Exporting a page for a student review request (v1.3)](#8-exporting-a-page-for-a-student-review-request-v13)
9. [Output files](#9-output-files)
10. [Reopening a previous session](#10-reopening-a-previous-session)
11. [Colour conventions in the annotated PDF](#11-colour-conventions-in-the-annotated-pdf)
12. [Keyboard shortcuts and navigation tips](#12-keyboard-shortcuts-and-navigation-tips)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Overview

The OMR Exam Corrector reads a scanned PDF of UPF bubble-sheet exams,
identifies each student by the U-number bubbles on their sheet, grades their
answers against an answer key, and produces:

- **`results.xlsx`** — one spreadsheet sheet per exam permutation with all grades.
- **`annotated_review.pdf`** — the scan with colour-coded annotations for visual review.
- **`review_cache.pkl`** — a session file that lets you reopen and continue
  editing without re-running the OCR.

The desktop GUI walks you through the process in three screens:
**Start → New exam → Review**.

---

## 2. Before you start — input files

You need three files before running an analysis.

### 2.1 Scanned exam PDF

A single multi-page PDF where each page is one student's completed answer
sheet, scanned at **300 or 600 DPI**. The app auto-detects the DPI from the
PDF metadata; if that fails you can set it manually.

- Pages can be in any order — each page is matched to a student individually.
- Orientation is auto-corrected; portrait and landscape scans both work.
- Pages that cannot be processed (low quality, wrong template, heavily skewed)
  are flagged for manual review and do not block the rest.

### 2.2 Students list (CSV or Excel)

A spreadsheet with one row per student. Two formats are accepted:

**Standard format** — columns `Nom`, `Cognom1`, `Cognom2`, `U_number`:

| Nom   | Cognom1 | Cognom2 | U_number |
|-------|---------|---------|----------|
| Alice | Example | Smith   | U000001  |
| Bob   | Sample  | Jones   | U000002  |
| Carol | Test    | Brown   | U000003  |

**UPF official export** — `.xls` or `;`-separated CSV with a course-code row
on row 1 and column headers `IDUSUARI;NIA;NIP;COGNOM1;COGNOM2;NOM` on row 2.
The app detects this format automatically.

### 2.3 Answer key (CSV or Excel)

One row per question per permutation. Required columns: `Perm`,
`QuestionNum`, and one column per answer option (`A`, `B`, `C`, `D`, …).
A value of `1` means that option is correct; `0` means incorrect. Multiple
correct options per question are supported (partial credit).

| Perm | QuestionNum | A | B | C | D |
|------|-------------|---|---|---|---|
| 0    | 1           | 0 | 1 | 0 | 0 |
| 0    | 2           | 1 | 1 | 0 | 0 |
| 1    | 1           | 0 | 0 | 1 | 0 |
| 1    | 2           | 0 | 1 | 0 | 1 |

Each scanned page declares its own permutation via the PERMUT bubble on the
form; the app grades it against the matching key automatically.

---

## 3. Start screen

![Start screen](assets/screenshots/01-start-screen.png)

When you launch the app you see two main buttons:

- **Evaluate new exam…** — opens the New exam screen to run a fresh analysis.
- **Review / edit existing results…** — opens a file picker to select a
  `review_cache.pkl` from a previous session and jump straight into the
  Review screen.

Click **Exit** (bottom) to close the application.

---

## 4. Evaluating a new exam

### 4.1 Fill in the input files

![New exam screen](assets/screenshots/02-new-exam-form.png)

| Field | What to pick |
| ------- | ----------- |
| **Scanned exam PDF** | The multi-page PDF of scanned answer sheets. |
| **Students list** | CSV or Excel file with student names and U-numbers. |
| **Answers (Perm, QuestionNum, A, B, …)** | CSV or Excel answer key with permutations. |
| **Output directory** | Folder where results will be saved (default: `./output`). |

Use **Browse…** next to each field or type the path directly.

### 4.2 Set exam parameters

| Parameter | Description |
| ----------- | ----------- |
| **Number of questions** | How many questions to grade (1–100). Must match your answer key. |
| **Options per question** | Number of answer options per question (2–10, default 4). |
| **Source DPI** | Leave **Auto-detect** checked unless auto-detection fails. |

### 4.3 Run the analysis

Click **Run Analysis**. The progress bar advances as each page is processed,
and the table fills with live results: page number, status, detected
U-number, matched student name, DNI, permutation, and number of answered
questions.

![Analysis running](assets/screenshots/03-analysis-running.png)

When processing finishes:

- The **Open output folder** button becomes active.
- The app switches automatically to the Review screen.

### 4.4 Status codes

| Status | Meaning |
| -------- | --------- |
| `OK` | Page processed successfully. |
| `CORNER_ERROR` | Could not detect the form's outer border. |
| `MARKER_ERROR` | Found the border but could not locate the alignment markers. |
| `EXCEPTION` | Unexpected error — see the Log panel for details. |

---

## 5. Review screen — navigating results

![Review screen](assets/screenshots/04-review-screen.png)

The review screen has three panels:

- **Left — Pages table**: one row per scanned page. Click any row to jump to
  that page.
- **Centre — Annotated page**: renders the annotated PDF for the selected
  page with the colour-coded overlays.
- **Right — Correct this page**: editable fields for identification data and
  an answer grid.

### 5.1 Preview controls

| Control | Action |
| --------- | -------- |
| **<< Prev / Next >>** | Navigate to the previous or next page. |
| **– / +** | Zoom out / in (each click multiplies by 1.25×). |
| **Fit to page** | Scale the preview to fit the visible area. |
| **Ctrl + scroll wheel** | Zoom in/out with the mouse wheel. |
| **Middle-click drag** | Pan the preview when zoomed in. |
| **Show expected answers** | Toggle the expected-answers overlay on/off. |

---

## 6. Review screen — correcting a page

### 6.1 Identification fields

The right panel shows the values the OCR read for the current page, in this
order (updated in v1.3 to read top-to-bottom the way a reviewer typically
checks them):

| Field | Description |
| ------- | ----------- |
| **U-Number** | Student identifier (digits only, without the leading "U"). The **Matched student** label updates live as you type. |
| **DNI** | National ID number as read from the DNI bubbles. |
| **Group** | Student group code (the sheet's GRUP bubbles). |
| **Partial** | Exam part number, if used (the sheet's PARCIAL bubbles). |
| **Permutation** | Exam permutation — determines which answer key is applied (the sheet's PERMUT bubbles). |

### 6.2 Answer grid

The grid shows one row per question and one column per answer option. Filled
cells show the option letter (A, B, C…); empty cells mean no mark. Click any
cell to toggle that mark on or off.

A cell's text colour tells you where a mark came from:

| Colour | Meaning |
| -------- | --------- |
| Default (plain) | The scanner detected this mark — matches what OCR read from the sheet. |
| **Orange** | You just toggled this cell and haven't clicked **Apply correction** yet. |
| **Bold purple** | A mark you (or a previous reviewer) set by hand and that has been saved — it doesn't match what the scanner actually detected on the sheet. |

The purple state persists across sessions (it's recomputed from the saved
pixel data every time the page loads, the same way the purple "reviewer
added/removed" markers on the annotated PDF are), so a hand-corrected answer
never gets silently confused with an automatically detected one, even after
closing and reopening the review.

After editing, click **Apply correction** to save.

### 6.3 Saving corrections

- **Apply correction** — saves the current identification fields and answer
  marks. The button turns **orange** while the write is in progress.
- **Revert to original** — discards all manual changes and restores the
  original OCR reading. Requires confirmation; cannot be undone.
- **Rescan this page** — re-runs OCR on the original scanned PDF for this
  page only, discarding manual changes.

![Correction panel](assets/screenshots/05-correction-panel.png)

Every correction immediately updates `results.xlsx`, the relevant page of
`annotated_review.pdf`, and `review_cache.pkl`.

### 6.4 Manual-correction indicators

Changes made in the review screen appear highlighted in **purple** on the
annotated PDF:

- **Purple circle (O)** — an answer mark the reviewer *added*.
- **Purple cross (X)** — an answer mark the reviewer *removed*.
- **Purple pill badge** — an identification field edited by hand.

The same orange/purple colouring also appears directly in the answer grid
itself — see [6.2 Answer grid](#62-answer-grid) above.

The **Manual** column in the pages table shows **Y** for any page that has
at least one manual change.

---

## 7. Expected-answers overlay (v1.2)

The **"Show expected answers"** button in the preview toolbar draws a **blue
diagonal slash** through every bubble the answer key marks as correct for
the current page's permutation.

![Expected answers overlay](assets/screenshots/06-expected-overlay.png)

- **Off by default** — it is a reviewer aid, not part of the standard annotation.
- **Purely visual** — it never modifies the underlying scan or the annotated PDF.
- **Scales with zoom** and updates automatically when you navigate to a
  different page or apply a correction that changes the permutation.
- If the page's permutation is not detected or not found in the answer key,
  the overlay shows nothing silently.

**Typical use:** toggle the overlay on before checking a page to immediately
see which bubbles should be filled, without looking up the answer key
separately.

---

## 8. Exporting a page for a student review request (v1.3)

When a student formally requests a grade review, you often need to hand
over just *their* page rather than the whole batch PDF. The **"Export for
student review request..."** button (bottom of the "Correct this page"
panel) writes a self-contained, 2-page PDF for the page currently on
screen:

![Export button](assets/screenshots/08-export-button.png)

1. **Page 1** — the raw scanned page, exactly as filled in by the student,
   with no annotation layer at all.
2. **Page 2** — the same page fully annotated: the usual colour-coded
   overlays (see [section 11](#11-colour-conventions-in-the-annotated-pdf)),
   the expected-answers overlay (blue diagonal slash) drawn automatically
   for *every* bubble the answer key marks correct — even on questions the
   student left blank, not just the ones they attempted — and the colour
   legend from the preview panel, so the page is self-explanatory without
   the app open.

![Exported review PDF](assets/screenshots/09-export-pdf-pages.png)

Clicking the button opens a save dialog pre-filled with a suggested
filename built from the page's identification fields:

```text
U<u_number>_T<group>_Q<partial>_P<permutation>.pdf
```

For example, U-number 225659, group 1, partial 2, permutation 2 becomes
**`U225659_T1_Q2_P2.pdf`**. Any field that couldn't be read is replaced with
`X` (e.g. `UX` if the U-number wasn't detected) so the filename always stays
well-formed — pick a different name in the dialog if that happens.

The button is disabled with an explanatory message for pages that failed
processing and have no scanned image to export.

---

## 9. Output files

All files are written to the output directory you specified (default `./output`).

### `results.xlsx`

One sheet per detected permutation (`Perm 0`, `Perm 1`, …) plus two special
sheets:

- **`No_Perm_Detected`** — pages where the PERMUT bubble could not be read
  or does not match any known permutation. Grades are blank.
- **`Summary`** — counts of total pages, processed pages, matched
  U-numbers, and pages per permutation.

Each permutation sheet has student identification, per-question answer
columns, per-question scores, total score, and grade on a 0–10 scale.

### `annotated_review.pdf`

One page per successfully processed exam sheet with perspective-corrected
scan and all colour-coded vector overlays. See
[section 11](#11-colour-conventions-in-the-annotated-pdf) for the full
colour legend.

### `review_cache.pkl`

Binary session file. Keep it next to `results.xlsx` and
`annotated_review.pdf` — the app uses their relative paths to locate them.
If you move the output folder, move all three files together.

### Student review export (v1.3)

A one-off, 2-page PDF generated on demand from the **"Export for student
review request..."** button — see [section 8](#8-exporting-a-page-for-a-student-review-request-v13).
Unlike the three files above, it isn't written automatically; you choose its
name and location each time via a save dialog.

---

## 10. Reopening a previous session

From the **Start screen**, click **Review / edit existing results…** and
select the `review_cache.pkl` from a previous run. The app will locate
`results.xlsx` and `annotated_review.pdf` automatically (they must be in the
same folder as the cache file) and open the Review screen with all previous
corrections intact.

---

## 11. Colour conventions in the annotated PDF

The legend at the bottom of the preview panel summarises the colours at a
glance. Full reference:

![Colour legend](assets/screenshots/07-legend.png)

| Colour / symbol | Meaning |
| ----------------- | --------- |
| **Green box** | Fully correct answer (student marked exactly the right options). |
| **Yellow box** | Partially correct (some correct options marked, no wrong ones). |
| **Red box** | Incorrect (wrong option marked, or correct option missed with a wrong one). |
| **Blue box + X** | Cancel mark — student crossed out this bubble in the cancel row. |
| **Purple circle (O)** | Answer mark *added* by a reviewer. |
| **Purple cross (X)** | Answer mark *removed* by a reviewer. |
| **Orange box** | Detected ID field boundary (DNI, PERMUT, GRUP, etc.). |
| **Green label** | Value read from an ID field, shown above its orange box. |
| **Purple pill** | Identification field value edited by a reviewer. |
| **Blue diagonal slash** | Expected correct answer from the answer key (v1.2 overlay; also drawn on the annotated page of a v1.3 student review export). |
| **Header green** | Page OK: U-number matched, answers detected. |
| **Header yellow** | Page needs review (partial detection or ambiguous U-number). |
| **Header red** | Page needs manual check (very low quality or no detections). |

This same legend is printed at the bottom of page 2 of a student review
export (v1.3) — see [section 8](#8-exporting-a-page-for-a-student-review-request-v13).

The **answer grid** in the "Correct this page" panel uses two additional,
grid-only colours that are *not* part of the annotated-PDF legend above —
see [6.2 Answer grid](#62-answer-grid): **orange** for a toggle not yet
saved, and **bold purple** for a saved hand-set mark.

---

## 12. Keyboard shortcuts and navigation tips

| Action | How |
| -------- | ----- |
| Next page | **Next >>** button, or click the next row in the Pages table. |
| Previous page | **<< Prev** button, or click the previous row. |
| Zoom in | **+** button or **Ctrl + scroll up**. |
| Zoom out | **–** button or **Ctrl + scroll down**. |
| Fit preview to window | **Fit to page** button. |
| Pan preview | Hold **middle mouse button** and drag. |
| Toggle expected answers | **Show expected answers** button (checkable toggle). |
| Save correction | **Apply correction** button. |
| Discard all changes on page | **Revert to original** (confirmation required). |
| Re-run OCR on current page | **Rescan this page** (confirmation required). |
| Export page for a review request | **Export for student review request...** button, then choose a save location. |
| Back to Start screen | **<< Back to start** button (top-left of review screen). |

---

## 13. Troubleshooting

### All pages fail with `CORNER_ERROR`

The app cannot find the outer border of the form. Likely causes:

- The PDF was not generated from the standard UPF bubble-sheet template.
- The scan is very dark/light, or the page has a large black border from the
  scanner lid.
- Try increasing scan brightness/contrast before re-scanning.

### Some pages fail with `MARKER_ERROR`

The border was found but the alignment markers (vertical strip of black
squares on the left margin) could not be located. Likely causes:

- The sheet was placed too far to one side in the scanner.
- Part of the marker strip is torn, folded, or obscured.
- Use **Rescan this page** after re-scanning that sheet.

### U-number not detected / shows `(no match)`

The app found a U-number in the bubbles but it does not appear in the
students list. Check:

- The U-number on the sheet must match the `U_number` column exactly.
- The student may have filled the wrong bubbles (filled a row instead of a
  column — a common mistake).
- Correct manually in the **U-Number** field in the review screen.

### The expected-answers overlay shows nothing

Check that:

- The current page's PERMUT bubble was read correctly (shown in the
  **Permutation** field on the right panel).
- The answer key contains an entry for that permutation (check the `Perm`
  values in your answers file).

### The "Apply correction" button stays orange for a long time

The app is copying the updated files back to a cloud-synced folder (Google
Drive, OneDrive, etc.). The local save is already done — data is safe. You
can navigate to other pages and keep working while the sync runs in the
background.

### "Export for student review request..." is greyed out, or shows an error

The button is disabled whenever the current page failed processing (no
scanned image to export — see [4.4 Status codes](#44-status-codes)). If it's
enabled but the export fails, an error dialog explains why (e.g. the chosen
save location isn't writable); the exported file is otherwise independent of
`results.xlsx`/`annotated_review.pdf` and can simply be retried.

### First launch of the `.exe` is very slow

Antivirus software often deep-scans an unfamiliar unsigned executable on
first launch. Wait 1–2 minutes; subsequent launches are much faster. On
managed/corporate machines, ask IT to whitelist the application folder.

---

## Appendix — Screenshots needed

> The screenshots below need to be captured from the running application and
> saved to `assets/screenshots/` with the exact filenames listed. The table
> describes exactly what to show in each one. `01-start-screen.png` already
> exists but was taken on v1.2 (the footer reads "v1.2") — retake it so the
> footer reads **v1.3**.

| File | Screen | What to show |
| ------ | -------- | ----------- |
| `01-start-screen.png` | Start | Full window at launch, both main buttons visible, footer showing **v1.3**. *(needs retaking — currently v1.2)* |
| `02-new-exam-form.png` | New exam | Form with all four file fields filled in, before clicking Run. |
| `03-analysis-running.png` | New exam | Mid-run: progress bar partially filled, several rows in the table. |
| `04-review-screen.png` | Review | Full window with an annotated page loaded, overlay **off**. |
| `05-correction-panel.png` | Review | Right panel close-up: fields in the new order (U-Number, DNI, Group, Partial, Permutation), answer grid visible. |
| `06-expected-overlay.png` | Review | Same page as `04` but **"Show expected answers" toggled on** (blue slashes visible). |
| `07-legend.png` | Review | Crop of the legend strip at the bottom of the preview panel. |
| `08-export-button.png` | Review | Right panel close-up showing the **"Export for student review request..."** button, plus the save dialog it opens with the suggested filename visible. |
| `09-export-pdf-pages.png` | Exported PDF | Both pages of one exported student-review PDF side by side (or stacked): page 1 the plain scan, page 2 the annotated page with the expected-answers overlay and legend visible in the footer. |
| `10-answer-grid-colours.png` | Review | Close-up of the answer grid showing all three cell states at once if possible: a plain (auto-detected) mark, an **orange** unsaved toggle, and a **bold purple** saved manual mark. |
