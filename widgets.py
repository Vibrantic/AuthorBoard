# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Small reusable widgets used by the Inspector and dialogs.

* :class:`GrowHandle`     - a drag bar that lets the user resize a list/table.
* :class:`TagEdit`        - a comma separated line edit with tag auto-completion.
* :class:`AttachmentList` - a list widget that accepts dropped files.
"""

from PySide6.QtCore import QRect, QStringListModel, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QFrame,
    QLineEdit,
    QListWidget,
)

from i18n import tr
from settings import settings


class GrowHandle(QFrame):
    """A thin bar placed under a widget; dragging it changes the widget's height.

    The chosen height is remembered in the application settings
    (``panel_heights``) under ``key`` and restored the next time.
    """

    def __init__(self, target, key, default_height=130, min_height=70,
                 max_height=900, parent=None):
        """Attach a resize handle to ``target``; the height is remembered under ``key``."""
        super().__init__(parent)
        self.target = target
        self.key = key
        self.min_height = min_height
        self.max_height = max_height
        self._drag = None

        self.setFixedHeight(10)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip(tr("Ziehen, um die Höhe der Liste zu ändern"))

        saved = (settings.get("panel_heights") or {}).get(key, default_height)
        self.set_height(saved)

    def set_height(self, h):
        """Set the target's height (clamped to min/max)."""
        h = max(self.min_height, min(self.max_height, int(h)))
        self.target.setMinimumHeight(h)
        self.target.setMaximumHeight(h)

    # -- mouse handling: remember start y and start height, resize while dragging
    def mousePressEvent(self, event):
        """Qt event handler: start dragging."""
        self._drag = (event.globalPosition().y(), self.target.height())

    def mouseMoveEvent(self, event):
        """Qt event handler: resize while dragging."""
        if self._drag is not None:
            y0, h0 = self._drag
            self.set_height(h0 + event.globalPosition().y() - y0)

    def mouseReleaseEvent(self, event):
        """Qt event handler: end dragging and remember the height."""
        self._drag = None
        heights = dict(settings.get("panel_heights") or {})
        heights[self.key] = self.target.height()
        settings.set("panel_heights", heights)

    def paintEvent(self, event):
        """Three small dots in the middle as a "grip" hint."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5d5e69"))
        cx, cy = self.width() / 2, self.height() / 2
        for dx in (-8, 0, 8):
            p.drawEllipse(int(cx + dx - 1.5), int(cy - 1.5), 3, 3)


class TagEdit(QLineEdit):
    """Line edit for comma separated tags with auto-completion.

    Only the tag under the cursor (the text after the last comma) is completed,
    and tags that are already in the field are not offered again.  The list of
    suggestions is book specific - the main window passes it via
    :meth:`set_suggestions`.
    """

    def __init__(self, parent=None):
        """Create the line edit and its completer."""
        super().__init__(parent)
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.activated[str].connect(self._insert_completion)
        self.textEdited.connect(self._update_completion)

    def set_suggestions(self, tags):
        """Set the known tags (book specific)."""
        self._all = sorted(set(tags), key=str.lower)
        self._refresh_model()

    def _refresh_model(self):
        """Offer every known tag that is not yet typed into the field."""
        present = {t.strip().lstrip("#").lower() for t in self.text().split(",")[:-1]}
        self._model.setStringList(
            [t for t in getattr(self, "_all", []) if t.lower() not in present])

    def current_token(self):
        """Text of the tag being typed (between the last comma and the cursor)."""
        before = self.text()[: self.cursorPosition()]
        return before.rsplit(",", 1)[-1].strip().lstrip("#")

    def _update_completion(self, _text=None):
        """Show / hide the suggestion pop-up for the current token."""
        self._refresh_model()
        token = self.current_token()
        if not token:
            self._completer.popup().hide()
            return
        self._completer.setCompletionPrefix(token)
        if self._completer.completionCount() == 0:
            self._completer.popup().hide()
            return
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        self._completer.complete(QRect(0, 0, self.width(), self.height()))

    def _insert_completion(self, tag):
        """Replace the tag being typed by the chosen one and append ', '."""
        text = self.text()
        tokens = [t.strip() for t in text.split(",")]
        index = text.count(",", 0, self.cursorPosition())   # which token is under the cursor
        tokens[index] = tag
        new = ", ".join(t for t in tokens if t) + ", "
        self.setText(new)
        self.setCursorPosition(len(new))
        self.textEdited.emit(new)           # let the inspector store the tags

    def keyPressEvent(self, event):
        """While the pop-up is open Enter/Tab/Escape belong to the completer."""
        popup = self._completer.popup()
        if popup.isVisible() and event.key() in (
                Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab, Qt.Key.Key_Escape):
            if event.key() == Qt.Key.Key_Escape:
                popup.hide()
            else:
                idx = popup.currentIndex()
                if idx.isValid():
                    self._insert_completion(idx.data())
                popup.hide()
            event.accept()
            return
        super().keyPressEvent(event)


class AttachmentList(QListWidget):
    """List of attachments; files dragged from the file manager are reported
    through :attr:`files_dropped`."""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        """Create the list and enable file drops."""
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):
        """Qt event handler: accept file drags."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Qt event handler: accept file drags."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Qt event handler: report the dropped files."""
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
