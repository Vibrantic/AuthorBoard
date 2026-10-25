# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The update dialog: release notes preview + Update / Tomorrow / Next week."""

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from i18n import tr
from version import __version__
from updater import ReleaseInfo, set_skip


class UpdateDialog(QDialog):
    """Shows the release notes of ``info`` and lets the user choose."""

    UPDATE_NOW = 0
    LATER = 1           # close → prompt again next start
    TOMORROW = 2        # skip 1 day
    NEXT_WEEK = 3       # skip 7 days

    def __init__(self, info: ReleaseInfo, qsettings: QSettings, parent=None):
        super().__init__(parent)
        self.info = info
        self.qsettings = qsettings
        self.choice = self.LATER

        self.setWindowTitle(tr("Update verfügbar — AuthorBoard {v}", v=info.version))
        self.resize(680, 560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(10)

        title = QLabel(tr("AuthorBoard {new} ist verfügbar", new=info.version))
        title.setStyleSheet("font-size: 18pt; font-weight: 700;")
        lay.addWidget(title)

        current = QLabel(tr("Installiert: {v}  ·  Neu: {new}",
                            v=__version__, new=info.version))
        current.setObjectName("Muted")
        lay.addWidget(current)

        notes_label = QLabel(tr("Was ist neu").upper())
        notes_label.setObjectName("Section")
        lay.addWidget(notes_label)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        if hasattr(browser, "setMarkdown"):
            browser.setMarkdown(info.body)          # Qt 6.4+
        else:
            browser.setPlainText(info.body)
        lay.addWidget(browser, 1)

        buttons = QHBoxLayout()
        now = QPushButton(tr("Jetzt aktualisieren"))
        now.setDefault(True)
        tomorrow = QPushButton(tr("Morgen erinnern"))
        week = QPushButton(tr("In einer Woche erinnern"))
        later = QPushButton(tr("Später"))
        now.setToolTip(tr("Update herunterladen und AuthorBoard neu starten"))
        tomorrow.setToolTip(tr("Erst beim nächsten Start wieder fragen (1 Tag)"))
        week.setToolTip(tr("Erst in einer Woche wieder fragen"))
        later.setToolTip(tr("Beim nächsten Start wieder fragen"))

        now.clicked.connect(lambda: self._choose(self.UPDATE_NOW))
        tomorrow.clicked.connect(lambda: self._choose(self.TOMORROW))
        week.clicked.connect(lambda: self._choose(self.NEXT_WEEK))
        later.clicked.connect(lambda: self._choose(self.LATER))

        buttons.addWidget(now)
        buttons.addWidget(tomorrow)
        buttons.addWidget(week)
        buttons.addStretch(1)
        buttons.addWidget(later)
        lay.addLayout(buttons)

    def _choose(self, choice):
        self.choice = choice
        if choice == self.TOMORROW:
            set_skip(self.info, 1, self.qsettings)
        elif choice == self.NEXT_WEEK:
            set_skip(self.info, 7, self.qsettings)
        elif choice == self.LATER:
            set_skip(self.info, 0, self.qsettings)
        self.accept()