# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The board: ``BoardScene`` (all notes, pins and threads) and ``BoardView``
(zoom / pan / keyboard).

Responsibilities of the scene
-----------------------------
* owns the lookup tables ``note_lookup`` / ``pin_lookup`` / ``connection_items``
* creates, duplicates, deletes notes, pins and threads
* right-button gestures: dragging from a pin to another pin creates a thread,
  a click without movement opens a context menu (the view's own context menu
  is disabled, see ``BoardView.contextMenuEvent``)
* filtering and *focus mode*: ``reapply_filter`` is the single place that sets
  the opacity of every note and thread
* signals tell the main window about changes (``notes_changed``,
  ``note_selected``, ``interaction_finished`` ...) - the scene never touches
  other widgets directly.
"""

from PySide6.QtCore import Qt, QLineF, QPointF, Signal
from PySide6.QtGui import QColor, QPen, QPainter, QTransform
from PySide6.QtWidgets import (
    QColorDialog,
    QInputDialog,
    QFrame,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
)

from models import (
    AttachmentData,
    AttributeData,
    CommentData,
    ConnectionData,
    NoteData,
    NoteTypeData,
    PinData,
    STATUS_INFO,
    note_matches,
    note_sort_key,
)
from note_item import NoteItem
from pin_item import PinItem
from connection_item import ConnectionItem, thread_path
from theme import ACCENT, PRESET_COLORS, color_icon
from i18n import tr, N_


class BoardScene(QGraphicsScene):

    """The board scene.  See the module docstring for the overall design."""
    notes_changed = Signal()
    note_selected = Signal(object)   # NoteItem oder None
    note_created = Signal(object)
    edit_requested = Signal(object)     # Notiz im großen Editor öffnen
    interaction_finished = Signal()     # Maus losgelassen -> evtl. Änderung

    def __init__(self, parent=None):
        """Create an empty scene; ``note_types`` is filled by the main window."""
        super().__init__(parent)

        # Wird vom MainWindow gesetzt (gemeinsames dict key -> NoteTypeData)
        self.note_types = {}

        self.note_lookup = {}
        self.pin_lookup = {}
        self.connection_items = []

        self._top_z = 10
        self._current_note = None
        self._filter = ("", "", "", "")
        self.snap_to_grid = False

        # Focus mode: while a note is selected, notes/threads that are not
        # connected to it are greyed out (see reapply_filter)
        self.focus_mode = True

        # Rechtsklick-Zustand
        self._right_item = None
        self._right_press_screen = None
        self._right_moved = False
        self._drag_pin = None
        self._drag_line = None
        self._hover_pin = None

        self.selectionChanged.connect(self.on_selection_changed)

    # ------------------------------------------------------------ Auswahl

    def _emit_selected(self, note, force=False):
        """Emit ``note_selected`` when the *current* note changes (or when ``force``)."""
        if note is self._current_note and not force:
            return
        self._current_note = note
        self.note_selected.emit(note)

    def on_selection_changed(self):

        """React to a selection change: tell the main window and refresh focus mode."""
        note = None
        pin_note = None

        for item in self.selectedItems():
            if isinstance(item, NoteItem):
                note = item
                break
            if isinstance(item, PinItem) and pin_note is None:
                pin_note = item.note

        self._emit_selected(note or pin_note)
        self.reapply_filter()       # focus mode depends on the selection

    def bring_to_front(self, note):
        """Raise a note above all others (threads stay above every note)."""
        self._top_z += 1
        if self._top_z >= ConnectionItem.THREAD_Z - 10:      # never reach the threads
            self._top_z = 10
        note.setZValue(self._top_z)

    # --------------------------------------------------------- Hintergrund

    def drawBackground(self, painter, rect):

        """Qt: paint the scene/view background (the grid)."""
        painter.fillRect(rect, QColor("#15161a"))

        scale = painter.worldTransform().m11()
        grid = 40

        left = int(rect.left())
        top = int(rect.top())

        minor, major = [], []

        x = left - (left % grid)
        while x < rect.right():
            line = QLineF(x, rect.top(), x, rect.bottom())
            (major if x % (grid * 5) == 0 else minor).append(line)
            x += grid

        y = top - (top % grid)
        while y < rect.bottom():
            line = QLineF(rect.left(), y, rect.right(), y)
            (major if y % (grid * 5) == 0 else minor).append(line)
            y += grid

        if scale > 0.35:
            painter.setPen(QPen(QColor("#1c1d23"), 0))
            painter.drawLines(minor)

        painter.setPen(QPen(QColor("#25262e"), 0))
        painter.drawLines(major)

    # ------------------------------------------------------------- Helfer

    def _transform(self):
        """The first view's transform (needed for ``itemAt``)."""
        views = self.views()
        return views[0].transform() if views else QTransform()

    def _item_at(self, pos):
        """Topmost item at ``pos``; pins win over threads and notes because the
        threads are stacked above the notes and would otherwise hide the pins."""
        pin = self._pin_at(pos)
        if pin is not None:
            return pin
        return self.itemAt(pos, self._transform())

    def _pin_at(self, pos, exclude=None):
        """The first pin under ``pos`` (optionally ignoring ``exclude``)."""
        for item in self.items(pos):
            if isinstance(item, PinItem) and item is not exclude:
                return item
        return None

    # ------------------------------------------------------------- Notizen

    def create_note(self, type_key="note", center=None):

        """Create a note of ``type_key`` centred on ``center`` and select it."""
        info = self.note_types.get(type_key)

        data = NoteData(note_type=type_key)

        if info is not None:
            data.title = info.label
            data.color = info.color
            data.attributes = [
                AttributeData(name, "") for name in info.attributes
            ]

        if center is not None:
            data.x = center.x() - data.width / 2
            data.y = center.y() - data.height / 2

        note = self.add_note_item(data)

        self.clearSelection()
        note.setSelected(True)
        self.bring_to_front(note)

        self.notes_changed.emit()
        self.note_created.emit(note)

        return note

    def set_note_locked(self, note, locked):
        """Lock/unlock a note and tell the main window."""
        note.set_locked(locked)
        self._emit_selected(self._current_note, force=True)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def set_pin_locked(self, pin, locked):
        """Lock/unlock a single pin."""
        pin.set_locked(locked)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def duplicate_note(self, note):
        """Kopie einer Notiz (ohne Fäden) leicht versetzt anlegen."""

        src = note.model

        data = NoteData(
            title=src.title,
            content=src.content,
            x=src.x + 30,
            y=src.y + 30,
            width=src.width,
            height=src.height,
            color=src.color,
            note_type=src.note_type,
            status=src.status,
            tags=list(src.tags),
            attributes=[AttributeData(a.name, a.value) for a in src.attributes],
            pins=[PinData(x=p.x, y=p.y, color=p.color, locked=p.locked) for p in src.pins],
            rich=src.rich,
            attachments=[AttachmentData(a.id, a.name, a.mime, a.size, a.inline)
                         for a in src.attachments],
            comments=[CommentData(c.id, c.text, c.quote, c.created) for c in src.comments],
        )

        copy = self.add_note_item(data)

        self.clearSelection()
        copy.setSelected(True)

        self.notes_changed.emit()
        self.interaction_finished.emit()

        return copy

    def arrange_by_type(self):
        """Notizen spaltenweise nach Notizart ordnen (Kapitel nach Nummer)."""

        if not self.note_lookup:
            return

        rect = self.content_rect()
        x0, y0 = rect.left(), rect.top()

        groups = {}
        for note in self.note_lookup.values():
            groups.setdefault(note.model.note_type, []).append(note)

        order = list(self.note_types.keys()) + [
            k for k in groups if k not in self.note_types
        ]

        x = x0
        for key in order:
            notes = groups.get(key)
            if not notes:
                continue

            # locked notes stay exactly where they are
            notes = [n for n in notes if not n.model.locked]
            if not notes:
                continue

            notes.sort(key=lambda n: note_sort_key(n.model))

            y = y0
            for note in notes:
                note.setPos(x, y)
                y += note.model.height + 40

            x += max(n.model.width for n in notes) + 70

        self.notes_changed.emit()
        self.interaction_finished.emit()

    def add_note_item(self, data):
        """Notiz (neu oder geladen) in die Szene einfügen."""

        note = NoteItem(data)

        self.addItem(note)

        self.note_lookup[data.id] = note
        self.bring_to_front(note)

        for pin_data in data.pins:
            note.load_pin(pin_data)

        return note

    def remove_note(self, note):

        """Delete a note with its pins and threads and update all lookup tables."""
        if note.scene() is not self:
            return

        note.remove_all_connections()

        for pin in note.pins:
            self.pin_lookup.pop(pin.model.id, None)

        self.note_lookup.pop(note.model.id, None)

        if self._current_note is note:
            self._emit_selected(None)

        self.removeItem(note)

        self.notes_changed.emit()

    # ------------------------------------------------------------- Fäden

    def create_connection(self, start_pin, end_pin):

        """Connect two pins with a new thread (ignores duplicates in either direction)."""
        if start_pin is end_pin:
            return None

        for c in start_pin.connections:
            if (
                (c.start_pin is start_pin and c.end_pin is end_pin)
                or (c.start_pin is end_pin and c.end_pin is start_pin)
            ):
                return None

        data = ConnectionData(
            start_pin_id=start_pin.model.id,
            end_pin_id=end_pin.model.id,
        )

        connection = self.add_connection(data, start_pin, end_pin)

        self.reapply_filter()
        self.notes_changed.emit()

        return connection

    def add_connection(self, data, start_pin, end_pin):

        """Insert a thread item for existing ``ConnectionData`` (also used when loading)."""
        connection = ConnectionItem(data, start_pin, end_pin)

        start_pin.connections.append(connection)
        end_pin.connections.append(connection)

        self.connection_items.append(connection)
        self.addItem(connection)

        return connection

    def remove_connection(self, connection):

        """Remove a thread from the scene, the pins and the lookup list."""
        connection.remove_from_pins()

        if connection in self.connection_items:
            self.connection_items.remove(connection)

        if connection.scene() is self:
            self.removeItem(connection)

    def delete_selected(self):

        """Delete everything that is selected (notes, pins, threads)."""
        for item in list(self.selectedItems()):

            # Kinder werden mit ihrer Notiz entfernt
            if item.scene() is not self:
                continue

            if isinstance(item, NoteItem):
                self.remove_note(item)

            elif isinstance(item, PinItem):
                item.note.remove_pin(item)
                self.notes_changed.emit()

            elif isinstance(item, ConnectionItem):
                self.remove_connection(item)
                self.notes_changed.emit()

    def rebuild_lookup_tables(self):

        """Recompute the id -> item dictionaries from the scene contents."""
        self.note_lookup.clear()
        self.pin_lookup.clear()

        for item in self.items():
            if isinstance(item, NoteItem):
                self.note_lookup[item.model.id] = item
                for pin in item.pins:
                    self.pin_lookup[pin.model.id] = pin

    def reset(self):
        """Komplettes Board leeren."""

        self._end_connect()
        self._emit_selected(None)

        self.blockSignals(True)
        self.clear()
        self.blockSignals(False)

        self.note_lookup.clear()
        self.pin_lookup.clear()
        self.connection_items.clear()

        self._top_z = 10

        self.notes_changed.emit()

    def content_rect(self):

        """Bounding rectangle of all notes (None when empty)."""
        rect = None

        for note in self.note_lookup.values():
            r = note.sceneBoundingRect()
            rect = r if rect is None else rect.united(r)

        return rect

    # ------------------------------------------------------ Filter / Suche

    def set_filter(self, text="", type_key="", tag="", status=""):
        """Set the search / filter criteria and re-apply the dimming."""
        self._filter = (text, type_key, tag, status)
        self.reapply_filter()

    def note_matches(self, note):

        """True when a note matches the current search / filter."""
        text, type_key, tag, status = self._filter
        info = self.note_types.get(note.model.note_type)

        return note_matches(
            note.model, text, type_key, tag,
            info.label if info else "", status
        )

    def _selected_notes(self):
        """Selected notes (a selected pin counts as its note)."""
        notes = []
        for item in self.selectedItems():
            note = item if isinstance(item, NoteItem) else (
                item.note if isinstance(item, PinItem) else None)
            if note is not None and note not in notes:
                notes.append(note)
        return notes

    def _focus_set(self):
        """Notes to keep visible in focus mode: the selection plus every note
        that is connected to it by a thread.  None = focus mode inactive."""
        if not self.focus_mode:
            return None
        selected = self._selected_notes()
        if not selected:
            return None

        keep = set(selected)
        for note in selected:
            for pin in note.pins:
                for c in pin.connections:
                    keep.add(c.start_pin.note)
                    keep.add(c.end_pin.note)
        return keep, set(selected)

    def reapply_filter(self):
        """Recompute the opacity of every note and thread.

        Two independent reasons can dim an item:

        * the search/filter does not match it (strong dimming, 0.18), and
        * focus mode: it is not connected to the selected note (0.15).
        """

        active = any(self._filter)
        focus = self._focus_set()
        keep, selected = focus if focus else (None, None)

        for note in self.note_lookup.values():
            if active and not self.note_matches(note):
                note.setOpacity(0.18)
            elif keep is not None and note not in keep:
                note.setOpacity(0.15)
            else:
                note.setOpacity(1.0)

        for c in self.connection_items:
            ok = (not active) or (
                self.note_matches(c.start_pin.note)
                and self.note_matches(c.end_pin.note)
            )
            if keep is not None:
                # only threads that touch a *selected* note stay visible
                ok = ok and (c.start_pin.note in selected or c.end_pin.note in selected)
            c.setOpacity(1.0 if ok else 0.08)

    def set_focus_mode(self, on):
        """Switch focus mode (grey out unconnected notes) on or off."""
        self.focus_mode = on
        self.reapply_filter()

    # ------------------------------------------------------------- Maus

    def mouseDoubleClickEvent(self, event):

        """Qt event handler: double click."""
        if event.button() == Qt.MouseButton.RightButton:
            # schnelle zweite Rechtsklicks nicht verschlucken
            self.mousePressEvent(event)
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._item_at(event.scenePos()) is None
        ):
            self.create_note("note", event.scenePos())
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):

        """Qt event handler: a mouse button was pressed."""
        if event.button() == Qt.MouseButton.RightButton:

            item = self._item_at(event.scenePos())

            self._right_item = item
            self._right_press_screen = event.screenPos()
            self._right_moved = False

            if isinstance(item, PinItem):
                self._begin_connect(item, event.scenePos())

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):

        """Qt event handler: the mouse moved."""
        if self._right_press_screen is not None:

            delta = event.screenPos() - self._right_press_screen
            if delta.manhattanLength() > 6:
                self._right_moved = True

            if self._drag_pin is not None:
                self._update_connect(event.scenePos())

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Qt event handler: a mouse button was released."""
        self._handle_release(event)
        self.interaction_finished.emit()

    def _handle_release(self, event):

        """Right-button release: finish a thread drag or show a context menu."""
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._right_press_screen is not None
        ):
            moved = self._right_moved
            item = self._right_item
            start = self._drag_pin

            target = None
            if start is not None:
                target = self._pin_at(event.scenePos(), exclude=start)

            self._end_connect()

            self._right_item = None
            self._right_press_screen = None
            self._right_moved = False

            if start is not None and moved:
                if target is not None:
                    self.create_connection(start, target)
            elif not moved:
                self.show_context_menu(
                    item, event.screenPos(), event.scenePos()
                )

            event.accept()
            return

        super().mouseReleaseEvent(event)

    # ------------------------------------------- Rechtsklick-Faden ziehen

    def _begin_connect(self, pin, pos):

        """Start dragging a new thread from ``pin``."""
        self._drag_pin = pin

        line = QGraphicsPathItem()
        line.setPen(
            QPen(QColor(ACCENT), 2.5, Qt.PenStyle.DashLine,
                 Qt.PenCapStyle.RoundCap)
        )
        line.setZValue(10 ** 6)
        line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.addItem(line)
        self._drag_line = line

        self._update_connect(pos)

    def _update_connect(self, pos):

        """Move the dashed preview line and highlight the pin under the pointer."""
        if self._drag_line is None or self._drag_pin is None:
            return

        self._drag_line.setPath(
            thread_path(self._drag_pin.scenePos(), pos)
        )

        target = self._pin_at(pos, exclude=self._drag_pin)

        if target is not self._hover_pin:
            if self._hover_pin is not None:
                self._hover_pin.set_highlight(False)
            if target is not None:
                target.set_highlight(True)
            self._hover_pin = target

    def _end_connect(self):

        """Remove the preview line and clear highlights."""
        if self._drag_line is not None:
            if self._drag_line.scene() is self:
                self.removeItem(self._drag_line)
            self._drag_line = None

        if self._hover_pin is not None:
            self._hover_pin.set_highlight(False)
            self._hover_pin = None

        self._drag_pin = None

    # ------------------------------------------------------ Kontextmenüs

    def _pick_color(self, current, callback):

        """Ask for a colour and pass it to ``callback``."""
        views = self.views()
        color = QColorDialog.getColor(
            QColor(current),
            views[0] if views else None,
            tr("Farbe wählen")
        )

        if color.isValid():
            callback(color.name())

    def _add_color_menu(self, menu, title, current, callback):

        """Add a sub-menu with preset colours and 'Custom colour …'."""
        sub = menu.addMenu(title)

        for name, hex_color in PRESET_COLORS:
            action = sub.addAction(color_icon(hex_color), tr(name))
            action.triggered.connect(
                lambda _=False, c=hex_color: callback(c)
            )

        sub.addSeparator()

        custom = sub.addAction(tr("Eigene Farbe …"))
        custom.triggered.connect(
            lambda _=False: self._pick_color(current, callback)
        )

    def show_context_menu(self, item, screen_pos, scene_pos):

        """Context menu for a pin, thread, note or the empty board."""
        views = self.views()
        menu = QMenu(views[0] if views else None)

        if isinstance(item, PinItem):

            self._add_color_menu(
                menu, tr("Pinfarbe"), item.model.color, item.set_color
            )

            if item.connections:
                menu.addAction(tr("Fäden dieses Pins entfernen")).triggered.connect(
                    lambda _=False: (
                        item.remove_connections(),
                        self.notes_changed.emit()
                    )
                )

            if item.model.locked:
                menu.addAction(tr("Pin entsperren")).triggered.connect(
                    lambda _=False: self.set_pin_locked(item, False))
            else:
                menu.addAction(tr("Pin sperren")).triggered.connect(
                    lambda _=False: self.set_pin_locked(item, True))

            menu.addSeparator()
            menu.addAction(tr("Pin löschen")).triggered.connect(
                lambda _=False: (
                    item.note.remove_pin(item),
                    self.notes_changed.emit()
                )
            )

        elif isinstance(item, ConnectionItem):

            self._add_color_menu(
                menu, tr("Fadenfarbe"), item.model.color, item.set_color
            )

            def edit_label():
                text, ok = QInputDialog.getText(
                    views[0] if views else None, tr("Beschriftung"),
                    tr("Beziehung / Text auf dem Faden:"),
                    text=item.model.label
                )
                if ok:
                    item.set_label(text)
                    self.notes_changed.emit()

            menu.addAction(tr("Beschriftung …")).triggered.connect(
                lambda _=False: edit_label()
            )

            menu.addSeparator()
            menu.addAction(tr("Faden löschen")).triggered.connect(
                lambda _=False: (
                    self.remove_connection(item),
                    self.notes_changed.emit()
                )
            )

        elif isinstance(item, NoteItem):

            local = item.mapFromScene(scene_pos)

            menu.addAction(tr("Im großen Editor öffnen")).triggered.connect(
                lambda _=False: self.edit_requested.emit(item)
            )
            menu.addAction(tr("Duplizieren")).triggered.connect(
                lambda _=False: self.duplicate_note(item)
            )

            menu.addSeparator()

            menu.addAction(tr("Pin hier hinzufügen")).triggered.connect(
                lambda _=False: item.add_pin(local.x(), local.y())
            )

            if item.model.locked:
                menu.addAction(tr("Notiz entsperren")).triggered.connect(
                    lambda _=False: self.set_note_locked(item, False))
            else:
                menu.addAction(tr("Notiz sperren")).triggered.connect(
                    lambda _=False: self.set_note_locked(item, True))

            def set_status(key):
                item.model.status = key
                item.update()
                self._emit_selected(self._current_note, force=True)
                self.notes_changed.emit()

            status_menu = menu.addMenu(tr("Status"))
            status_menu.addAction(tr("Kein Status")).triggered.connect(
                lambda _=False: set_status("")
            )
            for key, (label, col) in STATUS_INFO.items():
                status_menu.addAction(color_icon(col), tr(label)).triggered.connect(
                    lambda _=False, k=key: set_status(k)
                )

            def set_note_color(c):
                item.model.color = c
                item.update()
                self._emit_selected(self._current_note, force=True)

            self._add_color_menu(
                menu, tr("Notizfarbe"), item.model.color, set_note_color
            )

            menu.addSeparator()
            menu.addAction(tr("Notiz löschen")).triggered.connect(
                lambda _=False: self.remove_note(item)
            )

        else:

            sub = menu.addMenu(tr("Neue Notiz hier"))

            for t in self.note_types.values():
                action = sub.addAction(color_icon(t.color), t.label)
                action.triggered.connect(
                    lambda _=False, k=t.key: self.create_note(k, scene_pos)
                )

        menu.exec(screen_pos)


class BoardView(QGraphicsView):

    """The view: zoom with the wheel, pan with the middle button, Delete key, fit-all."""
    MIN_ZOOM = 0.08
    MAX_ZOOM = 4.0

    def __init__(self, scene):
        """Configure rendering, anchors and the rubber-band selection."""
        super().__init__(scene)

        self._panning = False
        self._last_pos = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )

        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        # Kein Anker: Größenänderungen der Docks dürfen das Board nicht verschieben
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    # Rechtsklick-Menüs werden von der Szene behandelt
    def contextMenuEvent(self, event):
        """Qt event handler: context-menu request."""
        event.accept()

    def wheelEvent(self, event):

        """Qt event handler: mouse wheel."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15

        new_zoom = self.transform().m11() * factor

        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            return

        self.scale(factor, factor)

    def mousePressEvent(self, event):

        """Qt event handler: a mouse button was pressed."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):

        """Qt event handler: the mouse moved."""
        if self._panning:
            pos = event.position().toPoint()
            delta = pos - self._last_pos
            self._last_pos = pos

            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() - delta.x())
            v.setValue(v.value() - delta.y())

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):

        """Qt event handler: a mouse button was released."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):

        """Qt event handler: a key was pressed."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.scene().delete_selected()
            event.accept()
            return

        super().keyPressEvent(event)

    def fit_all(self):

        """Zoom so that every note is visible."""
        rect = self.scene().content_rect()

        if rect is None or rect.isNull():
            self.resetTransform()
            self.centerOn(0, 0)
            return

        self.fitInView(
            rect.adjusted(-80, -80, 80, 80),
            Qt.AspectRatioMode.KeepAspectRatio
        )

        if self.transform().m11() > 1.2:
            self.resetTransform()
            self.centerOn(rect.center())

    def reset_zoom(self):
        """Back to 100 % zoom."""
        self.resetTransform()
