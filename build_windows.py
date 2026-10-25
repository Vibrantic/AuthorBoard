#!/usr/bin/env python3
# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build AuthorBoard on Windows: main app + updater + installer.

    python build_windows.py                 # main + updater + installer
    python build_windows.py --console       # main app keeps a console window
    python build_windows.py --no-updater    # skip the updater build
    python build_windows.py --no-installer  # skip the installer build
    python build_windows.py --no-iscc       # same as --no-installer (alias)

Produces:

    dist/AuthorBoard/AuthorBoard.exe         (main app, onedir)
    dist/AuthorBoard/_internal/...           (PyInstaller runtime)
    dist/AuthorBoard/updater/...             (staged updater, self-contained)
    dist/AuthorBoardUpdater/AuthorBoardUpdater.exe
    installer/Output/AuthorBoard-Setup-<version>.exe

The installer version is read from ``version.py:__version__`` at build time
and written into ``installer/_version.iss`` (an Inno Setup include).  This
keeps ``About → Version`` and ``AuthorBoard-Setup-<version>.exe`` in sync
without hand-editing the .iss on every release.

The update archive you upload to GitHub is a *zip of the whole
``dist/AuthorBoard`` folder* (which includes ``updater/``), not a patch.
Without ``updater/`` inside the zip, an in-app update on a user's machine
would land a new tree with no updater for the *next* update.

