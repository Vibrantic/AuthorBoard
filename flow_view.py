# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""FlowView: a navigable, zoomable view of one root note and its neighbours.

Reached from a note's right-click menu ("FlowView öffnen") or View → FlowView
(Ctrl+T).  The window shows one root note at the top and its direct neighbours
below in pin order; clicking a neighbour's ▶ button re-roots the window on
that note, so the user walks the connected graph one hop at a time.

Layout is a two-column grid: the root in column 0 and its neighbours stacked
in column 1.  Edges use orthogonal routing (horizontal channel, vertical run,
horizontal stub) so they never cross a node and the "straight lines with
corners" look is preserved.  Labels are pills placed on the longest horizontal
segment of each edge, with a collision pass that nudges overlapping pills down.

Both root and neighbour nodes render the same note content as on the board
and are editable through the embedded Inspector.  Edges are selectable;
right-clicking one offers colour / label / delete.  A double-click on the node
opens the big editor; a double-click in the Inspector's connections list
re-roots the view on that note.

The window is non-modal.  At most one instance exists at a time; opening it
again for a different note re-roots the existing window.
"""

import math

from PySide6.QtCore import Qt, QEvent, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QKeySequence, QLinearGradient,
    QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF, QShortcut,
    QTextOption, QGuiApplication,
)
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QFrame, QGraphicsItem, QGraphicsPathItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QSplitter, QToolTip, QVBoxLayout, QWidget,
)

from i18n import tr
from theme import ACCENT, PRESET_COLORS, color_icon, ideal_text_color


# --------------------------------------------------------------------- fonts

_BADGE_FONT = QFont(); _BADGE_FONT.setPointSizeF(7); _BADGE_FONT.setBold(True)
_BADGE_FONT.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
_TITLE_FONT = QFont(); _TITLE_FONT.setPointSize(11); _TITLE_FONT.setBold(True)
_ATTR_FONT = QFont(); _ATTR_FONT.setPointSizeF(8.5)
_ATTR_BOLD = QFont(_ATTR_FONT); _ATTR_BOLD.setBold(True)
_BODY_FONT = QFont(); _BODY_FONT.setPointSizeF(9)
_TAG_FONT = QFont(); _TAG_FONT.setPointSizeF(7.5)


def _text_option(align=Qt.AlignmentFlag.AlignLeft, wrap=False):
    opt = QTextOption(align)
    opt.setWrapMode(
        QTextOption.WrapMode.WordWrap if wrap else QTextOption.WrapMode.NoWrap)
    return opt


def _label_font():
    f = QFont()
    f.setPointSizeF(EDGE_LABEL_FONT_SIZE)
    f.setBold(True)
    return f


# --------------------------------------------------------------- constants

NODE_W = 260
NODE_H = 200
EDGE_PEN_W = 2.5
EDGE_LABEL_FONT_SIZE = 8.5
ARROW_STRIP_W = 24
ARROW_GLYPH = "▶"

# Grid layout
COL_W = NODE_W + 120
ROW_H = NODE_H + 30
GRID_MARGIN = 60
EDGE_CHANNEL_W = 10
LABEL_STACK_H = 20
MIN_LAYER_GAP = 60


# ------------------------------------------- module-level component layout

def lay_out_component(board_scene, root_note):
    """Return ``dict[id(note)] = (col, row)`` for the whole connected
    component of ``root_note``.

    Columns correspond to BFS depth.  Within a column, notes are ordered by
    the order in which BFS first reached them.  Deterministic for a given
    board.

    Shared by ``FlowScene.lay_out_component`` and ``MiniMap._rebuild`` so
    the two never drift.
    """
    if root_note is None or root_note.scene() is not board_scene:
        return {}

    seen = {id(root_note): 0}
    frontier = [root_note]
    by_col = {0: [root_note]}

    while frontier:
        next_frontier = []
        for current in frontier:
            depth = seen[id(current)]
            for other, _label in current.links():
                if id(other) in seen:
                    continue
                seen[id(other)] = depth + 1
                by_col.setdefault(depth + 1, []).append(other)
                next_frontier.append(other)
        frontier = next_frontier

    positions = {}
    for depth, notes in by_col.items():
        for row, note in enumerate(notes):
            positions[id(note)] = (depth, row)
    return positions


# ------------------------------------------------------------------- FlowNode

class FlowNode(QGraphicsItem):
    """One note rendered as a rectangle in the FlowView."""

    def __init__(self, note, kind):
        super().__init__()
        self.note = note
        self.kind = kind
        self._hover_arrow = False
        self.grid_col = 0
        self.grid_row = 0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)

    # ---- geometry

    def boundingRect(self):
        return QRectF(0, 0, NODE_W, NODE_H)

    def shape(self):
        path = QPainterPath()
        path.addRect(QRectF(0, 0, NODE_W, NODE_H))
        return path

    def arrow_rect(self):
        return QRectF(NODE_W - ARROW_STRIP_W, 0, ARROW_STRIP_W, NODE_H)

    def col_left(self):
        return self.pos().x()

    def col_right(self):
        return self.pos().x() + NODE_W

    def pin_flow_pos(self, pin):
        """Where a pin's dot is drawn in the FlowView, in node-local coordinates.

        Side rule:
        * root pins are always on the right (the root is the source side);
        * neighbour pins are on the **left** only if they are the pin through
          which the root's edge enters this neighbour; every other pin of a
          neighbour — a connection to a sibling, to a note outside the view,
          or no connection at all — is on the **right**.
        """
        if self.kind == "root":
            return QPointF(NODE_W - 8, pin.pos().y())
        if self._pin_is_connected_to_root(pin):
            return QPointF(8, pin.pos().y())
        return QPointF(NODE_W - 8, pin.pos().y())

    def _pin_is_connected_to_root(self, pin):
        """True when one of this pin's connections goes to the current root.

        Only the root determines the "incoming" side of a neighbour; a
        connection to a sibling neighbour, to a note outside the FlowView,
        or no connection at all, all count as "not the incoming connection".
        """
        scene = self.scene()
        if scene is None:
            return False
        root = getattr(scene, "root_note", None)
        if root is None:
            return False
        for c in pin.connections:
            other = c.end_pin if c.start_pin is pin else c.start_pin
            if other.note is root:
                return True
        return False

    # ---- state

    def set_kind(self, kind):
        if kind == self.kind:
            return
        self.kind = kind
        self.update()

    def model(self):
        return self.note.model

    # ---- hover / mouse

    def _set_arrow_hover(self, over):
        """Pointing hand over the ▶ strip, otherwise no item cursor at all."""
        if over != self._hover_arrow:
            self._hover_arrow = over
            if over:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
            self.update()

    def hoverEnterEvent(self, event):
        if self.kind == "neighbour":
            self._set_arrow_hover(self.arrow_rect().contains(event.pos()))
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        if self.kind == "neighbour":
            self._set_arrow_hover(self.arrow_rect().contains(event.pos()))
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._set_arrow_hover(False)
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if (self.kind == "neighbour"
                and event.button() == Qt.MouseButton.LeftButton
                and self.arrow_rect().contains(event.pos())):
            scene = self.scene()
            if scene is not None and hasattr(scene, "re_root"):
                scene.re_root(self.note)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click on the node: open the big editor for this note."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        scene = self.scene()
        if scene is None:
            return
        menu = QMenu()
        menu.addAction(tr("Im großen Editor öffnen")).triggered.connect(
            lambda: self._emit_edit())
        if self.kind == "neighbour":
            menu.addSeparator()
            menu.addAction(tr("Als Wurzel setzen")).triggered.connect(
                lambda: scene.re_root(self.note))
        menu.exec(event.screenPos())
        event.accept()

    def _emit_edit(self):
        """Ask the board scene to open the big editor for this note.

        The board's ``edit_requested`` signal is wired to ``MainWindow``'s
        ``open_editor`` slot, which takes a ``NoteItem`` — exactly what
        ``self.note`` is."""
        scene = self.scene()
        if scene is None:
            return
        board_scene = getattr(scene, "board_scene", None)
        if board_scene is not None:
            board_scene.edit_requested.emit(self.note)

    # ---- painting

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        m = self.note.model
        base = QColor(m.color)
        if not base.isValid():
            base = QColor("#fff176")

        rect = QRectF(0, 0, NODE_W, NODE_H)
        fold = 22
        paper = QPainterPath()
        paper.moveTo(0, 0)
        paper.lineTo(NODE_W, 0)
        paper.lineTo(NODE_W, NODE_H - fold)
        paper.lineTo(NODE_W - fold, NODE_H)
        paper.lineTo(0, NODE_H)
        paper.closeSubpath()

        gradient = QLinearGradient(0, 0, 0, NODE_H)
        gradient.setColorAt(0, base.lighter(108))
        gradient.setColorAt(1, base.darker(106))
        painter.fillPath(paper, gradient)

        if self.kind == "root":
            painter.setPen(QPen(QColor(ACCENT), 2.5))
        elif self.isSelected():
            painter.setPen(QPen(QColor(ACCENT), 1.5))
        else:
            painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(paper)

        text_color = ideal_text_color(base)
        muted = QColor(text_color)
        muted.setAlpha(150)

        pad = 14
        inner_w = NODE_W - pad * 2
        if self.kind == "neighbour":
            inner_w -= ARROW_STRIP_W // 2

        info = self.note.type_info() if hasattr(self.note, "type_info") else None
        label = info.label if info else m.note_type
        painter.setFont(_BADGE_FONT)
        painter.setPen(muted)
        painter.drawText(QRectF(pad, 9, inner_w, 12), label.upper(), _text_option())

        fm = QFontMetrics(_TITLE_FONT)
        title = fm.elidedText(m.title or tr("Ohne Titel"),
                              Qt.TextElideMode.ElideRight, int(inner_w))
        painter.setFont(_TITLE_FONT)
        painter.setPen(text_color)
        painter.drawText(QRectF(pad, 22, inner_w, 24), title, _text_option())

        y = 56
        attr_fm = QFontMetrics(_ATTR_FONT)
        attr_bold_fm = QFontMetrics(_ATTR_BOLD)
        for a in m.attributes:
            if not a.value.strip():
                continue
            if y + 15 > NODE_H - 40:
                break
            name = f"{a.name}: " if a.name else ""
            name_w = attr_bold_fm.horizontalAdvance(name)
            if name:
                painter.setFont(_ATTR_BOLD)
                painter.setPen(muted)
                painter.drawText(QRectF(pad, y, name_w + 2, 15), name, _text_option())
            value = attr_fm.elidedText(
                a.value.replace("\n", " "),
                Qt.TextElideMode.ElideRight,
                max(10, int(inner_w - name_w)))
            painter.setFont(_ATTR_FONT)
            painter.setPen(text_color)
            painter.drawText(
                QRectF(pad + name_w, y, inner_w - name_w, 15), value, _text_option())
            y += 15
        if y > 56:
            y += 5

        tags = [t for t in m.tags if t]
        content_bottom = NODE_H - (34 if tags else 14)
        if m.content and content_bottom - y > 14:
            painter.setFont(_BODY_FONT)
            body_color = QColor(text_color)
            body_color.setAlpha(225)
            painter.setPen(body_color)
            painter.drawText(
                QRectF(pad, y, inner_w, content_bottom - y),
                m.content, _text_option(wrap=True))

        if tags:
            tag_fm = QFontMetrics(_TAG_FONT)
            painter.setFont(_TAG_FONT)
            x = pad
            for tag in tags:
                text = f"#{tag}"
                tw = tag_fm.horizontalAdvance(text) + 14
                if x + tw > NODE_W - pad - (ARROW_STRIP_W if self.kind == "neighbour" else 0):
                    break
                chip = QRectF(x, NODE_H - 28, tw, 17)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 38))
                painter.drawRoundedRect(chip, 8.5, 8.5)
                painter.setPen(text_color)
                painter.drawText(chip, text, _text_option(Qt.AlignmentFlag.AlignCenter))
                x += tw + 5

        for pin in self.note.pins:
            p = self.pin_flow_pos(pin)
            painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
            painter.setBrush(QColor(pin.model.color))
            painter.drawEllipse(p, 4, 4)

        if self.kind == "neighbour":
            strip = self.arrow_rect()
            bg = QColor(0, 0, 0, 55 if self._hover_arrow else 30)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRect(strip)

            arrow_font = QFont()
            arrow_font.setPointSizeF(11)
            painter.setFont(arrow_font)
            painter.setPen(QColor("#ffffff") if self._hover_arrow else text_color)
            painter.drawText(strip, ARROW_GLYPH,
                             _text_option(Qt.AlignmentFlag.AlignCenter))

# ------------------------------------------------------------------- FlowEdge

class FlowEdge(QGraphicsPathItem):
    """One thread between two nodes, orthogonal with sharp corners."""

    def __init__(self, connection, source_node, target_node, source_pin, target_pin, channel_x=0):
        super().__init__()
        self.connection = connection
        self.source_node = source_node
        self.target_node = target_node
        self.source_pin = source_pin
        self.target_pin = target_pin
        self.channel_x = channel_x

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(5)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setAcceptHoverEvents(True)
        self._hover = False
        self._path = QPainterPath()
        self._label_pos = QPointF()
        self._label_text = connection.model.label or ""

        self.update_path()

    # ---- geometry

    def update_path(self):
        """Orthogonal route through this edge's dedicated channel.

        Source position is the pin's FlowView position (right side of the
        root).  Target is the pin's FlowView position (left side of the
        neighbour).  Because each edge owns a channel, no two vertical
        runs share an x, so no two edges overlap.
        """
        src = self.source_node.pos() + self.source_node.pin_flow_pos(self.source_pin)
        dst = self.target_node.pos() + self.target_node.pin_flow_pos(self.target_pin)

        path = QPainterPath()
        path.moveTo(src)
        path.lineTo(self.channel_x, src.y())
        path.lineTo(self.channel_x, dst.y())
        path.lineTo(dst.x(), dst.y())

        self._path = path
        self.setPath(path)
        self._label_pos = QPointF(
            self.channel_x, (src.y() + dst.y()) / 2)
        self.prepareGeometryChange()

    def boundingRect(self):
        return self._path.boundingRect().adjusted(-20, -20, 20, 20)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self._path)

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    # ---- context menu

    def contextMenuEvent(self, event):
        scene = self.scene()
        if scene is None:
            return
        menu = QMenu()
        sub = menu.addMenu(tr("Fadenfarbe"))
        for name, hex_color in PRESET_COLORS:
            act = sub.addAction(color_icon(hex_color), tr(name))
            act.triggered.connect(
                lambda _=False, c=hex_color: self._set_color(c))
        sub.addSeparator()
        sub.addAction(tr("Eigene Farbe …")).triggered.connect(
            lambda: self._pick_custom_color())
        menu.addAction(tr("Beschriftung …")).triggered.connect(
            lambda: self._edit_label())
        menu.addSeparator()
        menu.addAction(tr("Faden löschen")).triggered.connect(
            lambda: self._delete())
        menu.exec(event.screenPos())
        event.accept()

    def _set_color(self, color_name):
        self.connection.model.color = color_name
        self._notify_non_structural_change()
        self.update()

    def _pick_custom_color(self):
        c = QColorDialog.getColor(
            QColor(self.connection.model.color), None, tr("Farbe wählen"))
        if c.isValid():
            self._set_color(c.name())

    def _edit_label(self):
        text, ok = QInputDialog.getText(
            None, tr("Beschriftung"),
            tr("Beziehung / Text auf dem Faden:"),
            text=self.connection.model.label)
        if ok:
            self.connection.model.label = text.strip()
            self._label_text = self.connection.model.label
            self._notify_non_structural_change()
            self.update()

    def _delete(self):
        scene = self.scene()
        if scene is not None and hasattr(scene, "request_delete_edge"):
            scene.request_delete_edge(self.connection, self)

    def _notify_non_structural_change(self):
        """Tell the board scene that a connection changed but not the topology.

        Emits ``notes_changed`` so the main window updates the tree,
        statistics and undo checkpoint.  Does **not** emit
        ``note_content_changed`` — no note's data changed, only a thread's
        colour or label.  Does **not** trigger a FlowView rebuild either,
        because the layout is unaffected."""
        scene = self.scene()
        if scene is None:
            return
        board_scene = getattr(scene, "board_scene", None)
        if board_scene is not None:
            board_scene.notes_changed.emit()

    # ---- painting

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self.connection.model.color)
        if not color.isValid():
            color = QColor("#d4a373")

        width = EDGE_PEN_W
        if self._hover or self.isSelected():
            width += 1.2
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin))
        painter.drawPath(self._path)

        if self._label_text:
            fm = QFontMetrics(_label_font())
            tw = fm.horizontalAdvance(self._label_text) + 14
            th = 18
            r = QRectF(self._label_pos.x() - tw / 2,
                       self._label_pos.y() - th / 2, tw, th)
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(QColor(30, 31, 36, 235))
            painter.drawRoundedRect(r, 6, 6)
            painter.setFont(_label_font())
            painter.setPen(QColor("#e6e6ea"))
            painter.drawText(r, self._label_text,
                             _text_option(Qt.AlignmentFlag.AlignCenter))


# ------------------------------------------------------------------- FlowScene

class FlowScene(QGraphicsScene):
    """The FlowView's scene: root + direct neighbours, orthogonal edges."""

    edit_requested = Signal(object)  # kept for API compatibility; unused internally
    root_changed = Signal(object)

    def __init__(self, board_scene):
        super().__init__()
        self.board_scene = board_scene
        self.root_note = None
        self.nodes = []
        self.edges = []
        self._node_by_note = {}
        self.selectionChanged.connect(self.reapply_selection_dim)
        self._selection_locked = False
        self.setSceneRect(-100000, -100000, 200000, 200000)
        self.content_rect = QRectF()

    # ---- API used by the dialog / main window

    def reapply_selection_dim(self):
        """Dim everything not on the "interesting" set.

        Priority order (highest first):

        1.  An *edge* is selected → keep the two notes it connects bright,
            dim the rest.  (Unchanged from before.)
        2.  The minimap has a *silhouette selected* → keep every note on
            the shortest root → silhouette path bright, and every edge
            whose *both* endpoints are on the path.  Everything else
            dims.  This is what makes the walk "pop" out of the graph
            when the user clicks a silhouette on the minimap or a grey
            entry in the note list.
        3.  Nothing selected → everything full opacity.
        """

        # ---- 0) locked: path dim wins regardless of what's selected ----
        if self._selection_locked:
            path_ids = set()
            minimap = getattr(self.board_scene, "_flow_minimap", None)
            if minimap is not None:
                try:
                    path_ids = minimap.current_path_ids()
                except Exception:
                    path_ids = set()
            if path_ids:
                for n in self.nodes:
                    want = 1.0 if id(n.note) in path_ids else 0.25
                    if n.opacity() != want:
                        n.setOpacity(want)
                for e in self.edges:
                    both = (id(e.source_node.note) in path_ids
                            and id(e.target_node.note) in path_ids)
                    want = 1.0 if both else 0.1
                    if e.opacity() != want:
                        e.setOpacity(want)
                return
            # No path active: fall through to the normal rules even if
            # _selection_locked is still True (defensive — lock is only
            # set while a silhouette is selected).

        # ---- 1) an edge is selected --------------------------------
        selected_edges = [e for e in self.edges if e.isSelected()]
        if len(selected_edges) == 1:
            edge = selected_edges[0]
            keep_notes = {edge.source_node, edge.target_node}
            for n in self.nodes:
                want = 1.0 if n in keep_notes else 0.2
                if n.opacity() != want:
                    n.setOpacity(want)
            for e in self.edges:
                want = 1.0 if e is edge else 0.08
                if e.opacity() != want:
                    e.setOpacity(want)
            return

        # ---- 2) minimap path highlight -----------------------------
        path_ids = set()
        minimap = getattr(self.board_scene, "_flow_minimap", None)
        if minimap is not None:
            try:
                path_ids = minimap.current_path_ids()
            except Exception:
                path_ids = set()

        if path_ids:
            # Node ids map to FlowNode.note via id(note), matching the
            # minimap's own id space.
            for n in self.nodes:
                want = 1.0 if id(n.note) in path_ids else 0.25
                if n.opacity() != want:
                    n.setOpacity(want)
            for e in self.edges:
                both = (id(e.source_node.note) in path_ids
                        and id(e.target_node.note) in path_ids)
                want = 1.0 if both else 0.1
                if e.opacity() != want:
                    e.setOpacity(want)
            return

        # ---- 3) nothing selected ----------------------------------
        for n in self.nodes:
            if n.opacity() != 1.0:
                n.setOpacity(1.0)
        for e in self.edges:
            if e.opacity() != 1.0:
                e.setOpacity(1.0)

    def set_root(self, note):
        self.root_note = note
        self.rebuild()

    def rebuild(self):
        """Lay out the root (column 0) and its direct neighbours (column 1).

        Between the two columns, one orthogonal channel per edge reserves
        horizontal space.  Each edge gets its own channel x, so vertical
        runs never overlap.
        """
        for e in self.edges:
            if e.scene() is self:
                self.removeItem(e)
        for n in self.nodes:
            if n.scene() is self:
                self.removeItem(n)
        self.edges.clear()
        self.nodes.clear()
        self._node_by_note.clear()

        if self.root_note is None or self.root_note.scene() is not self.board_scene:
            self.content_rect = QRectF()
            self.root_changed.emit(None)
            return

        neighbours = self.board_scene.direct_neighbours(self.root_note)
        seen = set()
        ordered = []
        for pin_index, other, connection in neighbours:
            if other is self.root_note:
                continue
            if id(other) not in seen:
                seen.add(id(other))
                ordered.append((pin_index, other, connection))

        # Column 0: root.
        root_node = FlowNode(self.root_note, "root")
        root_node.grid_col = 0
        root_node.grid_row = 0
        root_node.setPos(GRID_MARGIN, GRID_MARGIN)
        self.addItem(root_node)
        self.nodes.append(root_node)
        self._node_by_note[id(self.root_note)] = root_node

        # Reserve channels: n_edges channels, each EDGE_CHANNEL_W wide, plus
        # the minimum layer gap on either side of the channel band.  This
        # is what "no overlap" is bought with.
        n_channels = len(ordered)
        channel_band = max(1, n_channels) * EDGE_CHANNEL_W
        neighbour_x = GRID_MARGIN + NODE_W + MIN_LAYER_GAP + channel_band + MIN_LAYER_GAP

        # Column 1: neighbours, one per row.
        for row, (_pin_index, other, _connection) in enumerate(ordered):
            node = FlowNode(other, "neighbour")
            node.grid_col = 1
            node.grid_row = row
            node.setPos(neighbour_x, GRID_MARGIN + row * ROW_H)
            self.addItem(node)
            self.nodes.append(node)
            self._node_by_note[id(other)] = node

        # Edges: one per distinct (root, neighbour) pair, each in its own
        # channel.  Channels are numbered from left to right, so edges close
        # to the root's pin y appear close to the root — visually natural.
        drawn_pairs = set()
        channel_start = GRID_MARGIN + NODE_W + MIN_LAYER_GAP + EDGE_CHANNEL_W / 2
        channel_index = 0
        for _pin_index, other, connection in neighbours:
            if other is self.root_note:
                continue
            target_node = self._node_by_note.get(id(other))
            if target_node is None:
                continue
            pair = (id(self.root_note), id(other))
            if pair in drawn_pairs:
                continue
            drawn_pairs.add(pair)
            start_pin = (connection.start_pin
                         if connection.start_pin.note is self.root_note
                         else connection.end_pin)
            end_pin = (connection.end_pin
                       if connection.end_pin.note is other
                       else connection.start_pin)
            channel_x = channel_start + channel_index * EDGE_CHANNEL_W
            channel_index += 1
            edge = FlowEdge(connection, root_node, target_node,
                            start_pin, end_pin, channel_x=channel_x)
            self.addItem(edge)
            self.edges.append(edge)

        # Scene rect covers the columns and the channel band.
        width = neighbour_x + NODE_W + GRID_MARGIN
        height = GRID_MARGIN * 2 + max(1, len(ordered)) * ROW_H
        self.content_rect = QRectF(0, 0, width, height)
        self.reapply_selection_dim()
        self.root_changed.emit(self.root_note)

    def lay_out_component(self, root_note):
        """See the module-level ``lay_out_component``."""
        return lay_out_component(self.board_scene, root_note)

    # ---- re-root and delete

    def re_root(self, note):
        self.set_root(note)

    def request_delete_edge(self, connection, edge):
        self.board_scene.remove_connection(connection)

    # ---- content refresh

    def refresh_node(self, note):
        """Update a node's rendering when its model changed (no re-layout)."""
        node = self._node_by_note.get(id(note))
        if node is None:
            return
        node.update()

    # ---- selection forwarding

    def selected_node(self):
        for n in self.nodes:
            if n.isSelected():
                return n
        return None

    def mousePressEvent(self, event):
        """While a silhouette is selected in the minimap/note list, block
        selection changes from clicks inside the FlowView so the user
        can't accidentally break the path view.  The ▶ arrows on
        neighbour nodes are still allowed — re-rooting is exactly the
        action we want while walking the path."""
        if self._selection_locked and event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.scenePos(), self.views()[0].transform()) \
                if self.views() else None
            # Allow the neighbour ▶ arrow to keep working.
            if isinstance(item, FlowNode) and item.kind == "neighbour" and \
                    item.arrow_rect().contains(item.mapFromScene(event.scenePos())):
                super().mousePressEvent(event)
                return
            event.accept()
            return
        super().mousePressEvent(event)


