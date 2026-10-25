#!/usr/bin/env python3
# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build AuthorBoard on Windows (onedir).

    python build_windows.py            # onedir (recommended)
    python build_windows.py --console  # onedir + console window (for debugging)

Produces dist/AuthorBoard/AuthorBoard.exe plus dist/AuthorBoard/_internal/.
Zip the entire dist/AuthorBoard/ folder to distribute.

The spellchecker dictionaries (en.json.gz, de.json.gz) are collected with
--collect-data so spell checking works in the frozen build.  Without that
flag the app crashes the moment a note is selected, because
SpellChecker(language=...) cannot find its resource file.
"""
import argparse
import os
import subprocess
import sys

import flow_view

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ";"   # PyInstaller --add-data / --add-binary use ';' on Windows

# --- Data files bundled into _internal/ -----------------------------------
# Paths on the left are relative to the project root; paths on the right
# are where they end up inside the frozen bundle.  resource.py resolves
# these at runtime via sys._MEIPASS.
DATAS = [
    (os.path.join(ROOT, "help"), "help"),
    (os.path.join(ROOT, "locales"), "locales"),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "showcase"), "showcase"),
    (os.path.join(ROOT, "LICENSE"), "."),
]

# --- Hidden imports -------------------------------------------------------
# Modules PyInstaller's hook does not always detect, plus every AuthorBoard
# module (cheap insurance against a future import that's behind a signal or
# dynamic dispatch).  QtPrintSupport is required by QTextEdit on some
# platforms; QtSvg for the window icon; QtNetwork for QDesktopServices on
# some Linux setups.
HIDDEN = [
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtNetwork",
    "main", "canvas", "inspector", "note_item", "pin_item",
    "connection_item", "rich_text", "editor_dialog", "comments_panel",
    "spellcheck", "attachments", "shelf", "library", "timeline",
    "models", "storage", "undo", "settings", "settings_dialog",
    "help_dialog", "about_dialog", "i18n", "theme", "widgets",
    "palette", "stats", "manuscript", "export", "version", "resource",
    "flow_view", "group_item",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--console",
        action="store_true",
        help="Keep the console window (for debugging a frozen build).",
    )
    a = ap.parse_args()

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name", "AuthorBoard",
        "--paths", ROOT,
        "--hidden-import", ",".join(HIDDEN),
        # Collect the pyspellchecker dictionaries (en, de, ...).  Without
        # this the app crashes when a note is selected: SpellChecker cannot
        # find its resource file inside the frozen bundle.
        "--collect-data", "spellchecker",
        # Qt 6 on Windows needs its platform plugin; --collect-binaries
        # makes sure Qt's DLLs come along even when PyInstaller's hook
        # only sees the Python-level PySide6 import.
        "--collect-binaries", "PySide6",
    ]

    if a.console:
        args.append("--console")
    else:
        args.append("--windowed")

    icon = os.path.join(ROOT, "assets", "logo.ico")
    if os.path.exists(icon):
        args += ["--icon", icon]

    for src, dest in DATAS:
        if os.path.exists(src):
            args += ["--add-data", f"{src}{SEP}{dest}"]

    args.append(os.path.join(ROOT, "main.py"))

    print("Running:", " ".join(args))
    result = subprocess.run(args)
    if result.returncode != 0:
        return result.returncode

    out = os.path.join(ROOT, "dist", "AuthorBoard")
    print()
    print("Built:", out)
    print("Distribute the whole folder (zip it). The exe is AuthorBoard.exe inside it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())