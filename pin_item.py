# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Pins: round push-pin heads that sit on a note and carry the threads.

``paint_pin_head`` is a free function because threads repaint the heads.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPen,
    QRadialGradient,
    QPainter,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
)

from models import DEFAULT_PIN_COLOR
from theme import ACCENT
from i18n import tr, N_


class PinItem(QGraphicsEllipseItem):
    """
    Pin auf einer Notiz. Verbinden: Rechtsklick auf den Pin gedrückt halten
    und auf einen anderen Pin ziehen (wird in BoardScene behandelt).
    """

    SIZE = 16

    def __init__(self, model, note):
        """Create a pin for ``model`` as a child of ``note``."""
        s = self.SIZE

        super().__init__(-s / 2, -s / 2, s, s, note)

        self.model = model
        self.note = note

        self.connections = []
        self.highlight = False

        self.setToolTip(
            tr("Rechtsklick + ziehen: Faden zu anderem Pin\n"
            "Rechtsklick: Farbe / Löschen")
        )

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not model.locked)

        self.setPos(model.x, model.y)
        self.setZValue(100)

    # ---------- Geometrie ----------

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return self.rect().adjusted(-5, -5, 6, 6)

    def shape(self):
        """Qt: the exact outline used for hit-testing and collisions."""
        path = QPainterPath()
        path.addEllipse(self.rect().adjusted(-3, -3, 3, 3))
        return path

    def itemChange(self, change, value):

        """Qt: called before/after item state changes (position, selection …)."""
        C = QGraphicsItem.GraphicsItemChange

        if change == C.ItemPositionChange:
            # Pin innerhalb der Notiz halten
            r = self.note.rect()
            return QPointF(
                min(max(value.x(), 0.0), r.width()),
                min(max(value.y(), 0.0), r.height()),
            )

        if change == C.ItemPositionHasChanged:
            pos = self.pos()
            self.model.x = pos.x()
            self.model.y = pos.y()
            self.update_connections()

        return super().itemChange(change, value)

    def update_connections(self):
        """Re-route the threads of this pin."""
        for connection in self.connections:
            connection.update_connection()

    # ---------- Zustand ----------

    def set_color(self, color: str):
        """Change the pin colour."""
        self.model.color = color
        self.update()

    def set_locked(self, locked: bool):
        """Lock / unlock the pin.  A locked pin cannot be dragged inside its
        note, but it still moves together with the note (it is a child item)."""
        self.model.locked = locked
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)
        self.update()

    def set_highlight(self, on: bool):
        """Highlight ring while a thread is dragged over this pin."""
        self.highlight = on
        self.update()

    def remove_connections(self):
        """Alle Fäden an diesem Pin löschen."""

        scene = self.scene()

        for connection in list(self.connections):
            if scene is not None and hasattr(scene, "remove_connection"):
                scene.remove_connection(connection)
            else:
                connection.remove_from_pins()

    # ---------- Painting ----------

    def paint(self, painter, option, widget=None):
        """Qt: draw the item."""
        paint_pin_head(
            painter, self.rect(), self.model.color,
            selected=self.isSelected(), highlight=self.highlight,
            locked=self.model.locked,
        )


def paint_pin_head(painter, r, color, selected=False, highlight=False, locked=False):
    """Draw a push-pin head into rectangle ``r``.

    Shared by :class:`PinItem` and by the threads (which re-draw the pin heads
    on top of themselves, because threads are stacked above the notes)."""

    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    base = QColor(color)
    if not base.isValid():
        base = QColor(DEFAULT_PIN_COLOR)

    # Highlight ring while a thread is dragged towards this pin
    if highlight:
        painter.setPen(QPen(QColor(ACCENT), 3))
        painter.setBrush(QColor(108, 156, 255, 60))
        painter.drawEllipse(r.adjusted(-4, -4, 4, 4))

    # Shadow
    painter.setPen(QPen(Qt.PenStyle.NoPen))
    painter.setBrush(QColor(0, 0, 0, 80))
    painter.drawEllipse(r.translated(2, 2.5))

    # Head with a glossy gradient
    grad = QRadialGradient(
        r.center().x() - r.width() * 0.15,
        r.center().y() - r.height() * 0.2,
        r.width() * 0.75,
    )
    grad.setColorAt(0, base.lighter(165))
    grad.setColorAt(1, base.darker(135))

    ring = QPen(QColor("#ffffff"), 2.5) if selected else QPen(base.darker(170), 1)

    painter.setBrush(QBrush(grad))
    painter.setPen(ring)
    painter.drawEllipse(r)

    # Specular highlight
    painter.setPen(QPen(Qt.PenStyle.NoPen))
    painter.setBrush(QColor(255, 255, 255, 150))
    painter.drawEllipse(QRectF(r.left() + 3.5, r.top() + 3, 4.5, 3.5))

    # A locked pin gets a small dark "keyhole" square in the middle
    if locked:
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRoundedRect(
            QRectF(r.center().x() - 2.5, r.center().y() - 1.5, 5, 4.5), 1, 1)
        painter.setPen(QPen(QColor(0, 0, 0, 190), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(r.center().x() - 1.8, r.center().y() - 4.2, 3.6, 4.2),
                        0, 180 * 16)
