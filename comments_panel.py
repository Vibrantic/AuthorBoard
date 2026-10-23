# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Right-hand dock: the Inspector and the Comments list in one tab widget.

* :class:`CommentsPanel` lists every comment of the open notebook.  A double
  click opens the note in the full-size editor and selects the commented words;
  the Delete button (or the Delete key) removes the comment.
* :class:`RightPanel` is the tab widget that hosts Inspector + Comments.  It
  reports fixed size hints so the dock never changes width when the content
  changes (that would make the board jump).
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from theme import color_icon


class CommentsPanel(QWidget):
    """List of all comments in the notebook, with search."""

    open_requested = Signal(object, str)      # note item, comment id
    delete_requested = Signal(object, str)    # note item, comment id
    focus_requested = Signal(object)  # note item (single click)

    def __init__(self, parent=None):
        """Build the search box, list and buttons."""
        super().__init__(parent)
        self._notes = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Kommentare suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(tr("Durchsucht Kommentartext, kommentierte Textstelle und Notiztitel"))
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setToolTip(tr("Doppelklick öffnet die Notiz und markiert die kommentierte Stelle"))
        layout.addWidget(self.list, 1)

        self.hint = QLabel(tr("Doppelklick: Notiz öffnen und Stelle markieren."))
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        row = QHBoxLayout()
        self.go_button = QPushButton(tr("Zur Stelle springen"))
        self.delete_button = QPushButton(tr("Kommentar löschen"))
        self.delete_button.setObjectName("Danger")
        self.go_button.setToolTip(tr("Notiz im großen Editor öffnen und die Stelle markieren"))
        self.delete_button.setToolTip(tr("Ausgewählten Kommentar samt Markierung entfernen (Entf)"))
        row.addWidget(self.go_button)
        row.addWidget(self.delete_button)
        layout.addLayout(row)

        self.search.textChanged.connect(self.rebuild)
        self.list.itemDoubleClicked.connect(lambda _: self._open_current())
        self.list.itemClicked.connect(self._focus_current)
        self.go_button.clicked.connect(self._open_current)
        self.delete_button.clicked.connect(self._delete_current)

    # ------------------------------------------------------------------ data

    def set_notes(self, notes):
        """Give the panel the notes (NoteItems) whose comments to show."""
        self._notes = list(notes)
        self.rebuild()

    def total(self):
        """Number of comments in the notebook (for the tab title)."""
        return sum(len(n.model.comments) for n in self._notes)

    def rebuild(self, *_):
        """Refill the list, applying the search text."""
        text = self.search.text().strip().lower()
        self.list.clear()

        for note in sorted(self._notes, key=lambda n: n.model.title.lower()):
            for c in note.model.comments:
                haystack = f"{note.model.title} {c.quote} {c.text}".lower()
                if text and text not in haystack:
                    continue
                shown = (f"{note.model.title or tr('Ohne Titel')}\n"
                         f"“{c.quote}”\n💬 {c.text}")
                item = QListWidgetItem(color_icon(note.model.color), shown)
                item.setData(Qt.ItemDataRole.UserRole, (note, c.id))
                self.list.addItem(item)

    # ---------------------------------------------------------------- actions

    def _current(self):
        """``(note, comment_id)`` of the selected row, or None."""
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_current(self):
        """Emit ``open_requested`` for the selected comment."""
        cur = self._current()
        if cur:
            self.open_requested.emit(*cur)

    def _delete_current(self):
        """Emit ``delete_requested`` for the selected comment."""
        cur = self._current()
        if cur:
            self.delete_requested.emit(*cur)

    def keyPressEvent(self, event):
        """Qt event handler: a key was pressed."""
        if event.key() == Qt.Key.Key_Delete:
            self._delete_current()
            return
        super().keyPressEvent(event)

    def _focus_current(self, item):
        """Single-click: emit ``focus_requested`` for the clicked comment's note."""
        cur = item.data(Qt.ItemDataRole.UserRole) if item else None
        if cur is not None:
            self.focus_requested.emit(cur[0])


class RightPanel(QTabWidget):
    """Tab widget with fixed size hints (see module docstring)."""

    def sizeHint(self):
        """Qt: preferred size of the widget."""
        return QSize(390, 640)

    def minimumSizeHint(self):
        """Qt: smallest sensible size of the widget."""
        return QSize(390, 300)
