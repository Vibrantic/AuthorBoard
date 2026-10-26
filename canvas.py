# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The board: ``BoardScene`` (all notes, pins and threads) and ``BoardView``.

Performance notes (Optimization.md)
-----------------------------------
*   ``BoardScene.drawBackground`` counts visible threads once per frame.  That
    count drives ``ConnectionItem._detail_level`` (full / medium / label /
    stroke).  This is what makes a dense cluster of 100+ threads fast even
    though the board is not "very large".
*   ``reapply_filter`` only sets opacity when the value changes and is
    deferred while a rubber-band selection is in progress.
*   Note-rect index (``_note_rects``) used by threads instead of
    ``scene.items(rect)``.
*   ``BoardView`` uses ``SmartViewportUpdate``; wheel zoom works from any
    starting state (including fit-all that would otherwise land below
    MIN_ZOOM).

Panning
-------
``BoardView`` pan is a middle-button drag.  Movement is applied by nudging
the scroll bars (``h.setValue(h.value() - dx)``) rather than by translating
the transform: scroll-bar values are in screen pixels, so the content tracks
the cursor 1:1 at any zoom.  The scene rect is huge (set by ``MainWindow``),
so this never clamps.

Ending the pan is done via an **application-level event filter** installed
only while the pan is active.  We do *not* use ``grabMouse()``: it is
unreliable across platforms (macOS needs an active window, Windows can
silently fail if another widget holds the grab), and it interferes with
``QGraphicsView``'s normal item delivery.  The filter catches the middle
button release *wherever it lands* — over a note, over a child widget, or
outside the window — and ends the pan cleanly.  A 5 s inactivity watchdog
covers the last case (a release swallowed by a system dialog).
"""

from PySide6.QtCore import (
    Qt,
    QEvent,
    QLineF,
    QPointF,
    QRectF,
    Signal,
    QTimer,
    QItemSelectionModel,
)
from PySide6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QTransform,
    QPixmap,
    QBrush,
    QPainterPath,
    QGuiApplication,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QInputDialog,
    QFrame,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
    QMessageBox,
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
    GroupData,
)
from note_item import NoteItem
from pin_item import PinItem
from connection_item import ConnectionItem, thread_path
from theme import ACCENT, PRESET_COLORS, GROUP_COLORS, color_icon
from i18n import tr, N_
from group_item import GroupItem, HEADER_H


def _make_grid_pixmap() -> QPixmap:
    """A 40 px tile with one minor grid line on its top and left edge."""
    tile = QPixmap(40, 40)
    tile.fill(QColor("#15161a"))
    p = QPainter(tile)
    p.setPen(QPen(QColor("#1c1d23"), 1))
    p.drawLine(0, 0, 40, 0)
    p.drawLine(0, 0, 0, 40)
    p.end()
    return tile


class BoardScene(QGraphicsScene):
    """The board scene.  See the module docstring for the overall design."""

    notes_changed = Signal()
    note_selected = Signal(object)   # NoteItem oder None
    note_created = Signal(object)
    edit_requested = Signal(object)
    interaction_finished = Signal()

    structure_changed = Signal()
    note_content_changed = Signal(object)

    flow_requested = Signal(object)

    def __init__(self, parent=None):
        """Create an empty scene; ``note_types`` is filled by the main window."""
        super().__init__(parent)

        self.note_types = {}
        self.note_lookup = {}
        self.pin_lookup = {}
        self.connection_items = []
        self.group_lookup = {}
        self._group_z_counter = 0

        self._top_z = 10
        self._current_note = None
        self._filter = ("", "", "", "")
        self.snap_to_grid = False
        self.focus_mode = True

        self._right_item = None
        self._right_press_screen = None
        self._right_moved = False
        self._drag_pin = None
        self._drag_line = None
        self._hover_pin = None

        self._note_rects = {}
        self._filter_deferred = False
        self._grid_pixmap = None

        # Per-frame count of visible threads (read by ConnectionItem._detail_level).
        self._visible_thread_count = 0
        self._visible_pin_count = 0
        self._view_rect = QRectF()

        self.selectionChanged.connect(self.on_selection_changed)
        self._mentions_revision = 0

        # True while BoardScene.render() is called for PNG export.  When set,
        # every graphics item paints at full fidelity and skips the
        # view-dependent LOD / viewport-culling logic that reads
        # _visible_thread_count / _view_rect / _visible_pin_count.
        self.export_mode = False

    # ------------------------------------------------------------ Auswahl

    def _emit_selected(self, note, force=False):
        """Emit ``note_selected`` when the *current* note changes (or when ``force``)."""
        if note is self._current_note and not force:
            return
        self._current_note = note
        self.note_selected.emit(note)

    def on_selection_changed(self):

        note = None
        pin_note = None
        for item in self.selectedItems():
            if isinstance(item, NoteItem):
                note = item
                break
            if isinstance(item, PinItem) and pin_note is None:
                pin_note = item.note
        self._emit_selected(note or pin_note)
        self._selected_note_ids = {
            n.model.id for n in self._selected_notes()
        }
        for c in self.connection_items:
            c.update()
        self.reapply_filter()

    def bring_to_front(self, note):
        """Raise a note above all others."""
        self._top_z += 1
        if self._top_z >= ConnectionItem.THREAD_Z - 10:
            self._top_z = 10
        note.setZValue(self._top_z)

    # --------------------------------------------------------- Hintergrund

    def drawBackground(self, painter, rect):
        """Qt: paint the scene background and count visible threads.

        Runs once per frame before any item is painted — the natural place to
        compute per-frame LOD state.  ``ConnectionItem._detail_level`` reads
        ``_visible_thread_count`` to pick a detail tier.
        """
        painter.fillRect(rect, QColor("#15161a"))

        # Minor grid (tiled pixmap)
        scale = painter.worldTransform().m11()
        if scale > 0.35:
            if self._grid_pixmap is None:
                self._grid_pixmap = _make_grid_pixmap()
            painter.setBrush(QBrush(self._grid_pixmap))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

        # Major grid lines
        grid = 40 * 5
        left = int(rect.left())
        top = int(rect.top())
        major = []

        x = left - (left % grid)
        while x < rect.right():
            major.append(QLineF(x, rect.top(), x, rect.bottom()))
            x += grid

        y = top - (top % grid)
        while y < rect.bottom():
            major.append(QLineF(rect.left(), y, rect.right(), y))
            y += grid

        painter.setPen(QPen(QColor("#25262e"), 0))
        painter.drawLines(major)

    # ------------------------------------------------------------- Helfer

    def _transform(self):
        """The first view's transform (needed for ``itemAt``)."""
        views = self.views()
        return views[0].transform() if views else QTransform()

    def _item_at(self, pos):
        """Topmost item at ``pos``; pins win over threads and notes."""
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

    # -------------------------------------------------- Note-rect index

    def invalidate_note_rect(self, note):
        """Update the rect index for a note (called on move / resize)."""
        if note.scene() is not self:
            self._note_rects.pop(note.model.id, None)
            return
        self._note_rects[note.model.id] = note.mapRectToScene(note.rect())

    def note_rects_overlapping(self, scene_rect, limit=None):
        """Scene rects of all notes intersecting ``scene_rect``.

        ``limit`` stops the scan as soon as that many matches are found —
        used by ``ConnectionItem`` to avoid a large union for a thread that
        crosses dozens of notes.
        """
        out = []
        for r in self._note_rects.values():
            if r.intersects(scene_rect):
                out.append(r)
                if limit is not None and len(out) >= limit:
                    break
        return out

    def _rebuild_note_rect_index(self):
        """Rebuild the whole rect index."""
        self._note_rects.clear()
        for note in self.note_lookup.values():
            self._note_rects[note.model.id] = note.mapRectToScene(note.rect())

    # ------------------------------------------------------------- Notizen

    def create_note(self, type_key="note", center=None):
        """Create a note of ``type_key`` centred on ``center`` and select it."""
        info = self.note_types.get(type_key)
        data = NoteData(note_type=type_key)
        if info is not None:
            data.title = info.label
            data.color = info.color
            data.attributes = [AttributeData(name, "") for name in info.attributes]
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
        """Kopie einer Notiz (ohne Fäden) leicht versetzt anlegen.

        Threads are duplicated by :meth:`duplicate_connections`, which the
        caller (``MainWindow.duplicate_selected``) invokes after copying
        all selected notes, so a thread is only duplicated when both of its
        endpoints were duplicated.
        """
        src = note.model
        data = NoteData(
            title=src.title, content=src.content,
            x=src.x + 30, y=src.y + 30,
            width=src.width, height=src.height,
            color=src.color, note_type=src.note_type, status=src.status,
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
        rect = self.content_rect(include_groups=False)
        x0, y0 = rect.left(), rect.top()
        groups = {}
        for note in self.note_lookup.values():
            groups.setdefault(note.model.note_type, []).append(note)
        order = list(self.note_types.keys()) + [k for k in groups if k not in self.note_types]
        x = x0
        for key in order:
            notes = groups.get(key)
            if not notes:
                continue
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
        self._note_rects[data.id] = note.mapRectToScene(note.rect())
        self.bring_to_front(note)
        for pin_data in data.pins:
            note.load_pin(pin_data)
        return note

    def remove_note(self, note):
        """Delete a note with its pins and threads."""
        if note.scene() is not self:
            return
        note.remove_all_connections()
        for pin in note.pins:
            self.pin_lookup.pop(pin.model.id, None)
        self.note_lookup.pop(note.model.id, None)
        self._note_rects.pop(note.model.id, None)
        if self._current_note is note:
            self._emit_selected(None)
        self.removeItem(note)
        self.notes_changed.emit()
        self.structure_changed.emit()

    # ------------------------------------------------------------ Gruppen

    GROUP_Z_BASE = -10000

    def add_group_item(self, data):
        """Insert a group frame (new or loaded).  Later groups lie on top."""
        group = GroupItem(data)
        self.addItem(group)
        self.group_lookup[data.id] = group
        self._group_z_counter += 1
        group.setZValue(self.GROUP_Z_BASE + self._group_z_counter)
        if self._group_z_counter > 9000:
            self._renormalize_group_z()
        return group

    def _renormalize_group_z(self):
        """Compact the z-values, keeping the stacking order."""
        ordered = sorted(self.group_lookup.values(), key=lambda g: g.zValue())
        for i, g in enumerate(ordered, 1):
            g.setZValue(self.GROUP_Z_BASE + i)
        self._group_z_counter = len(ordered)

    def clear_groups(self):
        """Remove all frames silently (used by undo / redo)."""
        for g in list(self.group_lookup.values()):
            if g.scene() is self:
                self.removeItem(g)
        self.group_lookup.clear()
        self._group_z_counter = 0

    def remove_group(self, group):
        """Remove a frame; the notes stay."""
        if group.scene() is self:
            self.removeItem(group)
        self.group_lookup.pop(group.model.id, None)
        self.notes_changed.emit()

    def _next_group_color(self):
        return GROUP_COLORS[len(self.group_lookup) % len(GROUP_COLORS)]

    def create_group_from_selection(self):
        """Frame the selection with a new group; None if nothing usable is selected.

        Handles three cases:

        * Only notes selected → old behaviour: the new frame wraps the notes,
          and the notes become its members (topmost frame containing their
          centre).
        * Only groups selected → the new frame wraps the selected groups and
          moves them forward so it lands *behind* them (geometric nesting rule
          requires the child to be in front of the parent).
        * Notes **and** groups selected → union of both: notes join the new
          frame directly, groups become its nested children.

        The new group is selected afterwards, so the user can rename, move or
        lock it immediately.
        """
        notes = self.selected_notes()
        groups = self.selected_groups()

        if not notes and not groups:
            return None

        # Union of the selected items' visible geometry.
        rect = None
        for n in notes:
            r = n.mapRectToScene(n.rect())
            rect = r if rect is None else rect.united(r)
        for g in groups:
            r = g.scene_rect()  # includes header, not the drop shadow
            rect = r if rect is None else rect.united(r)

        pad = 30
        data = GroupData(
            title=tr("Gruppe"),
            color=self._next_group_color(),
            x=rect.left() - pad,
            y=rect.top() - pad - HEADER_H,
            width=rect.width() + 2 * pad,
            height=rect.height() + 2 * pad + HEADER_H,
        )
        new_group = self.add_group_item(data)

        # Make sure the new frame wins the "topmost frame containing the
        # centre" rule for the selected notes: bring it to the very top, then
        # bring every selected group back in front of it (in their original
        # relative order) so their nesting is preserved.
        self.raise_group(new_group)

        if groups:
            for g in sorted(groups, key=lambda x: x.zValue()):
                self.raise_group(g)

        self.clearSelection()
        new_group.setSelected(True)

        self.notes_changed.emit()
        self.interaction_finished.emit()
        return new_group

    def create_empty_group(self, pos):
        """Create an empty frame whose top-left corner is ``pos``."""
        data = GroupData(title=tr("Gruppe"), color=self._next_group_color(),
                         x=pos.x(), y=pos.y())
        group = self.add_group_item(data)
        self.notes_changed.emit()
        return group

    def rename_group(self, group):
        """Ask for a new title."""
        views = self.views()
        text, ok = QInputDialog.getText(
            views[0] if views else None, tr("Gruppe umbenennen"),
            tr("Titel der Gruppe:"), text=group.model.title)
        if ok:
            group.set_title(text.strip())
            self.notes_changed.emit()

    def set_group_locked(self, group, locked):
        """Lock / unlock a frame.

        Locking cascades to every note and nested group inside the frame,
        because a locked group would otherwise still allow its contents to be
        dragged out of it.  Unlocking does *not* cascade — otherwise a user
        couldn't unlock one child while keeping the parent locked, which is
        exactly the scenario the cascade is supposed to allow.
        """
        group.set_locked(locked)
        if locked:
            self._cascade_lock_on(group)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def _descendants_of_group(self, group):
        """All notes and nested groups that are *inside* ``group`` at any depth.

        Returns ``(notes, groups)`` — both lists exclude ``group`` itself.

        Uses ``group_members`` so nesting semantics (child in front of parent,
        contained rect) match everywhere else in the code.
        """
        if group.scene() is not self:
            return [], []
        frames, notes = self.group_members(group)
        # group_members includes ``group`` itself in frames; strip it.
        frames = [f for f in frames if f is not group]
        return notes, frames

    def _cascade_lock_on(self, root_item):
        """Called when a group is *locked*: also lock every descendant.

        The child lock flags are ordinary ``model.locked`` flags, so they can
        be toggled independently afterwards (unlock one child, re-lock it, …).
        Nothing inherits the parent's lock; this is a one-time cascade.
        """
        if not isinstance(root_item, GroupItem):
            return
        notes, groups = self._descendants_of_group(root_item)
        for g in groups:
            g.set_locked(True)
        for n in notes:
            n.set_locked(True)

    def raise_group(self, group):
        """Put a frame above all other frames (it then wins overlaps).

        Raising a group above a bigger group **detaches** it: a group is only
        nested in another when it is in front of that other group, so bringing
        it forward makes it a top-level group again.  Conversely, sending it
        behind re-nests it if it lies inside a bigger group's rect.
        """
        if group.scene() is not self:
            return

        self._renormalize_group_z()
        ordered = sorted(self.group_lookup.values(), key=lambda g: g.zValue())
        if group in ordered:
            ordered.remove(group)
        ordered.append(group)

        for i, g in enumerate(ordered, 1):
            g.setZValue(self.GROUP_Z_BASE + i)
        self._group_z_counter = len(ordered)

        for g in self.group_lookup.values():
            g.update()

        self.notes_changed.emit()

    def send_group_to_back(self, group):
        """Put a frame below all other frames.

        Like raising, this changes nesting: a group that was inside another
        frame is *detached* (it is now behind its former parent, so it no
        longer counts as nested).
        """
        if group.scene() is not self:
            return

        self._renormalize_group_z()
        ordered = sorted(self.group_lookup.values(), key=lambda g: g.zValue())
        if group in ordered:
            ordered.remove(group)
        ordered.insert(0, group)

        for i, g in enumerate(ordered, 1):
            g.setZValue(self.GROUP_Z_BASE + i)
        self._group_z_counter = len(ordered)

        for g in self.group_lookup.values():
            g.update()

        self.notes_changed.emit()

    def raise_group_one_step(self, group):
        """Move a frame one step forward in the stacking order (swap with the
        group immediately above it).  No-op if already at the top."""
        if group.scene() is not self:
            return

        self._renormalize_group_z()
        ordered = sorted(self.group_lookup.values(), key=lambda g: g.zValue())
        try:
            idx = ordered.index(group)
        except ValueError:
            return
        if idx >= len(ordered) - 1:
            return

        ordered[idx], ordered[idx + 1] = ordered[idx + 1], ordered[idx]
        for i, g in enumerate(ordered, 1):
            g.setZValue(self.GROUP_Z_BASE + i)
        self._group_z_counter = len(ordered)

        for g in self.group_lookup.values():
            g.update()
        self.notes_changed.emit()

    def send_group_back_one_step(self, group):
        """Move a frame one step backward in the stacking order (swap with the
        group immediately below it).  No-op if already at the bottom."""
        if group.scene() is not self:
            return

        self._renormalize_group_z()
        ordered = sorted(self.group_lookup.values(), key=lambda g: g.zValue())
        try:
            idx = ordered.index(group)
        except ValueError:
            return
        if idx <= 0:
            return

        ordered[idx], ordered[idx - 1] = ordered[idx - 1], ordered[idx]
        for i, g in enumerate(ordered, 1):
            g.setZValue(self.GROUP_Z_BASE + i)
        self._group_z_counter = len(ordered)

        for g in self.group_lookup.values():
            g.update()
        self.notes_changed.emit()

    # --- geometric membership: the topmost frame containing the centre wins

    def _groups_by_z(self):
        """All frames, topmost first."""
        return sorted(self.group_lookup.values(),
                      key=lambda g: g.zValue(), reverse=True)

    def _group_index_path(self, group):
        """Return the nesting path of ``group`` as a tuple of 1-based indices.

        Example: a group that is the 2nd child of the 1st top-level group
        returns ``(1, 2)``. A top-level group returns ``()`` (no badge).

        A group is a *child* of another group only when:
          * it is completely inside the other group's rect, AND
          * the other group is **behind** it (lower z-value).

        A group that is in front of a bigger group is **not** its child —
        it is its own top-level group.  This matches :meth:`group_members`.
        """
        if group.scene() is not self:
            return ()

        ordered = self._groups_by_z()  # topmost first

        # Determine each group's parent (same rule as ``group_members``).
        parent_of = {}
        for g in ordered:
            gr = g.scene_rect()
            parent = None
            for h in ordered:
                if h is g:
                    continue
                if (h.scene_rect().contains(gr)
                        and h.zValue() < g.zValue()):  # parent must be BEHIND
                    parent = h
                    break
            parent_of[g] = parent

        path = []
        current = group
        seen = set()
        while True:
            if id(current) in seen:
                return tuple(path)
            seen.add(id(current))

            parent = parent_of.get(current)
            if parent is None:
                return tuple(reversed(path)) if path else ()

            siblings = [g for g in ordered if parent_of.get(g) is parent]
            siblings.sort(key=lambda g: (
                g.scene_rect().top(),
                g.scene_rect().left(),
                (g.model.title or "").lower(),
            ))
            try:
                index = siblings.index(current) + 1
            except ValueError:
                return tuple(reversed(path))

            path.append(index)
            current = parent

    def note_group(self, note, ordered=None):
        """The frame a note belongs to (None = no frame)."""
        if ordered is None:
            ordered = self._groups_by_z()
        c = note.mapToScene(note.rect().center())
        for g in ordered:
            if g.scene_rect().contains(c):
                return g
        return None

    def group_members(self, group):
        """``(frames, notes)`` that move with ``group``, locked ones included.

        Notes: those whose winning frame is ``group`` or one of its nested
        frames.

        A frame is nested in a parent when:
          * it lies completely inside the parent's rect, AND
          * it is **in front of** the parent (higher z-value).
        A frame behind a bigger frame is *not* nested in it — it is its own
        top-level frame.  This is what makes "bring group to front"
        detach a previously nested group instead of leaving it attached.
        """
        ordered = self._groups_by_z()  # topmost first
        moved = {group}
        changed = True
        while changed:
            changed = False
            for h in ordered:
                if h in moved:
                    continue
                hr = h.scene_rect()
                parent = next(
                    (g for g in ordered
                     if g is not h
                     and g.scene_rect().contains(hr)
                     and g.zValue() < h.zValue()),  # parent must be BEHIND child
                    None,
                )
                if parent is not None and parent in moved:
                    moved.add(h)
                    changed = True
        notes = [n for n in self.note_lookup.values()
                 if self.note_group(n, ordered) in moved]
        return moved, notes

    def group_chain_for_note(self, note):
        """The chain of groups a note belongs to, outermost first.

        Returns ``[]`` if the note is not in any group.  Uses the same rule as
        :meth:`group_members` and :meth:`_group_index_path`: a note belongs to
        the topmost group whose rect contains its centre, and that group may
        itself be nested in a bigger group (only if the bigger one is
        *behind* it).

        Walking up gives the full chain, e.g.::

            [big_frame, inner_frame]    # note is inside inner_frame, which
                                        # is inside big_frame
        """
        if note.scene() is not self:
            return []

        ordered = self._groups_by_z()  # topmost first

        # 1. Winner: the topmost group containing the note's centre.
        centre = note.mapToScene(note.rect().center())
        winner = None
        for g in ordered:
            if g.scene_rect().contains(centre):
                winner = g
                break
        if winner is None:
            return []

        # 2. Walk up to the outermost parent.
        chain = [winner]
        current = winner
        seen = {id(current)}
        while True:
            parent = None
            for g in ordered:
                if g is current:
                    continue
                if id(g) in seen:
                    continue
                if (g.scene_rect().contains(current.scene_rect())
                        and g.zValue() < current.zValue()):
                    parent = g
                    break
            if parent is None:
                break
            chain.append(parent)
            seen.add(id(parent))
            current = parent

        chain.reverse()  # outermost first
        return chain

    def group_block(self, group):
        """``[(item, start_pos)]`` of everything a group drag moves.

        Every note and sub-group inside ``group`` moves with it, *regardless*
        of whether that note/sub-group is individually locked.  Locking only
        prevents a user from dragging the item on its own; it does not sever
        it from its containing frame — exactly like a locked pin still follows
        its note.

        A locked *group itself* cannot be dragged directly (its
        ``mousePressEvent`` refuses to start a move), so this method only
        ever runs for an unlocked group.  But that group's locked children
        must still ride along.
        """
        frames, notes = self.group_members(group)
        return [(it, QPointF(it.pos())) for it in list(frames) + notes]

    def build_selection_block(self):
        """Everything a multi-item drag should move.

        Rules:

        *   A **note** moves if:
              * it is unlocked and selected (free-standing), OR
              * it is inside a selected group (locked or not — the group drags it).
        *   A **group** moves if:
              * it is unlocked and selected (free-standing), OR
              * it is nested inside a selected group (locked or not — the
                ancestor drags it).

        A locked free-standing item in the selection does **not** move on its
        own.  That mirrors the single-item drag behaviour (a locked note can't
        be dragged directly; a locked pin can't be dragged directly).

        Returns ``[(item, start_pos)]``.  Empty if nothing movable is selected.
        """
        selected = list(self.selectedItems())
        selected_notes = {it for it in selected if isinstance(it, NoteItem)}
        selected_groups = {it for it in selected if isinstance(it, GroupItem)}

        if not selected_notes and not selected_groups:
            return []

        # Notes and sub-groups covered by a *selected group's* block.  These
        # move via that group; we must not add them again with their own pos.
        covered_notes = set()
        for g in selected_groups:
            _, notes = self.group_members(g)
            covered_notes.update(notes)

        # Free-standing notes: selected and *not* covered by a selected group.
        # Locked free-standing notes are excluded — they must not move on their
        # own.  Their inclusion in ``covered_notes`` (if they happen to live
        # inside a selected group) already covers the "moves with the group" case.
        free_notes = {
            n for n in selected_notes
            if n not in covered_notes and not n.model.locked
        }

        # Free-standing groups: selected, unlocked, and not nested inside a
        # selected group.  Locked groups that are *inside* a selected ancestor
        # move via the ancestor's block; locked groups at the top level stay put.
        # We compute the ancestor relation using the same rule the rest of the
        # code uses (`group_chain_for_group`), so nesting semantics match.
        free_groups = []
        for g in selected_groups:
            if g.model.locked:
                continue
            # Skip groups already covered by another selected group.
            chain = self.group_chain_for_group(g)  # outermost first
            covered_by_selection = any(
                anc is not g and anc in selected_groups for anc in chain
            )
            if covered_by_selection:
                continue
            free_groups.append(g)

        # Build the block: group blocks first (they include locked children),
        # then free-standing unlocked notes, then free-standing unlocked groups.
        block = []
        seen_ids = set()

        def add(item):
            if id(item) in seen_ids:
                return
            seen_ids.add(id(item))
            block.append((item, QPointF(item.pos())))

        for g in selected_groups:
            for it, _start in self.group_block(g):
                add(it)

        for n in free_notes:
            add(n)

        for g in free_groups:
            add(g)

        return block

    def move_block(self, block, delta):
        """Move all items of ``block`` by ``delta`` (grid snapping applies to the delta)."""
        dx, dy = delta.x(), delta.y()
        snap = self.snap_to_grid
        if snap:
            dx, dy = round(dx / 20) * 20, round(dy / 20) * 20
        self.snap_to_grid = False          # keep relative offsets exact
        try:
            for item, start in block:
                item.setPos(start.x() + dx, start.y() + dy)
        finally:
            self.snap_to_grid = snap

    def delete_group_with_notes(self, group):
        """Delete the frame and every note it contains (after confirmation)."""
        frames, notes = self.group_members(group)
        views = self.views()
        answer = QMessageBox.question(
            views[0] if views else None, tr("Gruppe löschen"),
            tr("„{title}“ und {n} Notizen wirklich löschen?",
               title=group.model.title or tr("Gruppe"), n=len(notes)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        for n in notes:
            self.remove_note(n)
        for g in list(frames):
            self.remove_group(g)

    def ungrouped_order_list(self):
        """Return the live manual-ordering list for ungrouped notes.

        Stored on the scene so the tree stays in sync without a separate
        round-trip through ProjectData on every drag; ProjectData copies it
        in/out on save/load.
        """
        if not hasattr(self, "_ungrouped_order"):
            self._ungrouped_order = []
        return self._ungrouped_order

    def group_chain_for_group(self, group):
        """The chain of groups that contains ``group`` (outermost first, incl. self).

        Same rule as :meth:`group_chain_for_note`: each ancestor is a group
        whose rect contains this one *and* is behind it in z-order.
        """
        if group.scene() is not self:
            return []
        ordered = self._groups_by_z()
        chain = [group]
        current = group
        seen = {id(current)}
        while True:
            parent = None
            for g in ordered:
                if g is current or id(g) in seen:
                    continue
                if (g.scene_rect().contains(current.scene_rect())
                        and g.zValue() < current.zValue()):
                    parent = g
                    break
            if parent is None:
                break
            chain.append(parent)
            seen.add(id(parent))
            current = parent
        chain.reverse()
        return chain

    # ------------------------------------------------------------- Fäden

    def create_connection(self, start_pin, end_pin):
        """Connect two pins with a new thread (ignores duplicates)."""
        if start_pin is end_pin:
            return None
        for c in start_pin.connections:
            if ((c.start_pin is start_pin and c.end_pin is end_pin)
                    or (c.start_pin is end_pin and c.end_pin is start_pin)):
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
        """Insert a thread item for existing ``ConnectionData``."""
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
        self.structure_changed.emit()

    def delete_selected(self):
        """Delete everything that is selected (notes, pins, threads)."""
        for item in list(self.selectedItems()):
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
            elif isinstance(item, GroupItem):
                self.remove_group(item)

    def rebuild_lookup_tables(self):
        """Recompute the id -> item dictionaries from the scene contents."""
        self.note_lookup.clear()
        self.pin_lookup.clear()
        for item in self.items():
            if isinstance(item, NoteItem):
                self.note_lookup[item.model.id] = item
                for pin in item.pins:
                    self.pin_lookup[pin.model.id] = pin
        self._rebuild_note_rect_index()

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
        self.group_lookup.clear()
        self._group_z_counter = 0
        self._note_rects.clear()
        self._visible_thread_count = 0
        self._visible_pin_count = 0
        self._selected_note_ids = set()
        self._filter_deferred = False
        self._top_z = 10
        self.notes_changed.emit()
        self._mentions_revision += 1

        if hasattr(self, "_ungrouped_order"):
            self._ungrouped_order.clear()

        if hasattr(self, "_top_level_order"):
            self._top_level_order.clear()

    def content_rect(self, include_groups=True):
        """Bounding rectangle of all notes (and group frames); None when empty."""
        rect = None
        for note in self.note_lookup.values():
            r = note.sceneBoundingRect()
            rect = r if rect is None else rect.united(r)
        if include_groups:
            for g in self.group_lookup.values():
                r = g.sceneBoundingRect()
                rect = r if rect is None else rect.united(r)
        return rect

    # ------------------------------------------------------ Filter / Suche

    def set_filter(self, text="", type_key="", tag="", status=""):
        """Set the search / filter criteria and re-apply the dimming."""
        self._filter = (text, type_key, tag, status)
        self.reapply_filter()

    def note_matches(self, note: NoteData, text: str = "", type_key: str = "",
                     tag: str = "", type_label: str = "",
                     status: str = "") -> bool:
        """True when a note matches the current search / filter."""
        text, type_key, tag, status = self._filter
        info = self.note_types.get(note.model.note_type)
        label = info.label if info else ""
        return note_matches(
            note.model, text, type_key, tag, label, status,
            haystack=note.search_haystack(),  # ← no type_label
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

    def selected_notes(self):
        """All selected NoteItems."""
        return [i for i in self.selectedItems() if isinstance(i, NoteItem)]

    def selected_pins(self):
        """All selected PinItems."""
        return [i for i in self.selectedItems() if isinstance(i, PinItem)]

    def selected_groups(self):
        """All selected GroupItems."""
        return [i for i in self.selectedItems() if isinstance(i, GroupItem)]

    def selected_connections(self):
        """All selected ConnectionItems."""
        return [i for i in self.selectedItems() if isinstance(i, ConnectionItem)]

    def set_lock_for_selection(self, locked):
        """Lock or unlock every lockable item in the current selection.

        Applies to notes, pins and groups.  Threads are not lockable.
        Locking a group also locks its descendant notes and nested groups
        (one-time cascade — the children can be unlocked individually
        afterwards).  Emits one notes_changed / interaction_finished pair so
        undo sees the whole gesture as a single checkpoint.
        """
        notes = self.selected_notes()
        pins = self.selected_pins()
        groups = self.selected_groups()

        for n in notes:
            n.set_locked(locked)
        for p in pins:
            p.set_locked(locked)
        for g in groups:
            g.set_locked(locked)
            if locked:
                self._cascade_lock_on(g)

        self._emit_selected(self._current_note, force=True)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def direct_neighbours(self, note):
        """Return ``[(pin_index, other_note, connection_item), …]``.

        The list is ordered by:
        1. the pin index on ``note`` (i.e. the visual order of pins on the
           note itself),
        2. the order of connections on that pin.

        Duplicates (two threads between the same pair of pins) are kept —
        they represent distinct connections and the FlowView shows them
        as distinct edges.
        """
        if note is None or note.scene() is not self:
            return []
        out = []
        for pin_index, pin in enumerate(note.pins):
            for c in pin.connections:
                other = c.end_pin if c.start_pin is pin else c.start_pin
                out.append((pin_index, other.note, c))
        return out

    def _focus_set(self):
        """Notes to keep visible in focus mode.  None = focus mode inactive."""
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

    def select_connected(self, note, recursive=False):
        """Select a note and the notes connected to it by threads.

        With ``recursive=False`` (default), only direct neighbours are
        selected.  With ``recursive=True``, the walk continues through every
        neighbour until no new note is reachable — the whole connected
        component.

        The selection is applied in a single batch so the per-selection
        handler doesn't run between iterations and leave the scene
        half-selected.
        """
        if note is None or note.scene() is not self:
            return

        if recursive:
            # Build an adjacency map once so the walk is O(N + E) instead of
            # O(N × E).
            adjacency = {}
            for c in self.connection_items:
                a = c.start_pin.note
                b = c.end_pin.note
                adjacency.setdefault(a, []).append(b)
                adjacency.setdefault(b, []).append(a)

            selected = {note}
            frontier = [note]
            while frontier:
                current = frontier.pop()
                for other in adjacency.get(current, ()):
                    if other not in selected and other.scene() is self:
                        selected.add(other)
                        frontier.append(other)
        else:
            selected = {note}
            for c in self.connection_items:
                if c.start_pin.note is note:
                    other = c.end_pin.note
                elif c.end_pin.note is note:
                    other = c.start_pin.note
                else:
                    continue
                if other.scene() is self:
                    selected.add(other)

        self.blockSignals(True)
        try:
            self.clearSelection()
            for n in selected:
                n.setSelected(True)
        finally:
            self.blockSignals(False)

        self.on_selection_changed()
        self.notes_changed.emit()

    def select_connected_recursive(self, note):
        """Select a note and every note reachable from it by any number of threads."""
        if note is None or note.scene() is not self:
            return
        self.clearSelection()
        note.setSelected(True)
        seen = {note}
        stack = [note]
        while stack:
            current = stack.pop()
            for other, _label in current.links():
                if other in seen or other.scene() is not self:
                    continue
                seen.add(other)
                other.setSelected(True)
                stack.append(other)

    def duplicate_connections(self, old_to_new):
        """Recreate threads whose both endpoints are on duplicated notes.

        ``old_to_new`` maps ``old_note_id -> new_NoteItem``.  A thread is
        recreated if and only if *both* of its endpoint notes are in this
        map.  Threads that connect a duplicated note to a note that was
        not duplicated are left alone — the original note keeps its
        connection, the copy has no thread.
        """
        # Map old pin ids to the corresponding new pins.  Pins are copied
        # 1:1 in order, so index-by-index matching is exact.
        old_pin_to_new = {}
        for old_id, copy in old_to_new.items():
            old_note = self.note_lookup.get(old_id)
            if old_note is None or copy is None:
                continue
            if len(old_note.pins) != len(copy.pins):
                continue
            for old_pin, new_pin in zip(old_note.pins, copy.pins):
                old_pin_to_new[old_pin.model.id] = new_pin

        # Snapshot the connection list — add_connection appends to it and we
        # don't want to visit the newly created ones.
        for connection in list(self.connection_items):
            start_old = connection.start_pin.model.id
            end_old = connection.end_pin.model.id
            new_start = old_pin_to_new.get(start_old)
            new_end = old_pin_to_new.get(end_old)
            if new_start is None or new_end is None:
                continue                       # at least one endpoint not duplicated
            if new_start is new_end:
                continue                       # no self-loops from this pass
            data = ConnectionData(
                start_pin_id=new_start.model.id,
                end_pin_id=new_end.model.id,
                color=connection.model.color,
                label=connection.model.label,
            )
            self.add_connection(data, new_start, new_end)

        self.reapply_filter()
        self.notes_changed.emit()

    def reapply_filter(self):
        """Recompute opacity of every note and thread.

        Also forces an explicit update() on each item whose opacity changed —
        DeviceCoordinateCache doesn't reliably invalidate cached pixmaps when
        setOpacity changes, so without this the item stays visually dimmed
        until a pan or resize forces a full repaint.
        """
        active = any(self._filter)
        focus = self._focus_set()
        keep, selected = focus if focus else (None, None)

        for note in self.note_lookup.values():
            if active and not self.note_matches(note):
                op = 0.18
            elif keep is not None and note not in keep:
                op = 0.15
            else:
                op = 1.0
            if note.opacity() != op:
                note.setOpacity(op)
                note.update()

        for c in self.connection_items:
            ok = (not active) or (
                    self.note_matches(c.start_pin.note)
                    and self.note_matches(c.end_pin.note)
            )
            if keep is not None:
                ok = ok and (c.start_pin.note in selected or c.end_pin.note in selected)
            op = 1.0 if ok else 0.08
            if c.opacity() != op:
                c.setOpacity(op)
                c.update()

        if self.group_lookup:
            ordered = self._groups_by_z()
            members = {}
            if active or keep is not None:
                for note in self.note_lookup.values():
                    g = self.note_group(note, ordered)
                    if g is not None:
                        members.setdefault(g, []).append(note)
            for g in ordered:
                op = 1.0
                ms = members.get(g)
                if ms:
                    if active and not any(self.note_matches(n) for n in ms):
                        op = 0.18
                    elif keep is not None and not any(n in keep for n in ms):
                        op = 0.15
                if g.opacity() != op:
                    g.setOpacity(op)
                    g.update()

    def set_focus_mode(self, on):
        """Switch focus mode on or off."""
        self.focus_mode = on
        self.reapply_filter()

    # ------------------------------------------------------------- Maus

    def mouseDoubleClickEvent(self, event):
        """Qt event handler: double click."""
        if event.button() == Qt.MouseButton.RightButton:
            self.mousePressEvent(event)
            return
        if (event.button() == Qt.MouseButton.LeftButton
                and self._item_at(event.scenePos()) is None):
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
        if self._item_at(event.scenePos()) is None:
            self._filter_deferred = True
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
        super().mouseReleaseEvent(event)
        self._handle_release(event)
        self.interaction_finished.emit()

    def _handle_release(self, event):
        """Right-button release: finish a thread drag or show a context menu."""
        if (event.button() == Qt.MouseButton.RightButton
                and self._right_press_screen is not None):
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
                self.show_context_menu(item, event.screenPos(), event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------- Rechtsklick-Faden ziehen

    def _begin_connect(self, pin, pos):
        """Start dragging a new thread from ``pin``."""
        self._drag_pin = pin
        line = QGraphicsPathItem()
        line.setPen(QPen(QColor(ACCENT), 2.5, Qt.PenStyle.DashLine,
                         Qt.PenCapStyle.RoundCap))
        line.setZValue(10 ** 6)
        line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(line)
        self._drag_line = line
        self._update_connect(pos)

    def _update_connect(self, pos):
        """Move the dashed preview line and highlight the pin under the pointer."""
        if self._drag_line is None or self._drag_pin is None:
            return
        self._drag_line.setPath(thread_path(self._drag_pin.scenePos(), pos))
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
            QColor(current), views[0] if views else None, tr("Farbe wählen"))
        if color.isValid():
            callback(color.name())

    def _add_color_menu(self, menu, title, current, callback):
        """Add a sub-menu with preset colours and 'Custom colour …'."""
        sub = menu.addMenu(title)
        for name, hex_color in PRESET_COLORS:
            action = sub.addAction(color_icon(hex_color), tr(name))
            action.triggered.connect(lambda _=False, c=hex_color: callback(c))
        sub.addSeparator()
        custom = sub.addAction(tr("Eigene Farbe …"))
        custom.triggered.connect(lambda _=False: self._pick_color(current, callback))

    def show_context_menu(self, item, screen_pos, scene_pos):
        """Context menu for a pin, thread, note, group or the empty board.

        Multi-selection aware: if the right-clicked item is part of a larger
        selection of same-kind items, the menu reflects that and applies the
        action to every item of that kind in the selection.  Right-clicking an
        unselected item replaces the selection with it first (standard desktop
        convention).
        """
        views = self.views()
        menu = QMenu(views[0] if views else None)

        # Preserve the current multi-selection if the clicked item is part of it.
        if item is not None and not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
        elif item is None:
            # Right-click on empty board: keep selection (so the user can still
            # act on it via the menu below), but the empty-board branch does not
            # need any selection-preservation logic.
            pass

        lockable = (
                self.selected_notes()
                + self.selected_pins()
                + self.selected_groups()
        )
        kinds = {type(x) for x in lockable}
        mixed_lock = len(kinds) > 1

        if mixed_lock and item is not None:
            any_unlocked = any(not x.model.locked for x in lockable)
            lock_label = tr("Auswahl entsperren") if not any_unlocked else tr("Auswahl sperren")
            lock_action = menu.addAction(lock_label)
            lock_action.setShortcut(QKeySequence("Ctrl+L"))
            lock_action.triggered.connect(
                lambda _=False, v=any_unlocked: self.set_lock_for_selection(v))
            menu.addSeparator()

        # ---- PIN ----
        if isinstance(item, PinItem):
            pins = self.selected_pins()
            plural = len(pins) > 1
            self._add_color_menu(
                menu,
                tr("Pinfarben") if plural else tr("Pinfarbe"),
                item.model.color,
                lambda c: self._apply_color_to_pins(pins, c),
            )
            if plural:
                menu.addAction(tr("Fäden dieser Pins entfernen")).triggered.connect(
                    lambda _=False: self._remove_connections_of_pins(pins))
            elif item.connections:
                menu.addAction(tr("Fäden dieses Pins entfernen")).triggered.connect(
                    lambda _=False: (item.remove_connections(), self.notes_changed.emit()))
            menu.addSeparator()
            if not mixed_lock:
                if plural:
                    if all(p.model.locked for p in pins):
                        label = tr("Pins entsperren")
                        target = False
                    else:
                        label = tr("Pins sperren")
                        target = True
                    menu.addAction(label).triggered.connect(
                        lambda _=False, v=target: self._apply_lock_to_pins(pins, v))
                else:
                    if item.model.locked:
                        menu.addAction(tr("Pin entsperren")).triggered.connect(
                            lambda _=False: self.set_pin_locked(item, False))
                    else:
                        menu.addAction(tr("Pin sperren")).triggered.connect(
                            lambda _=False: self.set_pin_locked(item, True))
            menu.addSeparator()
            if plural:
                menu.addAction(tr("Pins löschen")).triggered.connect(
                    lambda _=False: self._delete_pins(pins))
            else:
                menu.addAction(tr("Pin löschen")).triggered.connect(
                    lambda _=False: (item.note.remove_pin(item), self.notes_changed.emit()))

        # ---- THREAD ----
        elif isinstance(item, ConnectionItem):
            threads = self.selected_connections()
            plural = len(threads) > 1
            self._add_color_menu(
                menu,
                tr("Fadenfarben") if plural else tr("Fadenfarbe"),
                item.model.color,
                lambda c: self._apply_color_to_connections(threads, c),
            )

            def edit_label():
                default = item.model.label if not plural else ""
                title = tr("Beschriftungen") if plural else tr("Beschriftung")
                text, ok = QInputDialog.getText(
                    views[0] if views else None, title,
                    tr("Beziehung / Text auf dem Faden:"), text=default)
                if ok:
                    for t in threads if plural else [item]:
                        t.set_label(text)
                    self.notes_changed.emit()

            menu.addAction(
                tr("Beschriftungen …") if plural else tr("Beschriftung …")
            ).triggered.connect(lambda _=False: edit_label())
            menu.addSeparator()
            if plural:
                menu.addAction(tr("Fäden löschen")).triggered.connect(
                    lambda _=False: self._delete_connections(threads))
            else:
                menu.addAction(tr("Faden löschen")).triggered.connect(
                    lambda _=False: (self.remove_connection(item), self.notes_changed.emit()))

        # ---- NOTE ----
        elif isinstance(item, NoteItem):
            notes = self.selected_notes()
            plural = len(notes) > 1
            local = item.mapFromScene(scene_pos)

            menu.addAction(tr("Im großen Editor öffnen")).triggered.connect(
                lambda _=False: self.edit_requested.emit(item))
            menu.addAction(tr("FlowView öffnen")).triggered.connect(
                lambda _=False: self.flow_requested.emit(item))
            menu.addAction(tr("Duplizieren")).triggered.connect(
                lambda _=False: self.duplicate_note(item))
            menu.addAction(tr("Gruppe aus Auswahl")).triggered.connect(
                lambda _=False: self.create_group_from_selection())

            has_connections = bool(item.links())
            select_direct = menu.addAction(tr("Verbundene Notizen auswählen"))
            select_direct.setEnabled(has_connections)
            select_direct.setToolTip(
                tr("Diese Notiz und alle direkt verbundenen Notizen auswählen"))
            select_direct.triggered.connect(lambda _=False: self.select_connected(item))

            select_recursive = menu.addAction(
                tr("Verbundene Notizen rekursiv auswählen"))
            select_recursive.setEnabled(has_connections)
            select_recursive.setToolTip(
                tr("Diese Notiz und alles, was über Fäden damit zusammenhängt"))
            select_recursive.triggered.connect(
                lambda _=False: self.select_connected(item, recursive=True))

            menu.addSeparator()
            if not plural:
                menu.addAction(tr("Pin hier hinzufügen")).triggered.connect(
                    lambda _=False: item.add_pin(local.x(), local.y()))

            # Lock: fan-out when multiple notes are selected.
            if not mixed_lock:
                if plural:
                    if all(n.model.locked for n in notes):
                        menu.addAction(tr("Notizen entsperren")).triggered.connect(
                            lambda _=False: self._apply_lock_to_notes(notes, False))
                    else:
                        menu.addAction(tr("Notizen sperren")).triggered.connect(
                            lambda _=False: self._apply_lock_to_notes(notes, True))
                else:
                    if item.model.locked:
                        menu.addAction(tr("Notiz entsperren")).triggered.connect(
                            lambda _=False: self.set_note_locked(item, False))
                    else:
                        menu.addAction(tr("Notiz sperren")).triggered.connect(
                            lambda _=False: self.set_note_locked(item, True))

            # Status: fan-out to all selected notes when plural.
            def set_status(key, _notes=notes):
                for n in _notes:
                    n.model.status = key
                    n.model_changed()
                self._emit_selected(self._current_note, force=True)
                self.notes_changed.emit()

            status_menu = menu.addMenu(tr("Status"))
            status_menu.addAction(tr("Kein Status")).triggered.connect(
                lambda _=False: set_status(""))
            for key, (label, col) in STATUS_INFO.items():
                status_menu.addAction(color_icon(col), tr(label)).triggered.connect(
                    lambda _=False, k=key: set_status(k))

            self._add_color_menu(
                menu,
                tr("Notizfarben") if plural else tr("Notizfarbe"),
                item.model.color,
                lambda c: self._apply_color_to_notes(notes, c),
            )
            menu.addSeparator()
            if plural:
                menu.addAction(tr("Notizen löschen")).triggered.connect(
                    lambda _=False: self._delete_notes(notes))
            else:
                menu.addAction(tr("Notiz löschen")).triggered.connect(
                    lambda _=False: self.remove_note(item))

        # ---- GROUP ----
        elif isinstance(item, GroupItem):
            groups = self.selected_groups()
            plural = len(groups) > 1

            if not plural:
                menu.addAction(tr("Gruppe umbenennen …")).triggered.connect(
                    lambda _=False: self.rename_group(item))

            self._add_color_menu(
                menu,
                tr("Gruppenfarben") if plural else tr("Gruppenfarbe"),
                item.model.color,
                lambda c: self._apply_color_to_groups(groups, c),
            )

            # Lock: same plural/single pattern as notes and pins.
            if not mixed_lock:
                if plural:
                    if all(g.model.locked for g in groups):
                        menu.addAction(tr("Gruppen entsperren")).triggered.connect(
                            lambda _=False: self._apply_lock_to_groups(groups, False))
                    else:
                        menu.addAction(tr("Gruppen sperren")).triggered.connect(
                            lambda _=False: self._apply_lock_to_groups(groups, True))
                else:
                    if item.model.locked:
                        menu.addAction(tr("Gruppe entsperren")).triggered.connect(
                            lambda _=False: self.set_group_locked(item, False))
                    else:
                        menu.addAction(tr("Gruppe sperren")).triggered.connect(
                            lambda _=False: self.set_group_locked(item, True))

            # NEW: wrap the selection in a new parent group (notes + groups).
            menu.addSeparator()
            menu.addAction(tr("Gruppe aus Auswahl")).triggered.connect(
                lambda _=False: self.create_group_from_selection())

            # Z-order: four actions, fan out to every selected group when plural.
            menu.addSeparator()
            if plural:
                menu.addAction(tr("Gruppen nach vorne")).triggered.connect(
                    lambda _=False: self._raise_groups(groups))
                menu.addAction(tr("Gruppen eine Ebene nach vorne")).triggered.connect(
                    lambda _=False: self._raise_groups_one_step(groups))
                menu.addAction(tr("Gruppen eine Ebene nach hinten")).triggered.connect(
                    lambda _=False: self._send_groups_back_one_step(groups))
                menu.addAction(tr("Gruppen nach hinten")).triggered.connect(
                    lambda _=False: self._send_groups_to_back(groups))
            else:
                menu.addAction(tr("Gruppe nach vorne")).triggered.connect(
                    lambda _=False: self.raise_group(item))
                menu.addAction(tr("Gruppe eine Ebene nach vorne")).triggered.connect(
                    lambda _=False: self.raise_group_one_step(item))
                menu.addAction(tr("Gruppe eine Ebene nach hinten")).triggered.connect(
                    lambda _=False: self.send_group_back_one_step(item))
                menu.addAction(tr("Gruppe nach hinten")).triggered.connect(
                    lambda _=False: self.send_group_to_back(item))

            # Dissolve / delete.
            menu.addSeparator()
            if plural:
                menu.addAction(tr("Gruppen auflösen")).triggered.connect(
                    lambda _=False: self._remove_groups(groups))
            else:
                menu.addAction(tr("Gruppe auflösen")).triggered.connect(
                    lambda _=False: self.remove_group(item))
                menu.addAction(tr("Gruppe samt Notizen löschen")).triggered.connect(
                    lambda _=False: self.delete_group_with_notes(item))

        # ---- EMPTY ----
        else:
            sub = menu.addMenu(tr("Neue Notiz hier"))
            for t in self.note_types.values():
                action = sub.addAction(color_icon(t.color), t.label)
                action.triggered.connect(
                    lambda _=False, k=t.key: self.create_note(k, scene_pos))
            menu.addAction(tr("Neue Gruppe hier")).triggered.connect(
                lambda _=False: self.create_empty_group(scene_pos))

        menu.exec(screen_pos)

    def _apply_color_to_notes(self, notes, color):
        for n in notes:
            n.model.color = color
            n.model_changed()
        self._emit_selected(self._current_note, force=True)
        self.notes_changed.emit()

    def _apply_color_to_pins(self, pins, color):
        for p in pins:
            p.set_color(color)
        self.notes_changed.emit()

    def _apply_color_to_connections(self, threads, color):
        for t in threads:
            t.set_color(color)
        self.notes_changed.emit()

    def _apply_color_to_groups(self, groups, color):
        for g in groups:
            g.set_color(color)
        self.notes_changed.emit()

    def _apply_lock_to_notes(self, notes, locked):
        for n in notes:
            n.set_locked(locked)
        self._emit_selected(self._current_note, force=True)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def _apply_lock_to_pins(self, pins, locked):
        for p in pins:
            p.set_locked(locked)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def _apply_lock_to_groups(self, groups, locked):
        for g in groups:
            g.set_locked(locked)
            if locked:
                self._cascade_lock_on(g)
        self.notes_changed.emit()
        self.interaction_finished.emit()

    def _delete_notes(self, notes):
        for n in list(notes):
            self.remove_note(n)

    def _delete_pins(self, pins):
        for p in list(pins):
            p.note.remove_pin(p)
        self.notes_changed.emit()

    def _delete_connections(self, threads):
        for t in list(threads):
            self.remove_connection(t)
        self.notes_changed.emit()

    def _raise_groups(self, groups):
        """Raise each group in the selection above all others, preserving order.

        Ascending z-order so the topmost of the selection ends up on top.
        """
        for g in sorted(groups, key=lambda x: x.zValue()):
            self.raise_group(g)

    def _send_groups_to_back(self, groups):
        """Send each group in the selection behind all others, preserving order.

        Descending z-order so the topmost of the selection ends up topmost
        within the send-to-back group.
        """
        for g in sorted(groups, key=lambda x: x.zValue(), reverse=True):
            self.send_group_to_back(g)

    def _raise_groups_one_step(self, groups):
        """Raise each selected group one step forward, preserving relative order."""
        for g in sorted(groups, key=lambda x: x.zValue(), reverse=True):
            self.raise_group_one_step(g)

    def _send_groups_back_one_step(self, groups):
        """Send each selected group one step backward, preserving relative order."""
        for g in sorted(groups, key=lambda x: x.zValue()):
            self.send_group_back_one_step(g)

    def _remove_groups(self, groups):
        for g in list(groups):
            self.remove_group(g)
        self.notes_changed.emit()

    def _remove_connections_of_pins(self, pins):
        for p in list(pins):
            p.remove_connections()
        self.notes_changed.emit()

    # In BoardScene:
    def note_model_changed(self, note):
        """A note's data changed: bump the mentions revision so caches that
        depend on the whole notebook's content are invalidated."""
        self._mentions_revision += 1
        self.note_content_changed.emit(note)

    def top_level_order_list(self):
        """Order of top-level groups in the Grouped tree view.

        Stored on the scene (like ``_ungrouped_order``) so a drag doesn't need
        a round-trip through ProjectData.  Persisted via
        ``ProjectData.group_order``.
        """
        if not hasattr(self, "_top_level_order"):
            self._top_level_order = []
        return self._top_level_order


class BoardView(QGraphicsView):
    """The view: zoom with the wheel, pan with the middle button, Delete key, fit-all.

    Panning
    -------
    Middle-button drag.  Movement is applied via the scroll bars, which
    are in screen pixels — so the content tracks the cursor 1:1 at any
    zoom level.  The scene rect is huge (set by ``MainWindow``), so this
    never clamps at the content edges.

    We do **not** use ``grabMouse()``: on Windows / some X11 setups it
    can survive a window maximize transition, leaving the OS showing the
    "grab" cursor and blocking further pan movement.  Instead, an
    application-level event filter is installed for the duration of the
    pan — it catches the middle-button release wherever it lands (over
    a note, over a child widget, outside the window) and ends the pan
    cleanly.  ``MainWindow`` also calls ``_end_pan_if_active()`` on its
    own ``changeEvent`` / ``resizeEvent``, so a maximize or restore can
    never leave a stale pan behind.
    """

    MIN_ZOOM = 0.08
    MAX_ZOOM = 4.0

    def __init__(self, scene):
        """Configure rendering, anchors and the rubber-band selection."""
        super().__init__(scene)
        self._panning = False
        self._pan_cursor_active = False
        self._last_pos = None
        self._drag_block = None
        self._drag_origin = None
        self._drag_moved = False
        self._pan_filter_installed = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Watchdog: force-end a stuck pan after 5 s of no movement.  Each
        # mouseMove refreshes the timer; a real drag never fires it, but a
        # swallowed release does.
        self._pan_watchdog = QTimer(self)
        self._pan_watchdog.setInterval(5000)
        self._pan_watchdog.setSingleShot(True)
        self._pan_watchdog.timeout.connect(self._watchdog_reset)

    def contextMenuEvent(self, event):
        """Qt event handler: context-menu request (the scene handles it)."""
        event.accept()

    def wheelEvent(self, event):
        """Qt event handler: mouse wheel.

        Zooming *in* is allowed from any starting point — including a
        fit-all that went below MIN_ZOOM.  Only zooming *out* past
        MIN_ZOOM and zooming *in* past MAX_ZOOM are blocked.
        """
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        new_zoom = self.transform().m11() * factor

        if factor < 1.0 and new_zoom < self.MIN_ZOOM:
            event.accept()
            return
        if factor > 1.0 and new_zoom > self.MAX_ZOOM:
            event.accept()
            return

        self.scale(factor, factor)
        event.accept()

    # -------------------------------------------------- pan: start / move

    def mousePressEvent(self, event):
        """Qt event handler: a mouse button was pressed.

        Middle button → free 2D pan.  Left button on a selected, movable
        item → start a *multi-item* drag (all selected notes + groups).
        Anything else → fall through to Qt's normal item delivery.
        """
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._last_pos = event.position().toPoint()
            self._begin_pan_cursor()
            self._install_pan_filter()
            self._pan_watchdog.start()
            event.accept()
            return

        # Left press inside the current selection → multi-item drag.
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            scene_pos = self.mapToScene(event.position().toPoint())
            item = scene._item_at(scene_pos) if scene is not None else None

            # Only notes and groups start a multi-drag.  Pins inside a
            # selected note follow the note; pins are single-item drags.
            if (item is not None
                    and item.isSelected()
                    and isinstance(item, (NoteItem, GroupItem))
                    and not item.model.locked):
                # A click on a group's resize grip must reach the item so
                # it can resize — do not intercept it here.
                in_grip = False
                if isinstance(item, (NoteItem, GroupItem)):
                    local = item.mapFromScene(scene_pos)
                    in_grip = item._in_grip(local)
                if not in_grip:
                    block = scene.build_selection_block()
                    if block:
                        self._drag_block = block
                        self._drag_origin = scene_pos
                        self._drag_moved = False
                        event.accept()
                        return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Qt event handler: the mouse moved."""
        # Multi-item selection drag.
        if self._drag_block is not None:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._drag_block = None
                self._drag_origin = None
                self._drag_moved = False
                return
            scene_pos = self.mapToScene(event.position().toPoint())
            delta = scene_pos - self._drag_origin
            if not self._drag_moved:
                if delta.manhattanLength() < 3:
                    return
                self._drag_moved = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.scene().move_block(self._drag_block, delta)
            event.accept()
            return

        if self._panning and not (event.buttons() & Qt.MouseButton.MiddleButton):
            self._end_pan()

        if self._panning:
            self._pan_watchdog.start()
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
        # End multi-item selection drag.
        if self._drag_block is not None and event.button() == Qt.MouseButton.LeftButton:
            moved = self._drag_moved
            self._drag_block = None
            self._drag_origin = None
            self._drag_moved = False
            self.unsetCursor()
            if moved:
                self.scene().interaction_finished.emit()
            event.accept()
            return

        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._end_pan()
            event.accept()
            return
        if self._panning:
            self._end_pan()
        super().mouseReleaseEvent(event)
    # -------------------------------------- pan: end + safety nets

    def _begin_pan_cursor(self):
        """Show the closed hand via an application override cursor.

        An override cursor is independent of the viewport/item cursor logic
        in QGraphicsView, so item hover cursors can never capture it as
        their "original" cursor and bring it back later."""
        if not self._pan_cursor_active:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
            self._pan_cursor_active = True

    def _end_pan_cursor(self):
        """Remove the override cursor (balanced, safe to call repeatedly)."""
        if self._pan_cursor_active:
            self._pan_cursor_active = False
            QGuiApplication.restoreOverrideCursor()

    def _end_pan(self):
        """Single choke point that ends a pan and clears the cursor,
        event filter and watchdog."""
        if not self._panning:
            return
        self._panning = False
        self._end_pan_cursor()
        self._remove_pan_filter()
        self._pan_watchdog.stop()
        self._last_pos = None

    def _end_pan_if_active(self):
        """Public alias for ``_end_pan()`` — used by ``MainWindow`` from
        its ``changeEvent`` / ``resizeEvent`` handlers so a maximize or
        restore can never leave a stale pan or stuck cursor behind."""
        self._end_pan()

    def _install_pan_filter(self):
        """Install the application-wide release catcher if not already."""
        if self._pan_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._pan_filter_installed = True

    def _remove_pan_filter(self):
        """Remove the application-wide release catcher."""
        if not self._pan_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except RuntimeError:
                pass
        self._pan_filter_installed = False

    def eventFilter(self, obj, event):
        """Application-wide filter active only while panning: catches the
        middle-button release wherever it happens, so the cursor never
        sticks even if the release goes to a child widget or to the
        window itself."""
        if self._panning and event.type() == QEvent.Type.MouseButtonRelease:
            try:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._end_pan()
            except AttributeError:
                pass
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event):
        """Qt event handler: focus left the view — end any active pan."""
        self._end_pan()
        super().focusOutEvent(event)

    def leaveEvent(self, event):
        """Qt event handler: the pointer left the view — end any active pan."""
        self._end_pan()
        super().leaveEvent(event)

    def _watchdog_reset(self):
        """Force-end a stuck pan after 5 s of no movement.  The watchdog
        is restarted by every pan movement, so a real drag never fires it.
        A release swallowed by a system dialog / another window does."""
        if not self._panning:
            self._pan_watchdog.stop()
            return
        self._end_pan()

    # ------------------------------------------------------ keys and fit

    def keyPressEvent(self, event):
        """Qt event handler: a key was pressed."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.scene().delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def fit_all(self):
        """Zoom so that every note is visible (clamped to MIN_ZOOM)."""

        self._end_pan()

        rect = self.scene().content_rect()
        if rect is None or rect.isNull():
            self.resetTransform()
            self.centerOn(0, 0)
            return

        self.fitInView(
            rect.adjusted(-80, -80, 80, 80),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

        if self.transform().m11() > 1.2:
            self.resetTransform()
            self.centerOn(rect.center())
        elif self.transform().m11() < self.MIN_ZOOM:
            self.resetTransform()
            self.scale(self.MIN_ZOOM, self.MIN_ZOOM)
            self.centerOn(rect.center())

    def reset_zoom(self):
        """Back to 100 % zoom."""
        self._end_pan()
        self.resetTransform()

    # ------------------------------------------------------ paint hooks

    def paintEvent(self, event):
        """Qt event handler: a paint event.

        Publishes ``_view_rect`` (always) and, on a throttle, the count of
        threads and pins visible in it.  Both counts feed the LOD tier
        choosers in ``ConnectionItem`` and ``PinItem``.  The counts are
        expensive (thousands of items × a ``contains()`` call) so they only
        recompute when the view has moved more than 200 scene units — a
        stale count for a fraction of a second is invisible, since the tier
        is a coarse choice.

        Skipped entirely during export: the export uses its own full-fidelity
        paint path and must not have these values overwritten with the
        viewport-derived numbers.
        """
        s = self.scene()
        if (s is not None
                and hasattr(s, "_visible_thread_count")
                and not getattr(s, "export_mode", False)):
            rect = self.mapToScene(self.viewport().rect()).boundingRect()
            if not rect.isEmpty():
                s._view_rect = rect
                last = getattr(self, "_last_count_rect", None)
                if (last is None
                        or abs(rect.x() - last.x()) > 200
                        or abs(rect.y() - last.y()) > 200
                        or abs(rect.width() - last.width()) > 20):
                    self._last_count_rect = rect
                    thread_count = 0
                    for c in s.connection_items:
                        if (rect.contains(c.start_pin.scenePos())
                                or rect.contains(c.end_pin.scenePos())):
                            thread_count += 1
                    s._visible_thread_count = thread_count

                    pin_count = 0
                    for p in s.pin_lookup.values():
                        if rect.intersects(p.sceneBoundingRect()):
                            pin_count += 1
                    s._visible_pin_count = pin_count
        super().paintEvent(event)

    def hideEvent(self, event):
        """Qt event handler: never leave the pan cursor behind when hidden."""
        self._end_pan()
        super().hideEvent(event)