``iscc`` (Inno Setup's compiler) is only run if it is on PATH; if it is not,
the build succeeds and prints how to install Inno Setup.  Pass ``--no-iscc``
to skip it entirely.

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

# Import the version *before* PyInstaller is invoked, so the installer
# version is consistent with the About dialog even if the build fails
# halfway through.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from version import __version__  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
SEP = ";"   # PyInstaller --add-data / --add-binary use ';' on Windows

INSTALLER_DIR = os.path.join(ROOT, "installer")
INSTALLER_ISS = os.path.join(INSTALLER_DIR, "AuthorBoard.iss")
INSTALLER_OUT = os.path.join(INSTALLER_DIR, "Output")
INSTALLER_EXE = os.path.join(INSTALLER_OUT, f"AuthorBoard-Setup-{__version__}.exe")

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
    "updater", "updater_dialog", "paths",
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


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _run(args, label, check=True):
    """Run ``args``, print the command, return True on success."""
    print(f"=== {label} ===")
    print("Running:", " ".join(args))
    print()
    result = subprocess.run(args)
    if check and result.returncode != 0:
        print(f"FAILED: {label} (exit {result.returncode})")
        return False
    return result.returncode == 0


def _clean_previous(build_name):
    """Remove stale artifacts for one PyInstaller build before rebuilding."""
    for path in (
        os.path.join(ROOT, "build", build_name),
        os.path.join(ROOT, "dist", build_name),
    ):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


def _find_iscc():
    """Locate ``iscc.exe``.  Checks PATH first, then the two default install
    locations on Windows (per-user and per-machine)."""
    exe = shutil.which("iscc") or shutil.which("ISCC")
    if exe:
        return exe
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------

def write_installer_version() -> bool:
    """Write ``installer/_version.iss`` with the current ``__version__``.

    ``iscc`` (Inno Setup's compiler) cannot run Python, so this is the
    only practical way to keep ``AuthorBoard.iss`` and ``version.py`` in
    sync.  ``AuthorBoard.iss`` reads this file via
    ``ReadIni(AddBackslash(SourcePath) + "_version.iss", ...)``.

    Written as UTF-8 *without* a BOM: a BOM would make ``ReadIni`` return
    ``"\\ufeff1.2.3"`` and break the ``AppVersion`` directive.
    """
    path = os.path.join(INSTALLER_DIR, "_version.iss")
    os.makedirs(INSTALLER_DIR, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("[build]\n")
            f.write(f"version={__version__}\n")
    except OSError as exc:
        print(f"FAILED: cannot write {path}: {exc}")
        return False
    print(f"Wrote {path}  ->  version={__version__}")
    return True


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
    """Build ``AuthorBoardUpdater.exe`` — a minimal Qt app with its own UI."""
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
    """Copy ``dist/AuthorBoardUpdater/`` into ``dist/AuthorBoard/updater/``.

    Two consumers rely on this layout:

    * ``installer/AuthorBoard.iss`` ships ``dist/AuthorBoard/*`` as the
      install tree and expects ``updater/AuthorBoardUpdater.exe`` to be
      inside it (so ``MainWindow._start_installer`` finds it).
    * The **release zip** (uploaded to GitHub) must contain ``updater/``
      so a user who installs *this* release can also receive the *next*
      one in-app — the future update only replaces
      ``dist/AuthorBoard/``, and if ``updater/`` were missing there,
      the update after that would have no updater to invoke.
    """
    src = os.path.join(ROOT, "dist", "AuthorBoardUpdater")
    dst = os.path.join(ROOT, "dist", "AuthorBoard", "updater")
    if not os.path.isdir(src):
        print(f"FAILED: {src} does not exist — cannot stage the updater.")
        return False
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    print(f"Staged updater: {dst}")
    return True


def build_installer(skip_iscc: bool) -> bool:
    """Run ``iscc`` against ``installer/AuthorBoard.iss``.

    The .iss reads the version from ``_version.iss`` (written by
    :func:`write_installer_version`), so ``AuthorBoard-Setup-<version>.exe``
    always matches ``version.py:__version__``.
    """
    if skip_iscc:
        print("Skipping installer build (--no-installer / --no-iscc).")
        return True

    if not os.path.isfile(INSTALLER_ISS):
        print(f"FAILED: {INSTALLER_ISS} does not exist.")
        return False

    main_dist = os.path.join(ROOT, "dist", "AuthorBoard")
    if not os.path.isdir(main_dist):
        print(f"FAILED: {main_dist} does not exist — cannot build installer.")
        return False

    iscc = _find_iscc()
    if iscc is None:
        print()
        print("WARNING: Inno Setup's ISCC.exe was not found on PATH.")
        print("         The main app and updater were built; the .exe")
        print("         installer was NOT built.")
        print()
        print("         Install Inno Setup 6:")
        print("           https://jrsoftware.org/isdl.php")
        print("         Then either add its install folder to PATH, or")
        print("         re-run this script — it also checks the two")
        print("         default install locations.")
        return True   # not a hard failure: the main artifacts exist

    args = [
        iscc,
        # SourcePath inside the .iss is the installer folder; it does not
        # depend on our CWD, so we can run iscc from anywhere.
        INSTALLER_ISS,
    ]
    return _run(args, "installer")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

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
    ap.add_argument(
        "--no-installer",
        "--no-iscc",
        action="store_true",
        dest="no_installer",
        help="Skip building the Inno Setup installer.",
    )
    a = ap.parse_args()

    # Version stub first, so a mid-build failure still leaves a valid
    # ``_version.iss`` in place.
    if not write_installer_version():
        return 1

    if not build_main(a.console):
        return 1

    if not a.no_updater:
        if not build_updater():
            return 1
        if not stage_for_installer():
            return 1

    # Only attempt the installer if the staged tree exists — otherwise
    # the .iss has nothing to compile.
    if not a.no_installer and not a.no_updater:
        if not build_installer(skip_iscc=False):
            return 1
    else:
        build_installer(skip_iscc=True)

    main_out = os.path.join(ROOT, "dist", "AuthorBoard")
    updater_out = os.path.join(ROOT, "dist", "AuthorBoardUpdater")

    print()
    print("=" * 72)
    print(f"Build complete — version {__version__}")
    print("=" * 72)
    print()
    print("Main app:  ", main_out)
    print("Updater:   ", updater_out)
    if not a.no_installer and not a.no_updater and os.path.isfile(INSTALLER_EXE):
        print("Installer: ", INSTALLER_EXE)
    print()
    print("Release assets for GitHub:")
    print(f"  • AuthorBoard-Setup-{__version__}.exe")
    print(f"  • AuthorBoard-{__version__}-windows.zip")
    print()
    print("To make the release zip:")
    print(f"  cd dist")
    print(f"  Compress-Archive -Path AuthorBoard -DestinationPath "
          f"AuthorBoard-{__version__}-windows.zip")
    print()
    print("Reminder: keep installer/AuthorBoard.iss in sync only if you")
    print("          bypass this script — the version above is authoritative.")
    return 0


if __name__ == "__main__":
    sys.exit(main())