# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone updater process.

Launched by the main app as::

    AuthorBoardUpdater.exe --pid <main pid> --zip <path> --target <install dir>

Steps:
  1. Wait for the main process to exit (the exe cannot be replaced while
     it runs on Windows).
  2. Extract the zip into a staging folder next to the install.
  3. Rename the old folder, move the new one in, restore on failure.
  4. Start the new AuthorBoard.exe.
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
import zipfile

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)
from PySide6.QtGui import QPalette, QColor

# --------------------------------------------------------------------------
# Worker (runs off the GUI thread so the progress bar stays responsive)
# --------------------------------------------------------------------------


class UpdaterWorker(QThread):
    progress = Signal(int, str)     # percent, status text
    finished_ok = Signal()
    finished_error = Signal(str)

    def __init__(self, main_pid: int, zip_path: str, target_dir: str):
        super().__init__()
        self.main_pid = main_pid
        self.zip_path = zip_path
        self.target_dir = target_dir

    def run(self):
        try:
            self.progress.emit(5, "Warte auf AuthorBoard …")
            self._wait_for_main()

            # Use the install folder if writable (fast — same volume),
            # fall back to %TEMP% otherwise (Program Files case).
            parent = os.path.dirname(self.target_dir)
            try:
                staging = tempfile.mkdtemp(prefix="ab-update-", dir=parent)
            except OSError:
                staging = tempfile.mkdtemp(prefix="ab-update-")

            try:
                self.progress.emit(20, "Entpacke Update …")
                with zipfile.ZipFile(self.zip_path) as z:
                    z.extractall(staging)

                entries = os.listdir(staging)
                if len(entries) != 1 or not os.path.isdir(
                        os.path.join(staging, entries[0])):
                    raise RuntimeError(
                        f"Unerwartete Zip-Struktur: {entries!r}")
                new_root = os.path.join(staging, entries[0])

                exe_name = ("AuthorBoard.exe" if sys.platform == "win32"
                            else "AuthorBoard")
                if not os.path.isfile(os.path.join(new_root, exe_name)):
                    raise RuntimeError(
                        f"The update archive does not contain {exe_name}. "
                        f"Aborting without touching the current install.")

                self.progress.emit(50, "Sichere alte Version …")
                backup = self.target_dir + ".old"
                if os.path.exists(backup):
                    shutil.rmtree(backup, ignore_errors=True)
                os.rename(self.target_dir, backup)

                self.progress.emit(70, "Ersetze Dateien …")
                try:
                    shutil.move(new_root, self.target_dir)
                except Exception:
                    if os.path.exists(self.target_dir):
                        shutil.rmtree(self.target_dir, ignore_errors=True)
                    os.rename(backup, self.target_dir)
                    raise

                self.progress.emit(90, "Räume auf …")
                shutil.rmtree(backup, ignore_errors=True)
                shutil.rmtree(staging, ignore_errors=True)

                self.progress.emit(100, "Fertig")
                self.finished_ok.emit()
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        except Exception as exc:
            self.finished_error.emit(str(exc))

    def _wait_for_main(self):
        """Block until the main process is gone (or 30 s timeout)."""
        if self.main_pid <= 0:
            return
        deadline = time.time() + 30
        while time.time() < deadline:
            if not self._pid_alive(self.main_pid):
                return
            time.sleep(0.2)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # SYNCHRONIZE
            if not handle:
                return False
            try:
                # 0 = WAIT_TIMEOUT means still running
                return kernel32.WaitForSingleObject(handle, 0) == 0x102
            finally:
                kernel32.CloseHandle(handle)
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

class UpdaterWindow(QDialog):
    def __init__(self, worker: UpdaterWorker, exe_path: str):
        super().__init__()
        self.worker = worker
        self.exe_path = exe_path
        self.setWindowTitle("AuthorBoard — Update")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.resize(460, 160)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)

        self.label = QLabel("Update wird vorbereitet …")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        lay.addStretch(1)

        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.finished_error.connect(self._on_error)

    def start(self):
        self.worker.start()

    def _on_progress(self, pct, text):
        self.bar.setValue(pct)
        self.label.setText(text)

    def _on_done(self):
        self.label.setText("AuthorBoard wird gestartet …")
        QTimer.singleShot(400, self._launch_and_quit)

    def _on_error(self, message):
        self.label.setText(f"Update fehlgeschlagen:\n{message}")
        btn = QPushButton("Schließen")
        btn.clicked.connect(self.accept)
        self.layout().addWidget(btn)

    def _launch_and_quit(self):
        from PySide6.QtCore import QProcess
        QProcess.startDetached(self.exe_path, [])
        self.accept()


# --------------------------------------------------------------------------
# Dark palette (mirrors theme.apply_dark_palette without importing theme,
# which would pull in i18n / resource and bloat the updater bundle)
# --------------------------------------------------------------------------


def _apply_dark(app):
    pal = QPalette()
    R = QPalette.ColorRole
    pal.setColor(R.Window, QColor("#16171b"))
    pal.setColor(R.WindowText, QColor("#e6e6ea"))
    pal.setColor(R.Base, QColor("#1e1f24"))
    pal.setColor(R.AlternateBase, QColor("#26272e"))
    pal.setColor(R.Text, QColor("#e6e6ea"))
    pal.setColor(R.Button, QColor("#26272e"))
    pal.setColor(R.ButtonText, QColor("#e6e6ea"))
    pal.setColor(R.Highlight, QColor("#6c9cff"))
    pal.setColor(R.HighlightedText, QColor("#101114"))
    app.setPalette(pal)

# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--target", required=True)
    a = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("AuthorBoard Updater")
    app.setStyle("Fusion")
    _apply_dark(app)

    exe_name = "AuthorBoard.exe" if sys.platform == "win32" else "AuthorBoard"
    exe_path = os.path.join(a.target, exe_name)

    worker = UpdaterWorker(a.pid, a.zip, a.target)
    win = UpdaterWindow(worker, exe_path)
    win.show()
    win.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())