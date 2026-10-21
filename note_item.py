# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""A note on the board, painted like a sticky note (``NoteItem``).

The item owns its pins (child items) and paints title, attributes, a content
preview, tags and small icons (status dot, lock, attachments, comments).
"""

from html import escape

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QTextOption,
    QPolygonF,
)
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsItem

from models import PinData, DEFAULT_NOTE_COLOR, STATUS_INFO
from pin_item import PinItem
from theme import ACCENT, ideal_text_color
from i18n import tr, N_


def _text_option(align=Qt.AlignmentFlag.AlignLeft, wrap=False):
    """QTextOption with alignment and wrap mode (used for painting text)."""
    opt = QTextOption(align)
    opt.setWrapMode(
        QTextOption.WrapMode.WordWrap if wrap
        else QTextOption.WrapMode.NoWrap
    )
    return opt


class NoteItem(QGraphicsRectItem):
    """Notiz im Post-it-Look."""

    MIN_W = 180
    MIN_H = 120
    GRIP = 20
    FOLD = 22
    SHADOW = 10

    def __init__(self, model):
        """Create the item for ``model`` (NoteData)."""
        super().__init__(0, 0, model.width, model.height)

        self.model = model
        self.pins = []

        self._resizing = False
        self._resize_origin = None
        self._orig_size = (0, 0)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not model.locked)
        self.setPos(model.x, model.y)
        self.setZValue(10)

    # ---------- Geometrie ----------

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return self.rect().adjusted(-4, -4, self.SHADOW, self.SHADOW)

    def shape(self):
        """Qt: the exact outline used for hit-testing and collisions."""
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    def itemChange(self, change, value):

        """Qt: called before/after item state changes (position, selection …)."""
        C = QGraphicsItem.GraphicsItemChange

        if change == C.ItemPositionChange:
            scene = self.scene()
            if scene is not None and getattr(scene, "snap_to_grid", False):
                g = 20
                return QPointF(
                    round(value.x() / g) * g,
                    round(value.y() / g) * g,
                )

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            pos = self.pos()
            self.model.x = pos.x()
            self.model.y = pos.y()
            self.update_connections()

        return super().itemChange(change, value)

    def update_connections(self):
        """Re-route all threads attached to this note's pins."""
        for pin in self.pins:
            for connection in pin.connections:
                connection.update_connection()

    def set_locked(self, locked):
        """Lock / unlock the note: a locked note cannot be moved or resized.
        Its pins follow it as usual (they are child items)."""
        self.model.locked = locked
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
        self.unsetCursor()
        self.update()

    def resize_to(self, width, height):

        """Resize the note (minimum size enforced, pins stay inside)."""
        width = max(self.MIN_W, width)
        height = max(self.MIN_H, height)

        self.setRect(0, 0, width, height)

        self.model.width = width
        self.model.height = height

        # Pins innerhalb der Notiz halten
        for pin in self.pins:
            p = pin.pos()
            nx = min(max(p.x(), 0), width)
            ny = min(max(p.y(), 0), height)
            if nx != p.x() or ny != p.y():
                pin.setPos(nx, ny)

        self.update()

    # ---------- Typ ----------

    def type_info(self):
        """NoteTypeData of this note's type (None when unknown)."""
        scene = self.scene()
        types = getattr(scene, "note_types", None) or {}
        return types.get(self.model.note_type)

    # ---------- Pins ----------

    def add_pin(self, x, y):

        """Add a new pin at (x, y) in note coordinates."""
        pin_data = PinData(x=x, y=y)
        self.model.pins.append(pin_data)

        return self.load_pin(pin_data)

    def load_pin(self, pin_data):

        """Create the PinItem for existing PinData and register it."""
        pin = PinItem(pin_data, self)
        self.pins.append(pin)

        scene = self.scene()
        if scene is not None and hasattr(scene, "pin_lookup"):
            scene.pin_lookup[pin_data.id] = pin

        return pin

    def remove_pin(self, pin):

        """Remove a pin and its threads."""
        pin.remove_connections()

        if pin in self.pins:
            self.pins.remove(pin)

        self.model.pins = [
            p for p in self.model.pins if p is not pin.model
        ]

        scene = self.scene()
        if scene is not None:
            scene.pin_lookup.pop(pin.model.id, None)
            scene.removeItem(pin)

    def links(self):
        """Liste (andere Notiz, Fadenbeschriftung) aller Verbindungen."""

        out = []
        for pin in self.pins:
            for c in pin.connections:
                other = c.end_pin if c.start_pin is pin else c.start_pin
                out.append((other.note, c.model.label))
        return out

    def remove_all_connections(self):
        """Remove all threads of all pins."""
        for pin in list(self.pins):
            pin.remove_connections()

    # ---------- Maus ----------

    def _in_grip(self, pos):
        """True when ``pos`` is in the resize corner (never for locked notes)."""
        if self.model.locked:          # locked notes cannot be resized
            return False
        r = self.rect()
        return (
            pos.x() > r.width() - self.GRIP
            and pos.y() > r.height() - self.GRIP
        )

    def tooltip_text(self):
        """Zusammenfassung der Notiz für den Hover-Tooltip."""

        m = self.model
        info = self.type_info()
        label = info.label if info else m.note_type

        lines = [f"<b>{escape(m.title or tr('Ohne Titel'))}</b>  <i>({escape(label)})</i>"]

        for a in m.attributes:
            if a.value.strip():
                lines.append(f"{escape(a.name or '')}: {escape(a.value.strip())}")

        if m.tags:
            lines.append(" ".join(f"#{escape(t)}" for t in m.tags))

        words = len(m.content.split())
        if words:
            lines.append(tr("{n} Wörter", n=words))

        if m.locked:
            lines.append("🔒 " + tr("Gesperrt – Position fixiert"))

        lines.append("<i>" + tr("Doppelklick: Pin setzen · Rechtsklick: Menü") + "</i>")
        return "<br>".join(lines)

    def hoverEnterEvent(self, event):
        """Qt event handler: the pointer entered the item."""
        self.setToolTip(self.tooltip_text())
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        """Qt event handler: the pointer moves over the item."""
        if self._in_grip(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            self.setToolTip(tr("Ziehen: Größe ändern"))
        else:
            self.unsetCursor()
            self.setToolTip(self.tooltip_text())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        """Qt event handler: the pointer left the item."""
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):

        """Qt event handler: a mouse button was pressed."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._in_grip(event.pos())
        ):
            self._resizing = True
            self._resize_origin = event.pos()
            self._orig_size = (self.rect().width(), self.rect().height())
            event.accept()
            return

        scene = self.scene()
        if scene is not None and hasattr(scene, "bring_to_front"):
            scene.bring_to_front(self)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):

        """Qt event handler: the mouse moved."""
        if self._resizing:
            d = event.pos() - self._resize_origin
            self.resize_to(
                self._orig_size[0] + d.x(),
                self._orig_size[1] + d.y(),
            )
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):

        """Qt event handler: a mouse button was released."""
        if self._resizing:
            self._resizing = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):

        """Qt event handler: double click."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._in_grip(event.pos())
        ):
            self.add_pin(event.pos().x(), event.pos().y())
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    # ---------- Painting ----------

    @staticmethod
    def _draw_lock(painter, x, y, color):
        """Tiny padlock: shackle arc above a rounded body."""
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 1.5))
        painter.drawArc(QRectF(x + 1.5, y, 7, 8), 0, 180 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x, y + 4.5, 10, 7.5), 1.5, 1.5)
        painter.restore()

    def paint(self, painter, option, widget=None):

        """Qt: draw the item."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = self.rect()
        w, h = rect.width(), rect.height()
        fold = self.FOLD

        base = QColor(self.model.color)
        if not base.isValid():
            base = QColor(DEFAULT_NOTE_COLOR)

        text_color = ideal_text_color(base)
        muted = QColor(text_color)
        muted.setAlpha(150)

        # Papierform mit abgeknickter Ecke unten rechts
        paper = QPainterPath()
        paper.moveTo(0, 0)
        paper.lineTo(w, 0)
        paper.lineTo(w, h - fold)
        paper.lineTo(w - fold, h)
        paper.lineTo(0, h)
        paper.closeSubpath()

        # weicher Schatten
        for offset, alpha in ((7, 16), (5, 24), (3, 34)):
            painter.fillPath(
                paper.translated(offset, offset),
                QColor(0, 0, 0, alpha)
            )

        # Papier
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0, base.lighter(108))
        gradient.setColorAt(1, base.darker(106))
        painter.fillPath(paper, gradient)

        # Klebestreifen-Kopfbereich
        painter.save()
        painter.setClipPath(paper)
        painter.fillRect(QRectF(0, 0, w, 48), QColor(0, 0, 0, 16))
        painter.restore()

        # Umgeknickte Ecke
        corner = QPolygonF()
        for x, y in ((w - fold, h), (w, h - fold), (w - fold, h - fold)):
            corner.append(QPointF(x, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base.darker(128))
        painter.drawPolygon(corner)

        # Rand
        if self.isSelected():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ACCENT), 2.5))
            painter.drawPath(paper)

        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 45), 1))
            painter.drawPath(paper)

        pad = 14
        inner_w = w - pad * 2

        # --- Typ-Badge ---
        info = self.type_info()
        label = info.label if info else self.model.note_type

        badge_font = QFont()
        badge_font.setPointSizeF(7)
        badge_font.setBold(True)
        badge_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)

        painter.setFont(badge_font)
        painter.setPen(muted)
        painter.drawText(
            QRectF(pad, 9, inner_w, 12),
            label.upper(),
            _text_option()
        )

        # --- Titel ---
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)

        fm = QFontMetrics(title_font)
        title = fm.elidedText(
            self.model.title or tr("Ohne Titel"),
            Qt.TextElideMode.ElideRight,
            int(inner_w)
        )

        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(
            QRectF(pad, 22, inner_w, 24),
            title,
            _text_option()
        )

        # --- Icons top right: status dot, lock, attachments, comments ---
        # (laid out right-to-left from the edge of the note)
        ix = w - 14

        status = STATUS_INFO.get(self.model.status)
        if status:
            ix -= 11
            painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
            painter.setBrush(QColor(status[1]))
            painter.drawEllipse(QRectF(ix, 10, 11, 11))
            ix -= 6

        if self.model.locked:
            ix -= 10
            self._draw_lock(painter, ix, 9, text_color)
            ix -= 6

        icon_font = QFont()
        icon_font.setPointSizeF(7.5)
        icon_fm = QFontMetrics(icon_font)
        painter.setFont(icon_font)
        painter.setPen(muted)
        for glyph, count in (("📎", len(self.model.attachments)),
                             ("💬", len(self.model.comments))):
            if count:
                text = f"{glyph}{count}"
                tw = icon_fm.horizontalAdvance(text) + 2
                ix -= tw
                painter.drawText(QRectF(ix, 8, tw + 2, 14), text, _text_option())
                ix -= 5

        # --- Layout-Grenzen ---
        tags = [t for t in self.model.tags if t]
        content_bottom = h - (34 if tags else 14)
        y = 56

        # --- Attribute ---
        attr_font = QFont()
        attr_font.setPointSizeF(8.5)
        attr_fm = QFontMetrics(attr_font)
        attr_bold = QFont(attr_font)
        attr_bold.setBold(True)
        attr_bold_fm = QFontMetrics(attr_bold)

        attrs = [a for a in self.model.attributes if a.value.strip()]
        drawn_attrs = 0

        for a in attrs:
            if y + 15 > content_bottom:
                break

            name = f"{a.name}: " if a.name else ""
            name_w = attr_bold_fm.horizontalAdvance(name)

            if name:
                painter.setFont(attr_bold)
                painter.setPen(muted)
                painter.drawText(
                    QRectF(pad, y, name_w + 2, 15),
                    name,
                    _text_option()
                )

            value = attr_fm.elidedText(
                a.value.replace("\n", " "),
                Qt.TextElideMode.ElideRight,
                max(10, int(inner_w - name_w))
            )

            painter.setFont(attr_font)
            painter.setPen(text_color)
            painter.drawText(
                QRectF(pad + name_w, y, inner_w - name_w, 15),
                value,
                _text_option()
            )

            y += 15
            drawn_attrs += 1

        if drawn_attrs:
            y += 5

        # --- Inhalt ---
        if self.model.content and content_bottom - y > 14:
            body_font = QFont()
            body_font.setPointSizeF(9)

            painter.save()
            painter.setClipRect(
                QRectF(pad, y, inner_w, content_bottom - y)
            )
            painter.setFont(body_font)

            body_color = QColor(text_color)
            body_color.setAlpha(225)
            painter.setPen(body_color)

            painter.drawText(
                QRectF(pad, y, inner_w, content_bottom - y),
                self.model.content,
                _text_option(wrap=True)
            )
            painter.restore()

        # --- Tags ---
        if tags:
            tag_font = QFont()
            tag_font.setPointSizeF(7.5)
            tag_fm = QFontMetrics(tag_font)

            painter.setFont(tag_font)

            x = pad
            for tag in tags:
                text = f"#{tag}"
                tw = tag_fm.horizontalAdvance(text) + 14

                if x + tw > w - pad:
                    break

                chip = QRectF(x, h - 28, tw, 17)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 38))
                painter.drawRoundedRect(chip, 8.5, 8.5)

                painter.setPen(text_color)
                painter.drawText(
                    chip,
                    text,
                    _text_option(Qt.AlignmentFlag.AlignCenter)
                )

                x += tw + 5
