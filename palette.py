# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The Shift+Space command palette: search a note type and create a note.
"""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from theme import color_icon
from i18n import tr, N_

NEW_TYPE = "__new__"


class CommandPalette(QDialog):
    """Shift+Leertaste: Notizart suchen (oder neue anlegen)."""

    def __init__(self, note_types, parent=None):
        """Build the search field and result list."""
        super().__init__(
            parent,
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )

        self.setObjectName("Palette")
        self.setModal(True)
        self.resize(440, 380)

        self.note_types = note_types
        self.selected_key = None
        self.new_label = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText(
            tr("Notizart suchen … (z. B. Charakter, Ort, Kapitel)")
        )
        layout.addWidget(self.input)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        hint = QLabel(tr("↑ ↓ wählen    ⏎ erstellen    Esc schließen"))
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        self.input.setToolTip(
            tr("Tippen filtert die Notizarten. Gibt es keinen Treffer,\n"
            "kann eine neue Notizart angelegt werden.")
        )
        self.input.textChanged.connect(self.refresh)
        self.input.installEventFilter(self)
        self.list.itemClicked.connect(lambda _: self.accept_current())

        self.refresh()

    def showEvent(self, event):
        """Qt event handler: the widget is about to be shown."""
        super().showEvent(event)

        parent = self.parentWidget()
        if parent is not None:
            g = parent.geometry()
            self.move(
                g.center().x() - self.width() // 2,
                g.top() + g.height() // 6
            )

        self.input.setFocus()

    def refresh(self):

        """Filter note types by the typed text (+ 'create new type' entry)."""
        query = self.input.text().strip().lower()

        self.list.clear()

        exact = False

        for t in self.note_types.values():
            if query and query not in t.label.lower() \
                    and query not in t.key.lower():
                continue

            if query and t.label.lower() == query:
                exact = True

            item = QListWidgetItem(color_icon(t.color, 16), t.label)
            item.setData(Qt.ItemDataRole.UserRole, t.key)

            if t.attributes:
                item.setToolTip(tr("Attribute: ") + ", ".join(t.attributes))

            self.list.addItem(item)

        if query and not exact:
            item = QListWidgetItem(
                tr("Neue Notizart anlegen: „{name}“", name=self.input.text().strip())
            )
            item.setData(Qt.ItemDataRole.UserRole, NEW_TYPE)
            self.list.addItem(item)

        if self.list.count():
            self.list.setCurrentRow(0)

    def eventFilter(self, obj, event):

        """Qt: filter events of another object (return True to swallow them)."""
        if obj is self.input and event.type() == QEvent.Type.KeyPress:

            key = event.key()
            row = self.list.currentRow()

            if key == Qt.Key.Key_Down:
                self.list.setCurrentRow(
                    min(row + 1, self.list.count() - 1)
                )
                return True

            if key == Qt.Key.Key_Up:
                self.list.setCurrentRow(max(row - 1, 0))
                return True

            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept_current()
                return True

        return super().eventFilter(obj, event)

    def accept_current(self):

        """Accept the highlighted entry."""
        item = self.list.currentItem()
        if item is None:
            return

        key = item.data(Qt.ItemDataRole.UserRole)

        if key == NEW_TYPE:
            self.new_label = self.input.text().strip()
        else:
            self.selected_key = key

        self.accept()
