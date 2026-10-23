# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Pins: round push-pin heads that sit on a note and carry the threads.

Performance (Optimization.md 1.4): ``paint_pin_head`` renders into a small
``QPixmap`` cache keyed by (colour, selected, highlight, locked), so the
radial gradient is built once per variant instead of once per call.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QPainterPath, QPen, QRadialGradient, QPainter, QPixmap,
)
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from models import DEFAULT_PIN_COLOR
from theme import ACCENT
from i18n import tr, N_

_PIN_CACHE = {}


def _pin_pixmap(color: str, selected: bool, highlight: bool, locked: bool) -> QPixmap:
    """Render a pin head into a QPixmap and cache it."""
    key = (color, selected, highlight, locked)
    pm = _PIN_CACHE.get(key)
    if pm is not None:
        return pm

    size = 24
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    r = QRectF(4, 4, 16, 16)
    base = QColor(color)
    if not base.isValid():
        base = QColor(DEFAULT_PIN_COLOR)

    if highlight:
        p.setPen(QPen(QColor(ACCENT), 3))
        p.setBrush(QColor(108, 156, 255, 60))
        p.drawEllipse(r.adjusted(-4, -4, 4, 4))

    p.setPen(QPen(Qt.PenStyle.NoPen))
    p.setBrush(QColor(0, 0, 0, 80))
    p.drawEllipse(r.translated(2, 2.5))

    grad = QRadialGradient(
        r.center().x() - r.width() * 0.15,
        r.center().y() - r.height() * 0.2,
        r.width() * 0.75,
    )
    grad.setColorAt(0, base.lighter(165))
    grad.setColorAt(1, base.darker(135))
    ring = QPen(QColor("#ffffff"), 2.5) if selected else QPen(base.darker(170), 1)
    p.setBrush(QBrush(grad))
    p.setPen(ring)
    p.drawEllipse(r)

    p.setPen(QPen(Qt.PenStyle.NoPen))
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawEllipse(QRectF(r.left() + 3.5, r.top() + 3, 4.5, 3.5))

    if locked:
        p.setBrush(QColor(0, 0, 0, 190))
        p.drawRoundedRect(
            QRectF(r.center().x() - 2.5, r.center().y() - 1.5, 5, 4.5), 1, 1)
        p.setPen(QPen(QColor(0, 0, 0, 190), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(
            QRectF(r.center().x() - 1.8, r.center().y() - 4.2, 3.6, 4.2),
            0, 180 * 16)

    p.end()
    _PIN_CACHE[key] = pm
    return pm


class PinItem(QGraphicsEllipseItem):
    """Pin auf einer Notiz. Verbinden: Rechtsklick auf den Pin gedrückt halten
    und auf einen anderen Pin ziehen (wird in BoardScene behandelt)."""

    SIZE = 16

    # ---- LOD thresholds (distinct names so they don't collide with
    # ConnectionItem's VISIBLE_* constants, which are on a different class) ----
    LOD_DETAIL_ZOOM = 0.30      # below this zoom, tiny dot (unless selected)
    PIN_VISIBLE_FULL = 60       # <= this many visible pins: full pixmap head
    PIN_VISIBLE_SIMPLE = 300    # <= this many visible pins: filled circle
    PIN_VISIBLE_MINIMAL = 800   # <= this many visible pins: tiny dot
    # Above PIN_VISIBLE_MINIMAL: skipped entirely (unreadable at that density)

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
               "Rechtsklick: Farbe / Löschen"))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not model.locked)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setPos(model.x, model.y)
        self.setZValue(100)

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return self.rect().adjusted(-5, -5, 6, 6)

    def shape(self):
        """Qt: the exact outline used for hit-testing and collisions."""
        path = QPainterPath()
        path.addEllipse(self.rect().adjusted(-3, -3, 3, 3))
        return path

    def itemChange(self, change, value):
        """Qt: called before/after item state changes."""
        C = QGraphicsItem.GraphicsItemChange
        if change == C.ItemPositionChange:
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

    def set_color(self, color: str):
        """Change the pin colour."""
        self.model.color = color
        self.update()

    def set_locked(self, locked: bool):
        """Lock / unlock the pin."""
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

    def paint(self, painter, option, widget=None):
        """Qt: draw the item (LOD tier from visible pin count and zoom).

        Four tiers, chosen by ``scene._visible_pin_count`` (set in
        ``BoardView.paintEvent``) and the current zoom:

            <= PIN_VISIBLE_FULL     full pixmap head (gradient, highlight,
                                    lock glyph, selection ring) — unchanged
            <= PIN_VISIBLE_SIMPLE   single filled circle with 1-px border
            <= PIN_VISIBLE_MINIMAL  single 3-px dot, no border
            >  PIN_VISIBLE_MINIMAL  skipped (too small to read at this
                                    density; same idea as the thread tier
                                    that drops labels above VISIBLE_LABEL)

        The pin's own ``paint`` is what draws it; the pixmap cache in
        ``paint_pin_head`` is only used at full detail, so the simple and
        minimal tiers bypass it entirely (they're cheap QPainter primitives).
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        scene = self.scene()
        visible = (getattr(scene, "_visible_pin_count", 0)
                   if scene is not None else 0)

        selected = self.isSelected()
        base = QColor(self.model.color)
        if not base.isValid():
            base = QColor(DEFAULT_PIN_COLOR)

        # Skip entirely at very high density.
        if visible > self.PIN_VISIBLE_MINIMAL:
            return

        # Minimal tier: tiny dot, no border.  Also used at any zoom below
        # LOD_DETAIL_ZOOM.
        if visible > self.PIN_VISIBLE_SIMPLE or lod < self.LOD_DETAIL_ZOOM:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(base)
            painter.drawEllipse(self.rect().center(), 2, 2)
            return

        # Simple tier: filled circle + 1-px border.  No gradient, no
        # highlight, no lock glyph, no pixmap.
        if visible > self.PIN_VISIBLE_FULL:
            painter.setPen(QPen(base.darker(170), 1))
            painter.setBrush(base)
            painter.drawEllipse(self.rect())
            if selected:
                painter.setPen(QPen(QColor(ACCENT), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(self.rect().adjusted(-2, -2, 2, 2))
            return

        # Full detail — pixmap-cached head.  Unchanged.
        paint_pin_head(
            painter, self.rect(), self.model.color,
            selected=selected, highlight=self.highlight,
            locked=self.model.locked,
        )


def paint_pin_head(painter, r, color, selected=False, highlight=False, locked=False):
    """Draw a push-pin head into rectangle ``r`` (pixmap-cached)."""
    key_color = QColor(color)
    if not key_color.isValid():
        key_color = QColor(DEFAULT_PIN_COLOR)
    pm = _pin_pixmap(key_color.name(), selected, highlight, locked)
    target = QRectF(r.center().x() - 12, r.center().y() - 12, 24, 24)
    painter.drawPixmap(target.toRect(), pm)