# ------------------------------------------------------------------- FlowView

class FlowView(QGraphicsView):
    """The pan/zoom viewport of the FlowView scene.

    Panning: middle-button drag.  Movement is applied via the scroll bars
    (scroll-bar values are in screen pixels, so the content tracks the
    cursor 1:1 at any zoom).  The scene rect is huge (see
    ``FlowScene.__init__``), so this never clamps.

    We do **not** call ``grabMouse()``: on Windows / some X11 setups it
    steals the mouse from the OS but breaks delivery of subsequent move
    events to this override (the scene accepts them first and never
    calls back here), which makes the pan appear dead while the
    closed-hand cursor is still shown.  Instead we install an
    application-level event filter for the duration of the pan — it
    catches the middle-button release wherever it lands and ends the
    pan cleanly.
    """

    MIN_ZOOM = 0.2
    MAX_ZOOM = 3.0

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._panning = False
        self._pan_cursor_active = False
        self._last_pos = None
        self._pan_filter_installed = False
        self._on_interaction = None
        self._minimap = None
        self._note_list = None
        self._on_reset = None

        self._pan_watchdog = QTimer(self)
        self._pan_watchdog.setInterval(500)
        self._pan_watchdog.timeout.connect(self._watchdog_end_pan)

    def set_reset_callback(self, fn):
        self._on_reset = fn

    def set_minimap(self, minimap):
        """Register the mini-map so it can be repositioned on resize."""
        self._minimap = minimap
        self._reposition_minimap()

    def set_note_list(self, panel):
        """Register the note-list panel next to the minimap."""
        self._note_list = panel
        panel._view = self
        self._reposition_minimap()

    def _reposition_minimap(self):
        if self._minimap is None:
            return
        h = self._minimap.height()
        w = self._minimap.width()
        margin = MiniMap.MARGIN
        x = margin
        y = self.viewport().height() - h - margin
        self._minimap.move(x, y)

        if self._note_list is None or not self._note_list.isVisible():
            return

        panel_x = x + w + margin
        available = self.viewport().width() - panel_x - margin
        self._note_list.move(panel_x, y)
        self._note_list.setFixedHeight(h)

        # Clamp width to what fits so the panel never runs off the view.
        cur_w = self._note_list.width()
        target_w = max(NoteListPanel.MIN_W, min(cur_w, available))
        if target_w != cur_w:
            self._note_list.setFixedWidth(target_w)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_minimap()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if self._minimap is not None:
            self._minimap.refresh_viewport()

    def set_interaction_callback(self, fn):
        self._on_interaction = fn

    def _notify_interaction(self):
        if self._on_interaction is not None:
            self._on_interaction()

    def fit_all(self):
        """Zoom to fit the *content* (root + neighbours + edges), not the
        huge scene rect used for free panning."""
        content = getattr(self.scene(), "content_rect", None)
        if content is None or content.isNull() or content.isEmpty():
            # Nothing on screen: keep current transform, centre on origin.
            self.centerOn(0, 0)
            return
        self.fitInView(content, Qt.AspectRatioMode.KeepAspectRatio)
        self._clamp_zoom()

    def reset_zoom(self):
        self.resetTransform()

    def _clamp_zoom(self):
        s = self.transform().m11()
        if s < self.MIN_ZOOM:
            self.scale(self.MIN_ZOOM / s, self.MIN_ZOOM / s)
        elif s > self.MAX_ZOOM:
            self.scale(self.MAX_ZOOM / s, self.MAX_ZOOM / s)

    def wheelEvent(self, event):
        self._notify_interaction()
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        new_zoom = self.transform().m11() * factor
        if new_zoom < self.MIN_ZOOM or new_zoom > self.MAX_ZOOM:
            event.accept()
            return
        self.scale(factor, factor)
        event.accept()

    # -------------------------------------------------- pan: start / move

    def mousePressEvent(self, event):
        """Middle button → free 2D pan.

        Movement is applied via the scroll bars (see ``mouseMoveEvent``).
        No ``grabMouse()`` — that breaks delivery of subsequent move
        events to this override on some platforms.  Instead we install
        an app-level event filter for the duration of the pan to catch
        the middle-button release wherever it lands.
        """
        if event.button() == Qt.MouseButton.MiddleButton:
            self._notify_interaction()
            self._panning = True
            self._last_pos = event.position().toPoint()
            self._begin_pan_cursor()
            self._install_pan_filter()
            self._pan_watchdog.start()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """While the middle button is held, scroll the view by the
        pointer delta.  Scroll-bar values are in screen pixels, so the
        content tracks the cursor 1:1 at *every* zoom; and because the
        scene rect is huge (see ``FlowScene.__init__``) it never clamps
        at the content edges."""

        if self._panning and not (event.buttons() & Qt.MouseButton.MiddleButton):
            self._end_pan()

        if self._panning:
            # Any real movement means the user is still dragging —
            # restart the inactivity watchdog.
            self._pan_watchdog.start()
            self._notify_interaction()

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
        if self._panning and event.button() == Qt.MouseButton.MiddleButton:
            self._end_pan()
            self._notify_interaction()
            event.accept()
            return
        # Defensive: any release while a pan is (unexpectedly) still
        # active also ends it.
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
        if not self._panning:
            return
        self._panning = False
        self._end_pan_cursor()
        self._remove_pan_filter()
        self._pan_watchdog.stop()
        self._last_pos = None

    def _install_pan_filter(self):
        """Install the application-wide release catcher if not already."""
        if self._pan_filter_installed:
            return
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            self._pan_filter_installed = True

    def _remove_pan_filter(self):
        """Remove the application-wide release catcher."""
        if not self._pan_filter_installed:
            return
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except RuntimeError:
                pass
        self._pan_filter_installed = False

    def eventFilter(self, obj, event):
        """Application-wide filter active only while panning: catches
        the middle-button release wherever it happens, so the cursor
        never sticks even if the release goes to a child widget or to
        the window itself."""
        if self._panning and event.type() == QEvent.Type.MouseButtonRelease:
            try:
                if event.button() == Qt.MouseButton.MiddleButton:
                    self._end_pan()
            except AttributeError:
                pass
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event):
        """End any active pan if the window loses focus mid-drag."""
        self._end_pan()
        super().focusOutEvent(event)

    def leaveEvent(self, event):
        """End any active pan if the cursor leaves the widget mid-drag."""
        self._end_pan()
        super().leaveEvent(event)

    def _watchdog_end_pan(self):
        """Force-end a stuck pan after 500 ms of no movement.  The
        watchdog is restarted by every pan movement, so a real drag
        never fires it.  A release swallowed by a system dialog / another
        window does."""
        if not self._panning:
            self._pan_watchdog.stop()
            return
        # Only end if the middle button is really up.  If we cannot
        # query the button state (unusual), fall back to ending — the
        # user can just start another pan if this was premature.
        try:
            from PySide6.QtWidgets import QApplication
            buttons = QApplication.mouseButtons()
            if buttons & Qt.MouseButton.MiddleButton:
                return
        except Exception:
            pass
        self._end_pan()

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key.Key_0
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self._on_reset is not None:
                self._on_reset()
            else:
                self.fit_all()
            event.accept()
            return
        if event.key() == Qt.Key.Key_1 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.reset_zoom()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Right-click on empty FlowView background → menu with reset.
        Right-click on a node or edge is handled by that item's own
        contextMenuEvent (the QGraphicsView path)."""
        scene = self.scene()
        item = self.itemAt(event.pos()) if scene is not None else None
        if item is not None:
            # Let the item's own contextMenuEvent run through the
            # standard QGraphicsView path.
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        act_reset = menu.addAction(tr("Ansicht zurücksetzen"))
        act_reset.setShortcut(QKeySequence("Ctrl+0"))
        if self._on_reset is not None:
            act_reset.triggered.connect(self._on_reset)
        else:
            act_reset.triggered.connect(self.fit_all)
        menu.exec(event.globalPos())
        event.accept()

    def hideEvent(self, event):
        self._end_pan()
        super().hideEvent(event)

# ------------------------------------------------------------------- MiniMap

class MiniMap(QGraphicsView):
    """A small floating overview in the bottom-left corner of the FlowView.

    Active vs. silhouette dots
    --------------------------
    *   **Active dots** — *exactly the notes the FlowView is showing*
        (root + every direct neighbour).  Filled, clickable → re-roots
        the FlowView.  The minimap and the FlowView never disagree about
        which nodes are "current".
    *   **Silhouette dots** — the nearest ``MAX_DOTS − |active|`` further
        notes by BFS distance, plus any nodes on the currently
        highlighted path.  Drawn as small hollow rings.  Clickable, but
        with a *different* action: it highlights the shortest path from
        the root to that silhouette through the graph so the user sees
        which active neighbour to click next.  Notes beyond the cap are
        not drawn here but still appear in the note list.

    Path highlighting
    -----------------
    Only **one** silhouette can be selected at a time.  Selecting a
    silhouette draws a poly-line through the dots of every intermediate
    node on the shortest root → silhouette path.  When the user re-roots
    (clicks an active dot), the path is recomputed from the new root to
    the still-selected silhouette, and — if the destination no longer
    fits under the 50-dot cap — the destination *and every node on its
    path* are force-included so the walk stays fully visible.  The
    selection is only cleared when the destination becomes the new root
    or an active neighbour (it is now on screen in the main FlowView
    anyway) or when the user picks a different silhouette.
    """
    rebuilt = Signal()

    SIZE = 240
    MARGIN = 12
    DOT_R = 2.5
    ROOT_R = 5
    ACTIVE_R = 4
    NEIGHBOUR_ALPHA = 255
    HIT_INFLATE = 4
    MAX_DOTS = 50
    PATH_COLOR = "#ffd54f"

    def __init__(self, dialog, parent):
        super().__init__(parent)
        self.dialog = dialog
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            "QGraphicsView { background: #1a1b20; "
            "border: 1px solid #3a3b45; border-radius: 6px; }")
        self.setMouseTracking(True)
        self.setToolTip(tr("Minimap: Wurzel + Nachbarn klicken = dorthin springen; "
                           "grauer Punkt = Pfad dorthin anzeigen."))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.raise_()
        self.setFixedSize(self.SIZE, self.SIZE)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setSceneRect(QRectF(0, 0, self.SIZE, self.SIZE))

        self._positions = {}          # id(note) -> (col, row)
        self._notes = {}              # id(note) -> NoteItem  (every drawn dot)
        self._dot_rects = {}          # id(note) -> QRectF    (every drawn dot)
        self._active_ids = set()      # root + all FlowView neighbours
        self._silhouette_ids = set()  # capped set + forced path nodes
        self._selected_silhouette = None
        self._path_items = []
        self._path_highlight_rings = []
        self._viewport_item = None
        self._root_id = None

        self._rebuild()

    # ------------------------------------------------------------------ data

    def _rebuild(self):
        self._scene.clear()
        self._viewport_item = None
        self._path_items = []
        self._path_highlight_rings = []
        self._dot_rects = {}
        self._positions = {}
        self._notes = {}
        self._active_ids = set()
        self._silhouette_ids = set()
        self._root_id = None

        board_scene = self.dialog.board_scene
        root_note = self.dialog._scene.root_note
        if root_note is None or root_note.scene() is not board_scene:
            self._selected_silhouette = None
            self.rebuilt.emit()
            return

        positions = lay_out_component(board_scene, root_note)
        if not positions:
            self._selected_silhouette = None
            self.rebuilt.emit()
            return

        self._positions = positions
        self._root_id = id(root_note)

        # ---- active set = exactly the notes shown in the FlowView -----
        # Reading FlowScene.nodes guarantees the minimap and the main
        # view describe the same set of "current" nodes.
        active_ids = {
            id(fn.note) for fn in self.dialog._scene.nodes
            if fn.note is not None and fn.note.scene() is board_scene
        }
        active_ids.add(id(root_note))
        self._active_ids = active_ids

        # ---- path to the currently selected silhouette (if any) ------
        # Computed *before* deciding the silhouette set so path nodes
        # can be excluded from the "extra silhouettes" budget and drawn
        # unconditionally (a truncated walk would mislead the user).
        selected_path = None
        if self._selected_silhouette is not None:
            sel = self._selected_silhouette
            if sel == self._root_id:
                # Destination reached → clear the selection.
                self._selected_silhouette = None
            else:
                selected_path = self._shortest_path(
                    board_scene, root_note, sel)
                if selected_path is None:
                    # Destination became unreachable (edge deleted).
                    self._selected_silhouette = None

        # ---- silhouette set ----------------------------------------
        # Path nodes are always drawn.  The MAX_DOTS budget caps the
        # *extra* silhouette dots (nearest non-active, non-path nodes).
        # Total dot count is therefore |active| + |path| + min(budget,
        # available) — exactly MAX_DOTS in the common case, and bounded
        # above by |active| + |path| in pathological cases.
        path_set = set()
        if selected_path:
            for nid in selected_path:
                if nid not in active_ids:
                    path_set.add(nid)

        remaining = max(
            0, self.MAX_DOTS - len(active_ids) - len(path_set))
        ordered_non_active = sorted(
            (nid for nid in positions
             if nid not in active_ids and nid not in path_set),
            key=lambda nid: positions[nid])
        extra = ordered_non_active[:remaining] if remaining > 0 else []

        self._silhouette_ids = set(path_set) | set(extra)

        # ---- local packing -----------------------------------------
        # Only the nodes we are about to draw affect the pixel layout.
        # If we used the whole component's extents (BFS depth up to
        # hundreds of columns, hundreds of rows in a hub column), the
        # dots would be squeezed into a fraction of a pixel each.
        # We keep the BFS depth as the *column* (left → right = closer
        # → farther) but re-pack rows per column so the drawn nodes
        # fill the square.
        drawn_ids = set(self._active_ids) | set(self._silhouette_ids)
        drawn_positions = {
            nid: positions[nid]
            for nid in drawn_ids
            if nid in positions
        }

        if not drawn_positions:
            self._update_viewport_rect()
            self.dialog._set_selection_lock(
                self._selected_silhouette is not None)
            self.rebuilt.emit()
            return

        col_count = max(c for c, _r in drawn_positions.values()) + 1

        per_col_counts = {}
        for c, _r in drawn_positions.values():
            per_col_counts[c] = per_col_counts.get(c, 0) + 1
        row_count = max(per_col_counts.values())

        margin = 10
        usable = self.SIZE - 2 * margin
        step_x = usable / (col_count - 1) if col_count > 1 else 0
        step_y = usable / (row_count - 1) if row_count > 1 else 0
        # Single-column / single-row → centre on the canvas.
        if col_count == 1:
            step_x = 0
        if row_count == 1:
            step_y = 0
        origin_x = margin if col_count > 1 else self.SIZE / 2
        origin_y = margin if row_count > 1 else self.SIZE / 2

        next_row_in_col = {}
        drawn_row = {}
        for nid, (col, _orig_row) in sorted(
                drawn_positions.items(),
                key=lambda kv: (kv[1][0], kv[1][1])):
            r = next_row_in_col.get(col, 0)
            next_row_in_col[col] = r + 1
            drawn_row[nid] = r

        def screen_xy(nid):
            col = drawn_positions[nid][0]
            row = drawn_row[nid]
            return origin_x + col * step_x, origin_y + row * step_y

        by_pyid = {id(it): it for it in board_scene.note_lookup.values()}

        # ---- draw active dots (filled) -----------------------------
        for nid in self._active_ids:
            note = by_pyid.get(nid)
            if note is None or nid not in positions:
                continue
            x, y = screen_xy(nid)
            is_root = nid == self._root_id
            radius = self.ROOT_R if is_root else self.ACTIVE_R

            color = QColor(note.model.color)
            if not color.isValid():
                color = QColor("#fff176")
            color.setAlpha(self.NEIGHBOUR_ALPHA)

            dot = self._scene.addEllipse(
                QRectF(x - radius, y - radius, radius * 2, radius * 2),
                QPen(QColor(0, 0, 0, 0)), QBrush(color))
            dot.setZValue(1)
            dot.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

            if is_root:
                ring = self._scene.addEllipse(
                    QRectF(x - radius - 2, y - radius - 2,
                           (radius + 2) * 2, (radius + 2) * 2),
                    QPen(QColor(ACCENT), 1.5), QBrush(Qt.BrushStyle.NoBrush))
                ring.setZValue(2)
                ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

            self._dot_rects[nid] = QRectF(
                x - radius, y - radius, radius * 2, radius * 2)
            self._notes[nid] = note

        # ---- draw silhouette dots (hollow rings) -------------------
        for nid in self._silhouette_ids:
            note = by_pyid.get(nid)
            if note is None or nid not in positions:
                continue
            x, y = screen_xy(nid)
            r = self.DOT_R

            ring_color = QColor("#8d8e9a")
            ring_color.setAlpha(220)
            dot = self._scene.addEllipse(
                QRectF(x - r, y - r, r * 2, r * 2),
                QPen(ring_color, 1.0),
                QBrush(Qt.BrushStyle.NoBrush))
            dot.setZValue(1)
            dot.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

            self._dot_rects[nid] = QRectF(x - r, y - r, r * 2, r * 2)
            self._notes[nid] = note

        # ---- highlight the selected silhouette + draw the path -----
        if self._selected_silhouette is not None:
            rect = self._dot_rects.get(self._selected_silhouette)
            if rect is not None:
                hl = self._scene.addEllipse(
                    rect.adjusted(-2, -2, 2, 2),
                    QPen(QColor(self.PATH_COLOR), 1.4),
                    QBrush(Qt.BrushStyle.NoBrush))
                hl.setZValue(3)
                hl.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._path_highlight_rings.append(hl)

            if selected_path:
                self._draw_path(selected_path)

        # ---- viewport box around the active set --------------------
        self._update_viewport_rect()
        self.dialog._set_selection_lock(
            self._selected_silhouette is not None)
        self.rebuilt.emit()



    # --------------------------------------------------------- graph search

    def _shortest_path(self, board_scene, start_note, goal_id):
        """BFS on the board's note graph.

        Returns ``[start_id, ..., goal_id]`` or ``None`` if unreachable."""
        if id(start_note) == goal_id:
            return [goal_id]

        parent = {id(start_note): None}
        frontier = [start_note]
        while frontier:
            next_frontier = []
            for note in frontier:
                for other, _label in note.links():
                    oid = id(other)
                    if oid in parent:
                        continue
                    parent[oid] = id(note)
                    if oid == goal_id:
                        path = [oid]
                        cur = parent[oid]
                        while cur is not None:
                            path.append(cur)
                            cur = parent.get(cur)
                        path.reverse()
                        return path
                    next_frontier.append(other)
            frontier = next_frontier
        return None

    def _draw_path(self, path_ids):
        """Draw one line per consecutive dot pair on ``path_ids``.

        Every node on the path is force-included in ``_silhouette_ids``
        (or is an active node), so it always has a dot and every
        segment is rendered — the amber walk is drawn end-to-end.

        Intermediate nodes get a small amber highlight ring so the user
        sees at a glance which dots to click next.  The root node does
        not get an extra ring (it already has the accent ring).

        Segments whose endpoints lack a dot (only possible if a path
        node has no position in the drawn set, which `_rebuild`
        guarantees won't happen) are skipped rather than emitted with
        a garbage coordinate — defensive only.
        """
        if not path_ids or len(path_ids) < 2:
            return

        pen = QPen(QColor(self.PATH_COLOR), 1.3,
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)

        for a_id, b_id in zip(path_ids, path_ids[1:]):
            ra = self._dot_rects.get(a_id)
            rb = self._dot_rects.get(b_id)
            if ra is None or rb is None:
                # Defensive: should be impossible after _rebuild's
                # force-include of path nodes.  Skip the segment
                # rather than crash or draw to a made-up point.
                continue

            p1 = ra.center()
            p2 = rb.center()

            qpp = QPainterPath(QPointF(p1))
            qpp.lineTo(QPointF(p2))
            item = self._scene.addPath(
                qpp, pen, QBrush(Qt.BrushStyle.NoBrush))
            item.setZValue(0.5)       # below dots, below viewport box
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._path_items.append(item)

            # Highlight every intermediate node, not the root (the root
            # already has its own accent ring drawn above).
            if a_id != self._root_id:
                hl = self._scene.addEllipse(
                    ra.adjusted(-1.5, -1.5, 1.5, 1.5),
                    QPen(QColor(self.PATH_COLOR), 1.0),
                    QBrush(Qt.BrushStyle.NoBrush))
                hl.setZValue(3)
                hl.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._path_highlight_rings.append(hl)

    # ------------------------------------------------------- viewport box

    def _update_viewport_rect(self):
        if self._viewport_item is not None:
            try:
                self._scene.removeItem(self._viewport_item)
            except RuntimeError:
                pass
            self._viewport_item = None

        rects = [self._dot_rects[nid]
                 for nid in self._active_ids if nid in self._dot_rects]
        if not rects:
            return
        box = QRectF(rects[0])
        for r in rects[1:]:
            box = box.united(r)
        box = box.adjusted(-4, -4, 4, 4)

        self._viewport_item = self._scene.addRect(
            box,
            QPen(QColor(ACCENT), 1.2, Qt.PenStyle.DashLine),
            QBrush(Qt.BrushStyle.NoBrush))
        self._viewport_item.setZValue(100)
        self._viewport_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def refresh_viewport(self):
        if self.isVisible():
            self._update_viewport_rect()

    def refresh(self):
        self._rebuild()

    def current_path_ids(self):
        """Ids of the notes on the currently highlighted root → silhouette
        path (empty when no silhouette is selected).  Consumed by
        FlowScene.reapply_selection_dim to dim everything off the path."""
        if self._selected_silhouette is None:
            return set()
        root_note = self.dialog._scene.root_note
        if root_note is None:
            return set()
        path = self._shortest_path(
            self.dialog.board_scene, root_note, self._selected_silhouette)
        return set(path) if path else set()

    def full_component_entries(self):
        """Notes the user can act on, as ``(nid, note, distance,
        is_active)``, sorted by (active-descending, BFS distance, title).

        Scope is *not* the whole connected component — that would offer
        300-hop notes on a 2000-note project, whose paths are neither
        walkable nor useful.  Scope is:

        * the root and its active neighbours (always);
        * the nearest ``MAX_DOTS − |active|`` notes by BFS distance
          (same cap the minimap uses to choose which dots to draw);
        * anything on the currently highlighted path (so a distant
          destination stays reachable while its path is being walked).

        This keeps the list and the minimap consistent: every dot you
        can see is in the list, every list entry corresponds to a dot
        (or an active node, which is also a dot).  Nothing further is
        offered because there is no walkable route to offer.
        """
        board_scene = self.dialog.board_scene
        root_note = self.dialog._scene.root_note
        if root_note is None or root_note.scene() is not board_scene:
            return []

        positions = lay_out_component(board_scene, root_note)
        if not positions:
            return []

        by_pyid = {id(it): it for it in board_scene.note_lookup.values()}

        # Same selection rule as _rebuild: active, then nearest by BFS
        # distance, then path nodes.
        active_ids = set(self._active_ids)
        ordered_non_active = sorted(
            (nid for nid in positions if nid not in active_ids),
            key=lambda nid: positions[nid])       # BFS order via (col, row)
        budget = max(0, self.MAX_DOTS - len(active_ids))
        silhouette_ids = ordered_non_active[:budget]

        if self._selected_silhouette is not None:
            path = self._shortest_path(
                board_scene, root_note, self._selected_silhouette)
            if path:
                for nid in path:
                    if nid not in active_ids:
                        silhouette_ids.append(nid)

        # Final set of ids to list — deduplicate while preserving order.
        seen = set()
        chosen_ids = []
        for nid in list(active_ids) + list(silhouette_ids):
            if nid in seen:
                continue
            if nid not in positions:
                continue
            seen.add(nid)
            chosen_ids.append(nid)

        entries = []
        for nid in chosen_ids:
            note = by_pyid.get(nid)
            if note is None:
                continue
            is_active = nid in active_ids
            distance = positions[nid][0]         # col = BFS depth
            entries.append((nid, note, distance, is_active))

        entries.sort(key=lambda e: (not e[3], e[2],
                                    (e[1].model.title or "").lower()))
        return entries

    # -------------------------------------------------------------- legend

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._dot_rects:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = QFont()
        font.setPointSizeF(7)
        painter.setFont(font)
        fm = QFontMetrics(font)

        entries = [
            ("●", "",             QColor(ACCENT)),
            (None, tr("Wurzel"),  QColor(ACCENT)),
            ("○", "",             QColor("#8d8e9a")),
            (None, tr("Notizen"), QColor("#8d8e9a")),
        ]

        gap = 4
        width = 0
        for glyph, text, _col in entries:
            if glyph:
                width += fm.horizontalAdvance(glyph) + 2
            if text:
                width += fm.horizontalAdvance(text) + gap
        width += 8

        x = self.viewport().width() - width - 8
        y = self.viewport().height() - 8

        for glyph, text, col in entries:
            painter.setPen(col)
            if glyph:
                painter.drawText(QPointF(x, y), glyph)
                x += fm.horizontalAdvance(glyph) + 2
            if text:
                painter.drawText(QPointF(x, y), text)
                x += fm.horizontalAdvance(text) + gap
        painter.end()

    # --------------------------------------------------------------- mouse

    def _hit(self, scene_pos):
        for nid, rect in reversed(list(self._dot_rects.items())):
            if rect.adjusted(-self.HIT_INFLATE, -self.HIT_INFLATE,
                             self.HIT_INFLATE, self.HIT_INFLATE).contains(scene_pos):
                return nid
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = self.mapToScene(event.position().toPoint())
        nid = self._hit(pos)
        if nid is None:
            super().mousePressEvent(event)
            return

        note = self._notes.get(nid)
        if note is None:
            event.accept()
            return

        if nid in self._active_ids:
            # Active dot → re-root the FlowView.  dialog.set_root()
            # refreshes the minimap, so the new root + its neighbours
            # become the new active set immediately (quirk #2).
            self.dialog.set_root(note)
        else:
            # Silhouette dot → toggle path highlight.  No re-root.
            if self._selected_silhouette == nid:
                self._selected_silhouette = None
            else:
                self._selected_silhouette = nid
                self.dialog._scene.clearSelection()
            self._rebuild()
        event.accept()

    def event(self, ev):
        if ev.type() == QEvent.Type.ToolTip:
            pos = self.mapToScene(ev.pos())
            nid = self._hit(pos)
            if nid is not None:
                note = self._notes.get(nid)
                if note is not None:
                    QToolTip.showText(
                        ev.globalPos(),
                        note.model.title or tr("Ohne Titel"),
                        self)
                return True
            QToolTip.hideText()
            return True
        return super().event(ev)


class _ResizeGrip(QFrame):
    """Thin vertical grip that resizes the parent NoteListPanel on drag.

    Only the panel's *width* changes — height stays locked to the minimap
    by ``FlowView._reposition_minimap``.
    """

    def __init__(self, panel):
        super().__init__(panel)
        self._panel = panel
        self._drag = None
        self.setFixedWidth(4)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setStyleSheet(
            "QFrame { background: #3a3b45; border: none; border-radius: 2px; }"
            "QFrame:hover { background: #6c9cff; }")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = (event.globalPosition().x(), self._panel.width())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            x0, w0 = self._drag
            new_w = w0 + int(event.globalPosition().x() - x0)
            new_w = max(self._panel.MIN_W, min(self._panel.MAX_W, new_w))
            if new_w != self._panel.width():
                self._panel.setFixedWidth(new_w)
                self._panel.reposition()
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None
        event.accept()


class NoteListPanel(QWidget):
    """A searchable list of the note titles shown on the minimap.

    Positioned to the right of the minimap at the same height, resizable
    on its right edge.  The search box filters in real time.

    Clicking a name has the same effect as clicking its dot on the
    minimap: active notes re-root the FlowView, silhouettes toggle the
    path highlight.  Active and silhouette entries are distinguished by
    the ``●`` / ``○`` prefix, matching the minimap legend.
    """

    note_selected = Signal(object)  # id(note) of the clicked entry

    MIN_W = 140
    MAX_W = 420
    DEFAULT_W = 350

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = None          # FlowView, set via FlowView.set_note_list
        self._entries = []         # list[(nid, title, is_active)]
        self._selected_id = None   # id(note) of the currently highlighted silhouette

        self.setObjectName("NoteListPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#NoteListPanel { background: #1a1b20; "
            "border: 1px solid #3a3b45; border-radius: 6px; }")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget()
        content.setObjectName("NoteListContent")
        content.setStyleSheet(
            "QWidget#NoteListContent { background: transparent; border: none; }")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(6, 4, 6, 4)
        cl.setSpacing(2)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Notizen suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(
            "QLineEdit { background: #202127; border: 1px solid #3a3b45; "
            "border-radius: 4px; padding: 3px 6px; font-size: 8pt; "
            "color: #e6e6ea; }"
            "QLineEdit:focus { border: 1px solid #6c9cff; }")
        self.search.textChanged.connect(self._apply_filter)
        self.search.installEventFilter(self)
        cl.addWidget(self.search)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setStyleSheet(
            "QListWidget { background: transparent; border: none; "
            "outline: 0; font-size: 8pt; }"
            "QListWidget::item { padding: 2px 4px; border-radius: 3px; }"
            "QListWidget::item:hover { background: #24252c; }"
            "QListWidget::item:selected { background: #2f3a57; color: white; }")
        self.list.itemClicked.connect(self._on_item_clicked)
        cl.addWidget(self.list, 1)

        outer.addWidget(content, 1)

        self._grip = _ResizeGrip(self)
        outer.addWidget(self._grip)

        self.setFixedWidth(self.DEFAULT_W)
        self.setToolTip(tr("Klick auf einen Namen: aktive Notiz öffnet, "
                           "grauer Punkt zeigt den Pfad dorthin."))

    def set_entries(self, entries, selected_id=None):
        """entries: list of (nid, title, is_active)."""
        self._entries = list(entries)
        self._selected_id = selected_id
        self._apply_filter()

    def _apply_filter(self):
        query = self.search.text().strip().lower()
        self.list.blockSignals(True)
        self.list.clear()
        amber = QColor(MiniMap.PATH_COLOR)

        for nid, title, is_active in self._entries:
            if query and query not in title.lower():
                continue
            prefix = "● " if is_active else "○ "
            item = QListWidgetItem(prefix + title)
            item.setData(Qt.ItemDataRole.UserRole, nid)

            # Amber styling for the selected silhouette: matches the
            # minimap path so the two read as one.
            if nid == self._selected_id and not is_active:
                item.setBackground(QColor(amber.red(), amber.green(),
                                          amber.blue(), 60))
                item.setForeground(amber)

            self.list.addItem(item)

        # Do not leave a system-selection row anywhere — the amber
        # highlight above is what the user should see.  This also
        # prevents QListWidget from hiding the amber colours behind a
        # blue selection rectangle when the list has focus.
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)


    def _on_item_clicked(self, item):
        if item is None:
            return
        self.note_selected.emit(item.data(Qt.ItemDataRole.UserRole))

    def reposition(self):
        """Called after user resizes the panel; FlowView repositions both
        widgets together."""
        if self._view is not None:
            self._view._reposition_minimap()

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # Enter must not bubble up to the QDialog — it would
                # accept the dialog or activate an unrelated button
                # (that's the "opens colour picker" bug).
                self.search.clear()
                self.list.setFocus()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.search.clear()
                return True
        return super().eventFilter(obj, event)

# ------------------------------------------------------------- FlowViewDialog

class FlowViewDialog(QDialog):
    """The FlowView window: view + embedded Inspector, non-modal."""

    def __init__(self, board_scene, attachments, root_note, parent=None,
                 note_types=None, inspector_factory=None):
        super().__init__(parent)
        self.setWindowTitle(tr("FlowView"))
        self.resize(1100, 760)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setSizeGripEnabled(True)

        self.board_scene = board_scene
        self._user_moved = False

        self._scene = FlowScene(board_scene)
        self._view = FlowView(self._scene)

        self._root_history = []  # list of note ids, oldest first
        self._root_history_index = -1

        if inspector_factory is None:
            self.inspector = _default_inspector_factory(
                attachments, note_types=note_types)
        else:
            self.inspector = inspector_factory(attachments)


        # FlowView fills the left pane.
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._view)
        self._splitter.addWidget(self.inspector)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)


        # The mini-map is a child of the FlowView (window-in-window).
        # It is built before the root note is set; the first _rebuild() in
        # MiniMap.__init__ is a no-op (no root), and set_root() below
        # refreshes it once the root exists.
        self.minimap = MiniMap(self, self._view)
        self._view.set_minimap(self.minimap)
        self.board_scene._flow_minimap = self.minimap
        self.minimap.show()

        y_btn = self.minimap.height() - 26

        self._btn_prev = QPushButton("◀", self.minimap)
        self._btn_prev.setFixedSize(20, 20)
        self._btn_prev.setToolTip(tr("Ein Schritt zurück auf dem Pfad"))
        self._btn_prev.setStyleSheet(
            "QPushButton { background: #26272e; color: #e6e6ea; "
            "border: 1px solid #3a3b45; border-radius: 4px; "
            "font-size: 9pt; padding: 0; }"
            "QPushButton:hover { background: #2f313a; }"
            "QPushButton:disabled { color: #5d5e69; }")
        self._btn_prev.clicked.connect(self._go_prev_on_path)
        self._btn_prev.move(6, y_btn)
        self._btn_prev.raise_()
        self._btn_prev.show()

        self._btn_next = QPushButton("▶", self.minimap)
        self._btn_next.setFixedSize(20, 20)
        self._btn_next.setToolTip(tr("Ein Schritt vor auf dem Pfad"))
        self._btn_next.setStyleSheet(self._btn_prev.styleSheet())
        self._btn_next.clicked.connect(self._go_next_on_path)
        self._btn_next.move(30, y_btn)
        self._btn_next.raise_()
        self._btn_next.show()

        self._update_nav_buttons()

        self.note_list = NoteListPanel(self._view)
        self._view.set_note_list(self.note_list)
        self.note_list.note_selected.connect(self._on_note_list_selected)
        self.minimap.rebuilt.connect(self._refresh_note_list)
        self.minimap.rebuilt.connect(self._refresh_path_dim)
        self.note_list.show()

        title = QLabel(tr("FlowView"))
        title.setObjectName("Section")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(title)
        layout.addWidget(self._splitter, 1)

        board_scene.structure_changed.connect(self._rebuild)
        board_scene.note_content_changed.connect(self._refresh_node)
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._scene.root_changed.connect(self._on_scene_root_changed)
        self.inspector.jump_requested.connect(self._on_inspector_jump)
        self.inspector.edit_requested.connect(self._on_inspector_edit)

        self.set_root(root_note)

        shortcut = QShortcut(QKeySequence("F2"), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._open_current_editor)

        self.minimap_toggle = QPushButton(tr("Minimap"))
        self.minimap_toggle.setCheckable(True)
        self.minimap_toggle.setChecked(True)
        self.minimap_toggle.setToolTip(tr("Minimap ein-/ausblenden"))
        self.minimap_toggle.toggled.connect(self._toggle_minimap)

        close = QPushButton(tr("Schließen"))
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(self.minimap_toggle)
        bottom.addStretch(1)
        bottom.addWidget(close)
        layout.addLayout(bottom)

        self._view.set_interaction_callback(self._on_view_moved)
        self._view.set_reset_callback(self.reset_view)

    # ---- API used by MainWindow

    def _toggle_minimap(self, on):
        self.minimap.setVisible(on)
        self.note_list.setVisible(on)
        self._btn_prev.setVisible(on)
        self._btn_next.setVisible(on)
        if on:
            self._view._reposition_minimap()
            self.minimap.refresh()

    # ------------------------------------------------- inspector sizing

    def _sync_inspector_width(self):
        if self._splitter.width() <= 0:
            return
        maximised = self.isMaximized() or self.isFullScreen()
        if maximised:
            self._splitter.setStretchFactor(0, 1)
            self._splitter.setStretchFactor(1, 0)
            self._splitter.setSizes(
                [max(1, self._splitter.width() - 400), 400])
        else:
            self._splitter.setStretchFactor(0, 3)
            self._splitter.setStretchFactor(1, 1)

    def changeEvent(self, event):
        """Qt event handler: window state changed (maximised / restored)."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            # A maximise / restore can re-layout the child widgets and can
            # interact badly with a mouse grab or a stuck "closed-hand"
            # cursor.  End any active pan before the layout pass runs.
            self._view._end_pan()
            self._sync_inspector_width()

    def _refresh_note_list(self):
        """Mirror the minimap's drawn set (active + nearest silhouettes
        + path) into the note list.  Beyond this set there is no walkable
        route to offer, so nothing further appears here."""

        if not hasattr(self, "note_list"):
            return
        minimap = self.minimap
        entries = []
        for nid, note, _distance, is_active in minimap.full_component_entries():
            title = note.model.title or tr("Ohne Titel")
            entries.append((nid, title, is_active))
        self.note_list.set_entries(entries, minimap._selected_silhouette)

    def _refresh_path_dim(self):
        """Recompute FlowView dimming based on the minimap's current
        selected silhouette / path."""
        self._scene.reapply_selection_dim()
        self._update_nav_buttons()

    def _on_note_list_selected(self, nid):
        """A name was clicked in the note list — behave like a minimap click."""
        minimap = self.minimap
        note = minimap._notes.get(nid)
        if note is None:
            return
        if nid in minimap._active_ids:
            self.set_root(note)
            return
        # Silhouette: toggle path highlight without re-rooting.
        if minimap._selected_silhouette == nid:
            minimap._selected_silhouette = None
        else:
            minimap._selected_silhouette = nid
            self._scene.clearSelection()
        minimap.refresh()

    def _on_view_moved(self):
        """Called by FlowView on pan/zoom: refresh the mini-map's viewport
        overlay and remember that the user has manually moved the view."""
        self._user_moved = True
        if self.minimap.isVisible():
            self.minimap.refresh_viewport()

    def _on_scene_root_changed(self, note):
        """FlowScene rebuilt because its root changed — refresh the
        minimap and note list so they stay in sync (this is the
        *FlowView → minimap* direction of the bidirectional link)."""
        # _scene.rebuild() already ran; minimap.refresh() will call
        # MiniMap._rebuild() which reads dialog._scene.root_note and
        # dialog._scene.nodes, so the new active set is picked up.
        # It also re-emits minimap.rebuilt, which updates the note
        # list and the path-dim.
        self._record_root(note)
        self._update_nav_buttons()
        self.minimap.refresh()

    def set_root(self, note):
        self._scene.set_root(note)
        self._user_moved = False
        self._view.fit_all()
        self.inspector.set_note(note)
        self.minimap.refresh()

    # ---- slots

    def _rebuild(self):
        self._scene.rebuild()
        if not self._user_moved:
            self._view.fit_all()
        if (self._scene.root_note is None
                or self._scene.root_note.scene() is not self.board_scene):
            self.setWindowTitle(tr("FlowView — Wurzelknoten entfernt"))
            return
        self.minimap.refresh()

    def _refresh_node(self, note):
        self._scene.refresh_node(note)

    def _on_selection_changed(self):
        node = self._scene.selected_node()
        if node is not None:
            self.inspector.set_note(node.note)

    def _on_inspector_jump(self, note):
        """A connection row was double-clicked in the embedded Inspector:
        re-root FlowView on that note."""
        if note is None or note.scene() is not self.board_scene:
            return
        self.set_root(note)

    def _on_inspector_edit(self, note):
        """The 'Open in large editor' button was pressed."""
        if note is None or note.scene() is not self.board_scene:
            return
        self.board_scene.edit_requested.emit(note)

    def _open_current_editor(self):
        """F2: open the big editor for the currently inspected note."""
        note = self.inspector.note
        if note is None or note.scene() is not self.board_scene:
            note = self._scene.root_note
        if note is None or note.scene() is not self.board_scene:
            return
        self.board_scene.edit_requested.emit(note)

    def closeEvent(self, event):
        try:
            self.board_scene.structure_changed.disconnect(self._rebuild)
        except (TypeError, RuntimeError):
            pass
        try:
            self.board_scene.note_content_changed.disconnect(self._refresh_node)
        except (TypeError, RuntimeError):
            pass
        try:
            self._scene.root_changed.disconnect(self._on_scene_root_changed)
        except (TypeError, RuntimeError):
            pass
        self.board_scene._flow_minimap = None
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._view._end_pan()  # ← new line
        if not self._user_moved:
            self._view.fit_all()
        self._view._reposition_minimap()
        self.minimap.refresh()
        self._sync_inspector_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._view._end_pan()  # ← new line
        if not self._user_moved:
            self._view.fit_all()
        self._view._reposition_minimap()
        self.minimap.refresh()
        if self.isMaximized() or self.isFullScreen():
            self._sync_inspector_width()

    def _set_selection_lock(self, locked):
        self._scene._selection_locked = locked

    # ---------------------------------------------------------- path walk

    def _current_path_ids(self):
        """The path from the current root to the selected silhouette, or
        an empty list.  Uses the same BFS as MiniMap so the buttons and
        the highlighted path can never disagree."""
        minimap = self.minimap
        if minimap._selected_silhouette is None:
            return []
        root_note = self._scene.root_note
        if root_note is None:
            return []
        path = minimap._shortest_path(
            self.board_scene, root_note, minimap._selected_silhouette)
        return path or []

    def _path_position(self):
        """Index of the current root on the current path, or -1."""
        path = self._current_path_ids()
        if not path:
            return -1
        root_id = id(self._scene.root_note) if self._scene.root_note else None
        try:
            return path.index(root_id)
        except ValueError:
            return -1

    def _go_prev_on_path(self):
        """The ◀ button.

        If a silhouette is selected, step one hop back along the path.
        Otherwise step back through the root history — this is what
        makes ◀ still useful after the destination is reached (path
        cleared) or when the path was toggled off."""
        if self._selected_silhouette_active():
            self._go_prev_on_path_step()
            return
        self._go_history_back()

    def _go_next_on_path(self):
        """The ▶ button.  Same rule as ◀: path first, history fallback."""
        if self._selected_silhouette_active():
            self._go_next_on_path_step()
            return
        self._go_history_forward()

    def _selected_silhouette_active(self):
        return self.minimap._selected_silhouette is not None


    def _jump_to_path_note(self, nid):
        """Re-root on the note whose Python id is ``nid`` — without
        touching ``_selected_silhouette``, so the path highlight
        recomputes from the new root (or clears, if this was the
        destination)."""
        note = None
        for n in self.board_scene.note_lookup.values():
            if id(n) == nid:
                note = n
                break
        if note is None:
            return
        # Same core as set_root, minus the "user moved" bookkeeping.
        # Re-rooting via the arrows is a *navigation* gesture along the
        # already-selected path, so it must not count as the user having
        # manually panned the view.
        self._scene.set_root(note)
        self._user_moved = False
        self._view.fit_all()
        self.inspector.set_note(note)
        self.minimap.refresh()

    def _update_nav_buttons(self):
        if not hasattr(self, "_btn_prev"):
            return
        if self._selected_silhouette_active():
            path = self._current_path_ids()
            pos = self._path_position()
            can_back = bool(path) and pos > 0
            can_fwd = bool(path) and 0 <= pos < len(path) - 1
        else:
            can_back = self._root_history_index > 0
            can_fwd = self._root_history_index < len(self._root_history) - 1
        self._btn_prev.setEnabled(can_back)
        self._btn_next.setEnabled(can_fwd)

    def _go_prev_on_path_step(self):
        path = self._current_path_ids()
        pos = self._path_position()
        if pos <= 0:
            return
        self._jump_to_path_note(path[pos - 1])

    def _go_next_on_path_step(self):
        path = self._current_path_ids()
        pos = self._path_position()
        if pos < 0 or pos >= len(path) - 1:
            return
        self._jump_to_path_note(path[pos + 1])

    def _go_history_back(self):
        if self._root_history_index <= 0:
            return
        self._root_history_index -= 1
        self._jump_to_history_note(
            self._root_history[self._root_history_index])

    def _go_history_forward(self):
        if self._root_history_index >= len(self._root_history) - 1:
            return
        self._root_history_index += 1
        self._jump_to_history_note(
            self._root_history[self._root_history_index])

    def _jump_to_history_note(self, nid):
        """Re-root on the note whose Python id is ``nid`` without
        recording another history entry."""
        note = None
        for n in self.board_scene.note_lookup.values():
            if id(n) == nid:
                note = n
                break
        if note is None:
            return
        self._scene.set_root(note)
        self._user_moved = False
        self._view.fit_all()
        self.inspector.set_note(note)
        self.minimap.refresh()

    def _record_root(self, note):
        """Push ``note`` onto the root history.

        Consecutive duplicates are collapsed.  Calling this while the
        history is *not* at the end truncates the forward entries
        (standard back/forward semantics)."""
        nid = id(note) if note is not None else None
        if (self._root_history_index >= 0
                and self._root_history[self._root_history_index] == nid):
            return
        del self._root_history[self._root_history_index + 1:]
        self._root_history.append(nid)
        self._root_history_index = len(self._root_history) - 1

    def reset_view(self):
        """Reset zoom, pan, and the 'user moved' flag so future structure
        changes auto-fit again."""
        self._user_moved = False
        self._view.fit_all()

# ------------------------------------------------------------ Inspector factory

def _default_inspector_factory(attachments, note_types=None):
    """Import the real InspectorWidget lazily to avoid a circular import.

    ``note_types`` is the dict the board uses (key -> NoteTypeData); the
    inspector needs it to populate its note-type combo.  When ``None``, the
    inspector opens with an empty combo (only useful for headless tests).
    """
    from inspector import InspectorWidget
    w = InspectorWidget(attachments)
    if note_types:
        w.set_types(note_types)
    return w