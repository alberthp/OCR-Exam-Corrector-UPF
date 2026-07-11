# poppler_bin/

This folder is **not tracked in git** (its contents are third-party
binaries, ~19MB) — it needs to be populated once before building the
standalone `.exe` with PyInstaller. It's *not* needed to run the app from
source if you already have Poppler installed and on PATH.

## Setup

1. Download the latest **standalone** Windows Poppler build (NOT a MiKTeX,
   TeX Live, or other LaTeX-distribution copy of `pdftoppm`/`pdfinfo` —
   those are dynamically linked against that distribution's own shared
   runtime and won't run on a machine without it installed):
   https://github.com/oschwartz10612/poppler-windows/releases (grab the
   `Release-*.zip` asset)
2. From the zip's `Library/bin/` folder, copy these 18 files into this
   folder (`poppler_bin/`):

   ```
   Lerc.dll
   deflate.dll
   freetype.dll
   jpeg8.dll
   lcms2.dll
   libcrypto-3-x64.dll
   libcurl.dll
   liblzma.dll
   libpng16.dll
   libssh2.dll
   openjp2.dll
   pdfimages.exe
   pdfinfo.exe
   pdftoppm.exe
   poppler.dll
   tiff.dll
   zlib.dll
   zstd.dll
   ```

3. Build the executable: `python -m PyInstaller --noconfirm "OMR Exam Corrector.spec"`

This exact file list was determined by walking the full DLL import
dependency tree of `pdftoppm.exe`/`pdfinfo.exe`/`pdfimages.exe` (via
`pefile`) with no other Poppler/LaTeX distribution on PATH, to confirm the
set is complete and self-contained.
