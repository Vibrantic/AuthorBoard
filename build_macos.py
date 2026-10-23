#!/usr/bin/env python3
"""Build AuthorBoard on macOS (onedir, produces .app)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ":"

DATAS = [
    (os.path.join(ROOT, "help"), "help"),
    (os.path.join(ROOT, "locales"), "locales"),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "showcase"), "showcase"),
    (os.path.join(ROOT, "LICENSE"), "."),
]

HIDDEN = [
    "PySide6.QtSvg", "PySide6.QtSvgWidgets", "PySide6.QtPrintSupport",
    "PySide6.QtNetwork",
    "main", "canvas", "inspector", "note_item", "pin_item",
    "connection_item", "rich_text", "editor_dialog", "comments_panel",
    "spellcheck", "attachments", "shelf", "library", "timeline",
    "models", "storage", "undo", "settings", "settings_dialog",
    "help_dialog", "about_dialog", "i18n", "theme", "widgets",
    "palette", "stats", "manuscript", "export", "version", "resource",
]

args = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean", "--windowed", "--onedir",
    "--name", "AuthorBoard",
    "--paths", ROOT,
    "--hidden-import", ",".join(HIDDEN),
]

icon = os.path.join(ROOT, "assets", "logo.ico")
if os.path.exists(icon):
    args += ["--icon", icon]

for src, dest in DATAS:
    if os.path.exists(src):
        args += ["--add-data", f"{src}{SEP}{dest}"]

args.append(os.path.join(ROOT, "main.py"))
print("Running:", " ".join(args))
subprocess.run(args, check=True)
print("\nDone. macOS bundle: dist/AuthorBoard.app")