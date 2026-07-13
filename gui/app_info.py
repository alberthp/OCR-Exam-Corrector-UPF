"""App identity constants, kept in their own module with zero heavy imports.

Deliberately has no PySide6/omr_correct/etc. imports: omr_gui.py needs
these for the startup splash *before* the slow image-processing/PDF
library imports run, and importing anything heavier here (even indirectly,
e.g. via gui.start_screen) would defeat the point -- the splash wouldn't
be able to show the version until after the very imports it exists to
give feedback about.
"""

# Bump this constant with each meaningful release.
APP_VERSION = "1.6"
APP_AUTHOR = "Albert Hernansanz (with Claude)"
APP_EMAIL = "albert.hernansanz@upf.edu"
