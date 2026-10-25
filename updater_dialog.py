# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The update dialog: release notes preview, download progress and log.

One dialog does the whole flow:

1. The user sees the release notes and picks an action.
2. If they pick **Update now**, the release-notes area is replaced by a
   progress bar and a **log** area that shows every diagnostic line from
   ``UpdateChecker`` (URL, redirects, HTTP status, byte counts, error
   messages).
3. On success, the dialog closes and the caller launches the updater.
   On failure, the dialog stays open with the log visible and a
   **Copy log** button.

The dialog is decoupled from ``MainWindow``: it connects to an
``UpdateChecker`` instance passed in by the caller and emits
``download_succeeded(path)`` / stays open on failure.
"""

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from i18n import tr
from version import __version__
from updater import ReleaseInfo, set_skip, UpdateChecker


class UpdateDialog(QDialog):
    """Release notes preview + download progress + diagnostic log."""

    UPDATE_NOW = 0
    LATER = 1
    TOMORROW = 2
    NEXT_WEEK = 3

    # Emitted after a successful download, with the local path of the archive.
    # The caller is expected to launch the installer / updater process.
    download_succeeded = Signal(str)

    def __init__(
        self,
        info: ReleaseInfo,
        checker: UpdateChecker,
        qsettings: QSettings,
        target_dir: str,
        parent=None,
    ):
        super().__init__(parent)
        self.info = info
        self.checker = checker
        self.qsettings = qsettings
        self.target_dir = target_dir
        self.choice = self.LATER
        self._downloading = False

        self.setWindowTitle(tr("Update verfügbar — AuthorBoard {v}", v=info.version))
        self.resize(720, 640)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)

        # --- header
        title = QLabel(tr("AuthorBoard {new} ist verfügbar", new=info.version))
        title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        lay.addWidget(title)

        current = QLabel(tr("Installiert: {v}  ·  Neu: {new}",
                            v=__version__, new=info.version))
        current.setObjectName("Muted")
        lay.addWidget(current)

        # --- release notes
        notes_label = QLabel(tr("Was ist neu").upper())
        notes_label.setObjectName("Section")
        lay.addWidget(notes_label)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        if hasattr(self.browser, "setMarkdown"):
            self.browser.setMarkdown(info.body)
        else:
            self.browser.setPlainText(info.body)
        lay.addWidget(self.browser, 3)

        # --- progress area (hidden until the user picks Update now)
        self.progress_box = QWidget()
        pl = QVBoxLayout(self.progress_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)

        self.progress_label = QLabel(tr("AutorBoard wird heruntergeladen …"))
        self.progress_label.setObjectName("Section")
        pl.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        pl.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(140)
        self.log_view.setStyleSheet(
            "QPlainTextEdit { font-family: monospace; font-size: 9pt; }")
        pl.addWidget(self.log_view, 1)

        copy_row = QHBoxLayout()
        copy_row.addStretch(1)
        self.copy_log_btn = QPushButton(tr("Log kopieren"))
        self.copy_log_btn.setToolTip(tr("Diagnose in die Zwischenablage kopieren"))
        self.copy_log_btn.clicked.connect(self._copy_log)
        copy_row.addWidget(self.copy_log_btn)
        pl.addLayout(copy_row)

        self.progress_box.setVisible(False)
        lay.addWidget(self.progress_box, 4)

        # --- buttons
        buttons = QHBoxLayout()
        self.now_btn = QPushButton(tr("Jetzt aktualisieren"))
        self.now_btn.setDefault(True)
        self.tomorrow_btn = QPushButton(tr("Morgen erinnern"))
        self.week_btn = QPushButton(tr("In einer Woche erinnern"))
        self.later_btn = QPushButton(tr("Später"))
        self.now_btn.setToolTip(tr("Update herunterladen und AuthorBoard neu starten"))
        self.tomorrow_btn.setToolTip(tr("Erst beim nächsten Start wieder fragen (1 Tag)"))
        self.week_btn.setToolTip(tr("Erst in einer Woche wieder fragen"))
        self.later_btn.setToolTip(tr("Beim nächsten Start wieder fragen"))

        self.now_btn.clicked.connect(self._on_update_now)
        self.tomorrow_btn.clicked.connect(lambda: self._choose(self.TOMORROW))
        self.week_btn.clicked.connect(lambda: self._choose(self.NEXT_WEEK))
        self.later_btn.clicked.connect(lambda: self._choose(self.LATER))

        buttons.addWidget(self.now_btn)
        buttons.addWidget(self.tomorrow_btn)
        buttons.addWidget(self.week_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.later_btn)
        lay.addLayout(buttons)

        # --- wire the checker
        self.checker.log.connect(self._append_log)
        self.checker.download_progress.connect(self._on_progress)
        self.checker.download_finished.connect(self._on_finished)
        self.checker.download_failed.connect(self._on_failed)

    # ---------------------------------------------------------- buttons

    def _choose(self, choice):
        self.choice = choice
        if choice == self.TOMORROW:
            set_skip(self.info, 1, self.qsettings)
        elif choice == self.NEXT_WEEK:
            set_skip(self.info, 7, self.qsettings)
        elif choice == self.LATER:
            set_skip(self.info, 0, self.qsettings)
        self.accept()

    def _on_update_now(self):
        """Start the download in-place; the dialog stays open."""
        self._downloading = True
        self.now_btn.setEnabled(False)
        self.tomorrow_btn.setEnabled(False)
        self.week_btn.setEnabled(False)
        self.later_btn.setText(tr("Abbrechen"))
        self.later_btn.setToolTip(tr("Download abbrechen"))
        try:
            self.later_btn.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.later_btn.clicked.connect(self._cancel_download)

        # Swap the release-notes view for the progress + log area.
        self.browser.setVisible(False)
        self.progress_box.setVisible(True)
        self.progress_bar.setRange(0, 0)   # busy until first progress
        self._append_log(tr("Update wird heruntergeladen …"))

        self.checker.download(self.info, self.target_dir)

    def _cancel_download(self):
        self._downloading = False
        self.checker.cancel_download()
        self._append_log(tr("Download abgebrochen."))
        self.reject()

    def _copy_log(self):
        text = self.log_view.toPlainText()
        QGuiApplication.clipboard().setText(text)
        self._append_log(tr("Log in die Zwischenablage kopiert."))

    # -------------------------------------------------------- progress

    def _append_log(self, text: str):
        self.log_view.appendPlainText(text)

    def _on_progress(self, received: int, total: int):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(received)
            pct = int(received * 100 / total)
            self.progress_label.setText(
                tr("Download: {r} / {t} Bytes ({pct} %)",
                   r=received, t=total, pct=pct))
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText(
                tr("Download: {r} Bytes", r=received))

    def _on_finished(self, path: str):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText(tr("Download abgeschlossen. Installiere …"))
        self._append_log(tr("Download abgeschlossen: {p}", p=path))
        # Give the user ~400 ms to see the bar before the dialog closes.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(400, lambda: self.download_succeeded.emit(path))

    def _on_failed(self, message: str):
        self._downloading = False
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText(tr("Download fehlgeschlagen"))
        self._append_log(tr("FEHLER: {m}", m=message))
        # Keep the dialog open; the buttons are re-enabled so the user can
        # retry or postpone.
        self.now_btn.setEnabled(True)
        self.tomorrow_btn.setEnabled(True)
        self.week_btn.setEnabled(True)
        try:
            self.later_btn.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.later_btn.setText(tr("Schließen"))
        self.later_btn.clicked.connect(self.reject)