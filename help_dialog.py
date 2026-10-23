# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""In-app documentation (Help -> Documentation, F1).

The manual is a set of Markdown files in ``help/<language>/NN-topic.md``.  The
window shows the topic list on the left and the rendered topic on the right.
The search box looks through *all* topics: it lists the topics that contain the
text (with the number of hits) and highlights every hit in the open topic.

Adding a language: copy ``help/en`` to ``help/<code>`` and translate the files.
Missing languages fall back to English.
"""

import os
import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import i18n
from i18n import tr
from resource import resource_path

HELP_DIR = resource_path("help")


def load_topics(lang):
    """Read all topics of a language -> list of ``(topic_id, title, markdown)``.

    ``topic_id`` is the file name without ``.md`` (used by ``topic:`` links)."""

    folder = os.path.join(HELP_DIR, lang)
    if not os.path.isdir(folder):
        folder = os.path.join(HELP_DIR, "en")

    topics = []
    try:
        names = sorted(f for f in os.listdir(folder) if f.endswith(".md"))
    except OSError:
        names = []

    for name in names:
        with open(os.path.join(folder, name), "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"^#\s+(.+)$", text, re.M)
        topics.append((name[:-3], m.group(1).strip() if m else name[:-3], text))
    return topics


class HelpDialog(QDialog):
    """Searchable documentation window."""

    def __init__(self, parent=None):
        """Build the window and show all topics."""
        super().__init__(parent)
        self.setWindowTitle(tr("AuthorBoard – Dokumentation"))
        self.resize(1050, 720)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        self.topics = load_topics(i18n.current_language())
        self._current = None                  # id of the displayed topic
        self._hit_cursors = []                # cursors of all hits (for next/prev)

        root = QHBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        # ----- left: search + topic list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Dokumentation durchsuchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(tr("Durchsucht alle Kapitel. Treffer werden im Text markiert."))
        ll.addWidget(self.search)
        self.result_label = QLabel("")
        self.result_label.setObjectName("Muted")
        ll.addWidget(self.result_label)
        self.list = QListWidget()
        ll.addWidget(self.list, 1)
        split.addWidget(left)

        # ----- right: viewer + hit navigation
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        nav = QHBoxLayout()
        self.hits_label = QLabel("")
        self.hits_label.setObjectName("Muted")
        self.prev_btn = QPushButton("◀")
        self.next_btn = QPushButton("▶")
        self.prev_btn.setToolTip(tr("Vorheriger Treffer"))
        self.next_btn.setToolTip(tr("Nächster Treffer"))
        nav.addWidget(self.hits_label, 1)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        rl.addLayout(nav)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        rl.addWidget(self.browser, 1)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        split.setSizes([300, 750])

        self.search.textChanged.connect(self.run_search)
        self.list.currentRowChanged.connect(self._row_changed)
        self.browser.anchorClicked.connect(self._link_clicked)
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))

        self.run_search("")

    # ------------------------------------------------------------- listing

    def run_search(self, text):
        """Fill the list with all topics, or only the ones containing ``text``."""
        text = text.strip()
        keep = self._current
        self.list.blockSignals(True)
        self.list.clear()
        shown = []

        for tid, title, md in self.topics:
            hits = md.lower().count(text.lower()) if text else 0
            if text and hits == 0:
                continue
            label = f"{title}" + (f"   ({hits})" if text else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tid)
            self.list.addItem(item)
            shown.append(tid)

        self.list.blockSignals(False)
        self.result_label.setText(
            tr("{n} Kapitel gefunden", n=len(shown)) if text else tr("{n} Kapitel", n=len(shown)))

        if shown:
            self.show_topic(keep if keep in shown else shown[0])
        else:
            self.browser.setMarkdown("")
            self.hits_label.setText(tr("Keine Treffer"))

    def _row_changed(self, row):
        """A topic was chosen in the list."""
        item = self.list.item(row)
        if item:
            self.show_topic(item.data(Qt.ItemDataRole.UserRole), select=False)

    # --------------------------------------------------------------- viewer

    def show_topic(self, topic_id, select=True):
        """Render a topic and highlight the current search text in it."""
        md = next((m for tid, _t, m in self.topics if tid == topic_id), None)
        if md is None:
            return
        self._current = topic_id
        self.browser.setMarkdown(md)

        if select:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole) == topic_id:
                    self.list.blockSignals(True)
                    self.list.setCurrentRow(i)
                    self.list.blockSignals(False)
        self._highlight(self.search.text().strip())

    def _highlight(self, text):
        """Mark every occurrence of ``text`` and jump to the first one."""
        self._hit_cursors = []
        selections = []
        if text:
            doc = self.browser.document()
            cursor = QTextCursor(doc)
            while True:
                cursor = doc.find(text, cursor)
                if cursor.isNull():
                    break
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cursor
                sel.format.setBackground(QColor(255, 213, 79, 120))
                selections.append(sel)
                self._hit_cursors.append(QTextCursor(cursor))
        self.browser.setExtraSelections(selections)
        self._hit_index = -1
        self.hits_label.setText(tr("{n} Treffer in diesem Kapitel", n=len(selections)) if text else "")
        if selections:
            self._step(1)
        else:
            self.browser.moveCursor(QTextCursor.MoveOperation.Start)

    def _step(self, direction):
        """Jump to the next/previous hit."""
        if not self._hit_cursors:
            return
        self._hit_index = (self._hit_index + direction) % len(self._hit_cursors)
        self.browser.setTextCursor(self._hit_cursors[self._hit_index])
        self.browser.ensureCursorVisible()

    def _link_clicked(self, url):
        """``topic:<id>`` links switch topics, everything else opens in the browser."""
        if url.scheme() == "topic":
            self.show_topic(url.path() or url.toString()[6:])
        elif url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
