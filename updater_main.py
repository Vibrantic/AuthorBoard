# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone updater process."""

import argparse
import os
import shutil
import sys
import tempfile
import time
import zipfile

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


def _log(msg: str):
    print(f"[updater] {msg}", file=sys.stderr, flush=True)


class UpdaterWorker(QThread):
    progress = Signal(int, str)
    finished_ok = Signal()
    finished_error = Signal(str)

    def __init__(self, main_pid: int, zip_path: str, target_dir: str):
        super().__init__()
        self.main_pid = main_pid
        self.zip_path = zip_path
        self.target_dir = target_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            _log(f"start: pid={self.main_pid} zip={self.zip_path} target={self.target_dir}")
            self.progress.emit(5, "Warte auf AuthorBoard …")
            self._wait_for_main()

            if self._cancelled:
                return

            parent = os.path.dirname(self.target_dir)
            try:
                staging = tempfile.mkdtemp(prefix="ab-update-", dir=parent)
            except OSError:
                staging = tempfile.mkdtemp(prefix="ab-update-")

            try:
                self.progress.emit(20, "Entpacke Update …")
                with zipfile.ZipFile(self.zip_path) as z:
                    z.extractall(staging)

                if self._cancelled:
                    return

                entries = os.listdir(staging)
                if len(entries) != 1 or not os.path.isdir(os.path.join(staging, entries[0])):
                    raise RuntimeError(f"Unerwartete Zip-Struktur: {entries!r}")

                new_root = os.path.join(staging, entries[0])

                exe_name = ("AuthorBoard.exe" if sys.platform == "win32" else "AuthorBoard")
                if not os.path.isfile(os.path.join(new_root, exe_name)):
                    raise RuntimeError(
                        f"The update archive does not contain {exe_name}. "
                        f"Aborting without touching the current install."
                    )

                if self._cancelled:
                    return

                # --- THE FIX: Wait for the main EXE specifically to be unlocked ---
                target_exe = os.path.join(self.target_dir, exe_name)
                for attempt in range(10):
                    if not os.path.exists(target_exe):
                        break
                    try:
                        # Try to open the main EXE for appending. If it succeeds, it's unlocked.
                        with open(target_exe, "ab"):
                            pass
                        break  # It's unlocked, we can proceed
                    except OSError:
                        self.progress.emit(50, f"Warte auf Freigabe der EXE … ({attempt + 1}/10)")
                        time.sleep(1)
                else:
                    raise RuntimeError(
                        "AuthorBoard.exe is still locked by Windows (Antivirus?). "
                        "Please close it manually and try again."
                    )

                self.progress.emit(70, "Ersetze Dateien …")

                # --- THE FIX: Copy files directly instead of renaming folders ---
                for root, dirs, files in os.walk(new_root):
                    # Calculate the relative path to recreate the folder structure
                    rel_path = os.path.relpath(root, new_root)
                    dest_dir = os.path.join(self.target_dir, rel_path) if rel_path != "." else self.target_dir

                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)

                    for file in files:
                        src_file = os.path.join(root, file)
                        dst_file = os.path.join(dest_dir, file)

                        try:
                            # copy2 preserves file metadata and overwrites existing files safely
                            shutil.copy2(src_file, dst_file)
                        except OSError as exc:
                            _log(f"Could not copy {file}: {exc}")
                            # If we can't overwrite a specific file, we skip it and continue.

                self.progress.emit(90, "Räume auf …")

                self.progress.emit(100, "Fertig")
                self.finished_ok.emit()
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        except Exception as exc:
            _log(f"FAILED: {exc}")
            self.finished_error.emit(str(exc))

    def _wait_for_main(self):
        if self.main_pid <= 0:
            return
        deadline = time.time() + 10
        while time.time() < deadline:
            if not self._pid_alive(self.main_pid):
                _log("main app exited; waiting 2s for process teardown")
                time.sleep(2.0)
                return
            if self._cancelled:
                return
            time.sleep(0.2)
        raise RuntimeError("AuthorBoard is still running after 10 s.")

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                result = kernel32.WaitForSingleObject(handle, 0)
                return result in (0x102, 0xFFFFFFFF)
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class UpdaterWindow(QDialog):
    def __init__(self, worker: UpdaterWorker, exe_path: str):
        super().__init__()
        self.worker = worker
        self.exe_path = exe_path
        self._finished = False

        self.setWindowTitle("AuthorBoard — Update")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.resize(500, 200)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)

        self.label = QLabel("Update wird vorbereitet …")
        self.label.setWordWrap(True)
        self.label.setMinimumHeight(48)
        lay.addWidget(self.label)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.bar)
        lay.addStretch(1)

        self.button_row = QHBoxLayout()
        self.button_row.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.close_btn.clicked.connect(self._on_close_clicked)
        self.close_btn.setVisible(False)
        self.button_row.addWidget(self.close_btn)
        lay.addLayout(self.button_row)

        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.finished_error.connect(self._on_error)

    def start(self):
        self.worker.start()

    def _on_progress(self, pct: int, text: str):
        self.bar.setValue(pct)
        self.label.setText(text)

    def _on_done(self):
        self._finished = True
        self.label.setText("AuthorBoard wird gestartet …")
        QTimer.singleShot(400, self._launch_and_quit)

    def _on_error(self, message: str):
        self._finished = True
        self.label.setText(f"Update fehlgeschlagen:\n{message}")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.close_btn.setVisible(True)

    def _on_close_clicked(self):
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        self.reject()

    def _launch_and_quit(self):
        from PySide6.QtCore import QProcess
        _log(f"launching new app: {self.exe_path}")
        ok = QProcess.startDetached(self.exe_path, [])
        if not ok:
            self.label.setText(
                "Update abgeschlossen, aber die neue AuthorBoard.exe konnte "
                "nicht gestartet werden.\nBitte starten Sie sie von Hand aus "
                f"dem Ordner:\n{os.path.dirname(self.exe_path)}")
            self.close_btn.setVisible(True)
            return
        self.accept()

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
            if self.worker.isRunning():
                self.worker.wait()
        super().closeEvent(event)


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