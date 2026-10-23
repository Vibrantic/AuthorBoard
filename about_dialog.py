# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""About dialog: version, origin, licence and disclaimer."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from i18n import tr
from version import APP_NAME, LICENSE_NAME, __version__

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class LicenseDialog(QDialog):
    """Shows the full GPL text from the LICENSE file."""

    def __init__(self, parent=None):
        """Build the dialog and load the LICENSE file."""
        super().__init__(parent)
        self.setWindowTitle(tr("Lizenz – GNU GPL v3"))
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        try:
            with open(os.path.join(BASE_DIR, "LICENSE"), "r", encoding="utf-8") as f:
                view.setPlainText(f.read())
        except OSError:
            view.setPlainText(tr("Die Datei LICENSE wurde nicht gefunden.\n"
                                 "https://www.gnu.org/licenses/gpl-3.0.html"))
        lay.addWidget(view)
        close = QPushButton(tr("Schließen"))
        close.clicked.connect(self.accept)
        lay.addWidget(close)


class AboutDialog(QDialog):
    """Information about the software.  ``open_help`` is called by the
    "Documentation" button."""

    def __init__(self, parent=None, open_help=None):
        """Build the dialog; ``open_help`` is called by the Documentation button."""
        super().__init__(parent)
        self.setWindowTitle(tr("Über AuthorBoard"))
        self.resize(640, 640)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 26pt; font-weight: 700;")
        lay.addWidget(title)
        version = QLabel(tr("Version {v}", v=__version__) + "  ·  " + LICENSE_NAME)
        version.setObjectName("Muted")
        lay.addWidget(version)

        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(self._html())
        lay.addWidget(text, 1)

        row = QHBoxLayout()
        docs = QPushButton(tr("Dokumentation"))
        lic = QPushButton(tr("Lizenz anzeigen …"))
        close = QPushButton(tr("Schließen"))
        docs.setToolTip(tr("Durchsuchbare Dokumentation öffnen"))
        lic.setToolTip(tr("Vollständigen Lizenztext (GNU GPL v3) anzeigen"))
        if open_help:
            docs.clicked.connect(lambda: (self.accept(), open_help()))
        else:
            docs.setEnabled(False)
        lic.clicked.connect(lambda: LicenseDialog(self).exec())
        close.clicked.connect(self.accept)
        row.addWidget(docs)
        row.addWidget(lic)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

    @staticmethod
    def _html():
        """The body text (translated).  Plain HTML for QTextBrowser."""
        h = lambda s: f"<h3 style='color:#6c9cff'>{s}</h3>"
        return (
            f"<p>{tr('Notizbücher für Autorinnen und Autoren: ein Bücherregal, ein Korkboard mit Post-its, Pins und Fäden, Zeitleiste, Rich-Text-Editor mit Kommentaren und vieles mehr.')}</p>"
            + h(tr("Entwicklung"))
            + f"<p>{tr('AuthorBoard entstand in einer fortlaufenden Zusammenarbeit zwischen einem menschlichen Maintainer und zwei KI-Assistenten: <b>Konzept, Richtung und Übersicht</b> durch die Autorinnen und Autoren des Projekts, <b>erste Umsetzung, Architektur, Handbuch und Beispielprojekte</b> durch <b>Claude</b> (Anthropic), <b>Performance-Arbeit, Level-of-Detail-Rendering, Zeitleisten-Neufassung, Undo-Umbau und Fehlerbehebungen</b> durch <b>DeepSeek</b>.')}</p>"
            + h(tr("Wie es entstanden ist"))
            + f"<p>{tr('Jede Funktion, jedes Layout und jede Leistungsverbesserung wurde vom Maintainer angestoßen, ausprobiert und abgenommen. Die Umsetzung entstand im Dialog mit diesem Feedback und wurde nach jedem Schritt geprüft – von der ersten Veröffentlichung über die Leistungsüberarbeitung bis zu den letzten Detailkorrekturen.')}</p>"
            + h(tr("Technik"))
            + "<p>Python 3 · Qt 6 (PySide6) · pyspellchecker</p>"
            + h(tr("Danksagung"))
            + f"<p>{tr('Dank an alle, die AuthorBoard ausprobiert, Fehler gemeldet und Verbesserungen vorgeschlagen haben. Die Projektgeschichte ist im Git-Verlauf einsehbar.')}</p>"
            + h(tr("Lizenz"))
            + f"<p>{tr('Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public License, wie von der Free Software Foundation veröffentlicht, weitergeben und/oder verändern – Version 3 der Lizenz oder (nach Ihrer Wahl) jede spätere Version.')}</p>"
            + f"<p>{tr('Dieses Programm wird in der Hoffnung verbreitet, dass es nützlich ist, aber OHNE JEDE GEWÄHRLEISTUNG – sogar ohne die implizite Gewährleistung der MARKTFÄHIGKEIT oder EIGNUNG FÜR EINEN BESTIMMTEN ZWECK.')}</p>"
            + "<p><a href='https://www.gnu.org/licenses/gpl-3.0.html'>https://www.gnu.org/licenses/gpl-3.0.html</a></p>"
            + h(tr("Haftungsausschluss"))
            + f"<p><b>{tr('Die Software wird „wie sie ist“ bereitgestellt.')}</b> "
              f"{tr('Die Nutzung erfolgt auf eigenes Risiko. Es wird keinerlei Verantwortung oder Haftung übernommen – weder für Schäden, Datenverlust, entgangene Arbeit noch für sonstige Nachteile jeglicher Art, die direkt oder indirekt aus der Nutzung oder Nichtnutzung der Software entstehen. Bitte sichern Sie Ihre Arbeit regelmäßig.')}</p>"
        )
