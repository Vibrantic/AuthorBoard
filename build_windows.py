#!/usr/bin/env python3
# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build AuthorBoard on Windows (onedir) plus the standalone updater.

    python build_windows.py                 # main app + updater
    python build_windows.py --console       # main app keeps a console window
    python build_windows.py --no-updater    # skip the updater build

Produces:

    dist/AuthorBoard/AuthorBoard.exe         (main app, onedir)
    dist/AuthorBoard/_internal/...           (PyInstaller runtime)
    dist/AuthorBoardUpdater/AuthorBoardUpdater.exe

The updater is installed by the Inno Setup installer into
``<install>/updater/`` next to the main exe, so ``MainWindow._start_installer``
can launch it.  The update archive you upload to GitHub is a *zip of the whole
``dist/AuthorBoard`` folder* (which includes ``updater/``), not a patch.

The spellchecker dictionaries (en.json.gz, de.json.gz) are collected with
``--collect-data`` so spell checking works in the frozen build.  Without it
the app crashes the moment a note is selected, because
``SpellChecker(language=...)`` cannot find its resource file.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ";"   # PyInstaller --add-data / --add-binary use ';' on Windows

# --- Data files bundled into the main app --------------------------------
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

# --- Hidden imports (main app) -------------------------------------------
# Modules PyInstaller's hook does not always detect, plus every AuthorBoard
# module (cheap insurance against a future import that's behind a signal or
# dynamic dispatch).  QtPrintSupport is required by QTextEdit on some
# platforms; QtSvg for the window icon; QtNetwork for the updater.
HIDDEN = [
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtNetwork",
    "PySide6.QtGui",
    "PySide6.QtCore",
    "PySide6.QtWidgets",
    "main", "canvas", "inspector", "note_item", "pin_item",
    "connection_item", "rich_text", "editor_dialog", "comments_panel",
    "spellcheck", "attachments", "shelf", "library", "timeline",
    "models", "storage", "undo", "settings", "settings_dialog",
    "help_dialog", "about_dialog", "i18n", "theme", "widgets",
    "palette", "stats", "manuscript", "export", "version", "resource",
    "flow_view", "group_item",
    "updater", "updater_dialog",
]

# --- Hidden imports for the standalone updater ---------------------------
# The updater is a minimal Qt app; it must not pull in any AuthorBoard UI
# module (they would drag in the whole PySide6 widget set unnecessarily).
HIDDEN_UPDATER = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "updater_main",
]


def _run(args, label):
    print(f"=== {label} ===")
    print("Running:", " ".join(args))
    print()
    result = subprocess.run(args)
    if result.returncode != 0:
        print(f"FAILED: {label} (exit {result.returncode})")
        return False
    return True


def _clean_previous(build_name):
    """Remove stale artifacts for one PyInstaller build before rebuilding."""
    for path in (
        os.path.join(ROOT, "build", build_name),
        os.path.join(ROOT, "dist", build_name),
    ):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def build_main(console: bool) -> bool:
    """Build the main AuthorBoard application (onedir)."""
    _clean_previous("AuthorBoard")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name", "AuthorBoard",
        "--paths", ROOT,
        "--hidden-import", ",".join(HIDDEN),
        # Spellchecker dictionaries (en, de, ...).  Without this the app
        # crashes when a note is selected inside the frozen bundle.
        "--collect-data", "spellchecker",
        # Qt's DLLs and plugins.  --collect-binaries makes sure the platform
        # plugin and image-format plugins come along even when PyInstaller's
        # hook only sees the Python-level PySide6 import.
        "--collect-binaries", "PySide6",
    ]

    if console:
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
    return _run(args, "main app")


def build_updater() -> bool:
    """Build AuthorBoardUpdater.exe — a minimal Qt app with its own UI."""
    _clean_previous("AuthorBoardUpdater")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name", "AuthorBoardUpdater",
        "--paths", ROOT,
        "--hidden-import", ",".join(HIDDEN_UPDATER),
        "--windowed",
    ]

    icon = os.path.join(ROOT, "assets", "logo.ico")
    if os.path.exists(icon):
        args += ["--icon", icon]

    args.append(os.path.join(ROOT, "updater_main.py"))
    return _run(args, "updater")


def stage_for_installer() -> bool:
    """Copy AuthorBoardUpdater next to AuthorBoard so Inno Setup can pick it up.

    The installer script bundles ``dist/AuthorBoard/*`` and
    ``dist/AuthorBoardUpdater/*`` into two separate folders, but at runtime
    the updater must live at ``<install>/updater/`` relative to the main
    exe.  Doing the staging here keeps the installer script simple and
    keeps the "updater is inside the app folder" invariant — which is
    exactly what the update zip depends on.
    """
    src = os.path.join(ROOT, "dist", "AuthorBoardUpdater")
    dst = os.path.join(ROOT, "dist", "AuthorBoard", "updater")
    if not os.path.isdir(src):
        print(f"WARNING: {src} does not exist — skipping updater staging.")
        return False
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    print(f"Staged updater: {dst}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--console",
        action="store_true",
        help="Keep the console window on the main app (for debugging a frozen build).",
    )
    ap.add_argument(
        "--no-updater",
        action="store_true",
        help="Skip building AuthorBoardUpdater (main app only).",
    )
    a = ap.parse_args()

    if not build_main(a.console):
        return 1

    if not a.no_updater:
        if not build_updater():
            return 1
        stage_for_installer()

    out = os.path.join(ROOT, "dist", "AuthorBoard")
    print()
    print("Built:", out)
    print("Distribute:")
    print("  - release zip:  zip dist/AuthorBoard/  (contains updater/ for in-app updates)")
    print("  - installer:    dist/AuthorBoard/ must exist, then:  iscc installer\\AuthorBoard.iss")
    return 0


if __name__ == "__main__":
    sys.exit(main())