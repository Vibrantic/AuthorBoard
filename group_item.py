# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Group frames: a titled, coloured, resizable frame behind notes.

Membership is geometric: a note belongs to the topmost frame that contains
its centre.  Only the header, the border band and the resize grip are
hit-testable, so clicks inside the frame reach the board (rubber band,
double-click = new note).  Moving is done through ``BoardScene.group_block``
and ``BoardScene.move_block``; this item deliberately never sets a cursor.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QTextOption,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from i18n import tr
from models import DEFAULT_GROUP_COLOR
from theme import ACCENT

HEADER_H = 34
GRIP = 20
BORDER_HIT = 8


class GroupItem(QGraphicsRectItem):
    """A group frame (see module docstring)."""

    MIN_W = 200
    MIN_H = 120

    def __init__(self, model):
        """Create the item for ``model`` (GroupData)."""
        super().__init__(0, 0, model.width, model.height)
        self.model = model
        self._mode = None            # None / "move" / "resize"
        self._press_scene = None
        self._block = []
        self._orig_size = (model.width, model.height)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(model.x, model.y)
        self.setZValue(-1000)
        self.setToolTip(tr("Ziehen: Gruppe samt Notizen verschieben\n"
                           "Doppelklick: umbenennen\nRechtsklick: Menü"))

    # ---------- geometry ----------

    def scene_rect(self):
        """The frame rectangle in scene coordinates."""
        p = self.pos()
        r = self.rect()
        return QRectF(p.x(), p.y(), r.width(), r.height())

    def boundingRect(self):
        """Qt: the area this item may paint into."""
        return self.rect().adjusted(-3, -3, 3, 3)

    def shape(self):
        """Hit area: header, border band and grip.  The inside is click-through."""
        r = self.rect()
        b = BORDER_HIT
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.WindingFill)
        path.addRect(QRectF(r.left(), r.top(), r.width(), HEADER_H))
        path.addRect(QRectF(r.left(), r.bottom() - b, r.width(), b))
        path.addRect(QRectF(r.left(), r.top(), b, r.height()))
        path.addRect(QRectF(r.right() - b, r.top(), b, r.height()))
        path.addRect(QRectF(r.right() - GRIP, r.bottom() - GRIP, GRIP, GRIP))
        return path

    def _in_grip(self, pos):
        """True in the resize corner (never when locked)."""
        if self.model.locked:
            return False
        r = self.rect()
        return pos.x() > r.width() - GRIP and pos.y() > r.height() - GRIP

    def itemChange(self, change, value):
        """Qt: keep the model position in sync and refresh badges."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            p = self.pos()
            self.model.x, self.model.y = p.x(), p.y()
        return super().itemChange(change, value)

    # ---------- state ----------

    def set_title(self, text):
        """Change the title."""
        self.model.title = text
        self.update()

    def set_color(self, color):
        """Change the frame colour."""
        self.model.color = color
        self.update()

    def set_locked(self, locked):
        """Lock / unlock (locked frames can be neither moved nor resized)."""
        self.model.locked = locked
        self.update()

    def resize_to(self, width, height):
        """Resize the frame (minimum size enforced)."""
        width = max(self.MIN_W, width)
        height = max(self.MIN_H, height)
        self.setRect(0, 0, width, height)
        self.model.width = width
        self.model.height = height

    # ---------- mouse ----------

    def mousePressEvent(self, event):
        """Qt: select, then start moving or resizing."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        super().mousePressEvent(event)           # selection handling
        self._mode = None
        if not self.model.locked:
            self._press_scene = event.scenePos()
            if self._in_grip(event.pos()):
                self._mode = "resize"
                self._orig_size = (self.rect().width(), self.rect().height())
            else:
                self._mode = "move"
                self._block = self.scene().group_block(self)
        event.accept()

    def mouseMoveEvent(self, event):
        """Qt: drag."""
        if self._mode is None:
            super().mouseMoveEvent(event)
            return
        # A release that went elsewhere (dialog, menu): stop right away.
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self._mode = None
            self._block = []
            return
        d = event.scenePos() - self._press_scene
        if self._mode == "resize":
            self.resize_to(self._orig_size[0] + d.x(), self._orig_size[1] + d.y())
        else:
            self.scene().move_block(self._block, d)
        event.accept()

    def mouseReleaseEvent(self, event):
        """Qt: end the drag and refresh ordering badges on all groups."""
        was_moving = self._mode is not None
        self._mode = None
        self._block = []
        super().mouseReleaseEvent(event)
        if was_moving:
            scene = self.scene()
            if scene is not None:
                for g in scene.group_lookup.values():
                    g.update()

    def mouseDoubleClickEvent(self, event):
        """Qt: double-click renames."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._mode = None
            self._block = []
            scene = self.scene()
            if scene is not None:
                scene.rename_group(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ---------- painting ----------

    # ---------- painting ----------

    def paint(self, painter, option, widget=None):
        """Qt: draw the frame."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect()
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        base = QColor(self.model.color)
        if not base.isValid():
            base = QColor(DEFAULT_GROUP_COLOR)

        fill = QColor(base)
        fill.setAlpha(34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(r, 8, 8)

        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        painter.save()
        painter.setClipPath(clip)
        head = QColor(base)
        head.setAlpha(120)
        painter.fillRect(QRectF(r.left(), r.top(), r.width(), HEADER_H), head)
        painter.restore()

        edge = QColor(base)
        edge.setAlpha(200)
        sel = self.isSelected()
        painter.setPen(QPen(QColor(ACCENT) if sel else edge, 2.5 if sel else 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r, 8, 8)

        if lod >= 0.12:
            font = QFont()
            font.setPointSizeF(11)
            font.setBold(True)
            painter.setFont(font)
            title = ("🔒 " if self.model.locked else "") + self.model.title
            text = QFontMetrics(font).elidedText(
                title, Qt.TextElideMode.ElideRight, int(r.width() - 24))
            painter.setPen(QColor("#f1f1f4"))
            painter.drawText(
                QRectF(12, 0, r.width() - 24, HEADER_H), text,
                QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft))

        if lod >= 0.3 and not self.model.locked:
            painter.setPen(QPen(edge, 1.5))
            x, y = r.right() - 6, r.bottom() - 6
            painter.drawLine(QPointF(x - 10, y), QPointF(x, y - 10))
            painter.drawLine(QPointF(x - 5, y), QPointF(x, y - 5))

        # NEW: ordering index badge for nested groups
        if lod >= 0.15:
            self._paint_index_badge(painter, lod)

    def _paint_index_badge(self, painter, lod):
        """Draw the ordering index (e.g. ``1.2.3``) of a nested group
        in the bottom-left corner.

        Top-level groups get no badge — they have no parent to be ordered
        against. The path is computed live from the scene's geometry, so
        moving a group updates the number on the next paint.
        """
        scene = self.scene()
        if scene is None or not hasattr(scene, "_group_index_path"):
            return
        path = scene._group_index_path(self)
        if not path:
            return

        font = QFont()
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text = ".".join(str(p) for p in path)
        tw = fm.horizontalAdvance(text) + 12
        th = 18

        r = self.rect()
        # Bottom-left corner, inside the border
        rect = QRectF(r.left() + 6, r.bottom() - th - 6, tw, th)

        bg = QColor(0, 0, 0, 140)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 5, 5)

        painter.setPen(QColor("#e6e6ea"))
        painter.drawText(rect, text,
                         QTextOption(Qt.AlignmentFlag.AlignCenter))