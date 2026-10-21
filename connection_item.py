# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Threads: the visual connection between two pins.

A thread is a ``QGraphicsPathItem`` drawn above all notes.  Where it crosses a
note it is painted at reduced opacity; the pin heads are repainted on top.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPainter,
    QTextOption,
)
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem

from models import DEFAULT_THREAD_COLOR
from note_item import NoteItem
from pin_item import PinItem, paint_pin_head
from i18n import tr, N_


class ConnectionItem(QGraphicsPathItem):
    """
    A thread between two pins (it sags slightly), optionally with a label.

    Stacking: threads are drawn **above** the notes (z = THREAD_Z).  Where a
    thread crosses a note it is drawn at half opacity so the note text stays
    readable.  Because the thread would also cover the pin heads at its ends,
    the pin heads are painted again on top of the thread.
    """

    THREAD_Z = 100_000          # above every note (notes count up from 10)
    OVER_NOTE_OPACITY = 0.5     # visibility of the thread where it crosses a note

    def __init__(self, model, start_pin, end_pin):
        """Create the thread between two pins."""
        super().__init__()

        self.model = model

        self.start_pin = start_pin
        self.end_pin = end_pin

        self.setZValue(self.THREAD_Z)

        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            True
        )

        # Nur für Bounding-Rect/Trefferfläche (12px breit, unsichtbar);
        # gezeichnet wird in paint().
        self.setPen(QPen(QColor(0, 0, 0, 0), 22))

        self.setToolTip(tr("Rechtsklick: Farbe / Beschriftung / Löschen"))

        self.update_connection()

    # ---------- Zustand ----------

    def set_color(self, color: str):
        """Change the thread colour."""
        self.model.color = color
        self.update()

    def set_label(self, text: str):
        """Set / clear the text shown on the thread."""
        self.prepareGeometryChange()
        self.model.label = text.strip()
        self.update()

    def update_connection(self):
        """Faden neu berechnen, wenn sich ein Pin bewegt."""

        start = self.start_pin.scenePos()
        end = self.end_pin.scenePos()

        self.setPath(thread_path(start, end))

    # ---------- Beschriftung ----------

    @staticmethod
    def _label_font():
        """Font of the label."""
        font = QFont()
        font.setPointSizeF(8.5)
        font.setBold(True)
        return font

    def _label_rect(self):

        """Rectangle of the label at the middle of the thread (null if no label)."""
        if not self.model.label:
            return QRectF()

        fm = QFontMetrics(self._label_font())
        w = fm.horizontalAdvance(self.model.label) + 18
        h = 20

        mid = self.path().pointAtPercent(0.5)
        return QRectF(mid.x() - w / 2, mid.y() - h / 2, w, h)

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        r = super().boundingRect()
        lr = self._label_rect()
        return r.united(lr.adjusted(-3, -3, 3, 3)) if not lr.isNull() else r

    def shape(self):
        """Hit area: a 9 px wide band around the path (plus the label), but
        *without* small discs around the two pins so the pins stay clickable
        even though the thread lies above them."""
        stroker = QPainterPathStroker()
        stroker.setWidth(9)
        p = stroker.createStroke(self.path())

        for pin in (self.start_pin, self.end_pin):
            hole = QPainterPath()
            c = pin.scenePos()
            hole.addEllipse(c, 11, 11)
            p = p.subtracted(hole)

        lr = self._label_rect()
        if not lr.isNull():
            p.addRect(lr)
        return p

    # ---------- Painting ----------

    def _notes_under_thread(self):
        """Union of the rectangles of all notes that the thread's bounds touch.

        The connection item sits at the scene origin, so scene coordinates are
        also item coordinates."""
        clip = QPainterPath()
        scene = self.scene()
        if scene is None:
            return clip
        for item in scene.items(self.sceneBoundingRect()):
            if isinstance(item, NoteItem):
                clip.addRect(item.mapRectToScene(item.rect()))
        return clip

    def _draw_thread(self, painter, path, color):
        """Glow (if selected), shadow and the thread itself."""
        if self.isSelected():
            painter.setPen(
                QPen(QColor(108, 156, 255, 110), 9,
                     Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.drawPath(path)

        painter.save()
        painter.translate(2, 4)
        painter.setPen(
            QPen(QColor(0, 0, 0, 80), 3.5,
                 Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawPath(path)
        painter.restore()

        painter.setPen(
            QPen(color, 3, Qt.PenStyle.SolidLine,
                 Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawPath(path)

    def paint(self, painter, option, widget=None):

        """Qt: draw the item."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        path = self.path()

        color = QColor(self.model.color)
        if not color.isValid():
            color = QColor(DEFAULT_THREAD_COLOR)

        over_notes = self._notes_under_thread()

        if over_notes.isEmpty():
            self._draw_thread(painter, path, color)
        else:
            # Pass 1: full strength outside the notes
            outside = QPainterPath()
            outside.addRect(self.boundingRect())
            outside = outside.subtracted(over_notes)

            painter.save()
            painter.setClipPath(outside, Qt.ClipOperation.IntersectClip)
            self._draw_thread(painter, path, color)
            painter.restore()

            # Pass 2: reduced opacity where the thread lies over a note
            painter.save()
            painter.setClipPath(over_notes, Qt.ClipOperation.IntersectClip)
            painter.setOpacity(painter.opacity() * self.OVER_NOTE_OPACITY)
            self._draw_thread(painter, path, color)
            painter.restore()

        # Re-draw the two pin heads on top of the thread
        for pin in (self.start_pin, self.end_pin):
            c = pin.scenePos()
            half = PinItem.SIZE / 2
            paint_pin_head(
                painter, QRectF(c.x() - half, c.y() - half, PinItem.SIZE, PinItem.SIZE),
                pin.model.color, selected=pin.isSelected(), highlight=pin.highlight,
                locked=pin.model.locked,
            )

        lr = self._label_rect()
        if not lr.isNull():
            painter.setBrush(QColor(30, 31, 36, 235))
            painter.setPen(QPen(color, 1.5))
            painter.drawRoundedRect(lr, 9, 9)

            painter.setFont(self._label_font())
            painter.setPen(QColor("#e6e6ea"))
            painter.drawText(
                lr, self.model.label,
                QTextOption(Qt.AlignmentFlag.AlignCenter)
            )

    def remove_from_pins(self):
        """Vor dem Löschen aus den Pins austragen."""

        if self in self.start_pin.connections:
            self.start_pin.connections.remove(self)

        if self in self.end_pin.connections:
            self.end_pin.connections.remove(self)


def thread_path(start: QPointF, end: QPointF) -> QPainterPath:
    """Durchhängender Faden (Bezier)."""

    dx = end.x() - start.x()
    dy = end.y() - start.y()

    sag = min(math.hypot(dx, dy) * 0.18, 120.0)

    path = QPainterPath()
    path.moveTo(start)
    path.cubicTo(
        QPointF(start.x() + dx * 0.33, start.y() + dy * 0.33 + sag),
        QPointF(start.x() + dx * 0.66, start.y() + dy * 0.66 + sag),
        end,
    )
    return path
