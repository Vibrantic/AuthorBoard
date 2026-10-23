#!/usr/bin/env python3
# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build AuthorBoard on Linux (onedir).

    python build_linux.py            # onedir (recommended)
    python build_linux.py --console  # keep the console (for debugging)

Produces dist/AuthorBoard/AuthorBoard (an ELF binary) plus
dist/AuthorBoard/_internal/.  Tar or zip the whole dist/AuthorBoard
folder to distribute.  Users may need to chmod +x AuthorBoard after
extracting from a zip.

The spellchecker dictionaries (en.json.gz, de.json.gz) are collected
with --collect-data so spell checking works in the frozen build.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ":"   # PyInstaller --add-data / --add-binary use ':' on POSIX

# --- Data files bundled into _internal/ -----------------------------------
DATAS = [
    (os.path.join(ROOT, "help"), "help"),
    (os.path.join(ROOT, "locales"), "locales"),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "showcase"), "showcase"),
    (os.path.join(ROOT, "LICENSE"), "."),
]

# --- Hidden imports -------------------------------------------------------
# Modules PyInstaller's hook does not always detect, plus every AuthorBoard
# module.  QtPrintSupport is required by QTextEdit on some platforms;
# QtSvg for the window icon; QtDBus for Linux desktop integration.
HIDDEN = [
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtNetwork",
    "PySide6.QtDBus",
    "main", "canvas", "inspector", "note_item", "pin_item",
    "connection_item", "rich_text", "editor_dialog", "comments_panel",
    "spellcheck", "attachments", "shelf", "library", "timeline",
    "models", "storage", "undo", "settings", "settings_dialog",
    "help_dialog", "about_dialog", "i18n", "theme", "widgets",
    "palette", "stats", "manuscript", "export", "version", "resource",
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
        # Spellchecker dictionaries (en, de, ...).
        "--collect-data", "spellchecker",
        # Qt DLLs and plugins (platform plugin libqxcb.so, image formats,
        # styles, etc.).  Without this the frozen app may fail on a clean
        # machine with "Could not load the Qt platform plugin xcb".
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
    print("Distribute the whole folder (tar.gz or zip).  The binary is AuthorBoard.")
    print("Users may need to run: chmod +x AuthorBoard")
    return 0


if __name__ == "__main__":
    sys.exit(main())