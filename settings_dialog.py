# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Settings window (Edit -> Settings).

Tabs
----
* **General**            spell checking, focus mode, autosave, user dictionary
* **Note types - book**  custom note types that exist only in the open notebook
* **Note types - global** custom note types available in *every* notebook

The dialog only collects values; :meth:`main.MainWindow.open_settings` applies
them.  :class:`NoteTypesEditor` is the reusable list + form used by both note
type tabs.
"""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from models import NoteTypeData
from settings import GLOBAL_PREFIX, settings
from spellcheck import LANGUAGES, engine
from theme import CUSTOM_TYPE_COLORS, color_icon


class NoteTypesEditor(QWidget):
    """Edit a list of :class:`NoteTypeData` (label, colour, suggested attributes).

    ``prefix`` is put in front of the key of newly created types
    (``custom_`` for book types, ``global_`` for global ones).  ``in_use`` maps
    a type key to the number of notes that use it - such types cannot be removed.
    ``reserved`` are keys/labels that must not be reused (e.g. built-in types).
    """

    def __init__(self, types, prefix, in_use=None, reserved_labels=(), parent=None):
        """Build the list + form for ``types``."""
        super().__init__(parent)
        self.prefix = prefix
        self.in_use = in_use or {}
        self.reserved = {l.lower() for l in reserved_labels}
        # work on copies so Cancel leaves everything untouched
        self._types = [NoteTypeData(t.key, t.label, t.color, list(t.attributes)) for t in types]
        self._loading = False

        layout = QHBoxLayout(self)

        # left: list + add/remove
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setToolTip(tr("Eigene Notizarten – Auswahl zum Bearbeiten"))
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.add_btn = QPushButton(tr("＋ Notizart"))
        self.remove_btn = QPushButton(tr("Entfernen"))
        self.add_btn.setToolTip(tr("Neue Notizart anlegen"))
        self.remove_btn.setToolTip(tr("Ausgewählte Notizart löschen (nur wenn keine Notiz sie benutzt)"))
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        left.addLayout(row)
        layout.addLayout(left, 1)

        # right: form
        form = QFormLayout()
        self.label_edit = QLineEdit()
        self.label_edit.setToolTip(tr("Name der Notizart, wie er im Suchmenü erscheint"))
        self.color_btn = QPushButton(tr("Farbe"))
        self.color_btn.setToolTip(tr("Standardfarbe der Notizen dieser Art"))
        self.attr_edit = QLineEdit()
        self.attr_edit.setPlaceholderText(tr("z. B. Alter, Rolle, Beruf"))
        self.attr_edit.setToolTip(tr("Attribute, die neue Notizen dieser Art automatisch bekommen (mit Komma trennen)"))
        form.addRow(tr("Name"), self.label_edit)
        form.addRow(tr("Farbe"), self.color_btn)
        form.addRow(tr("Attribute"), self.attr_edit)
        self.info = QLabel("")
        self.info.setObjectName("Hint")
        self.info.setWordWrap(True)
        form.addRow("", self.info)
        right = QWidget()
        right.setLayout(form)
        layout.addWidget(right, 1)
        self._right = right

        self.list.currentRowChanged.connect(self._select)
        self.add_btn.clicked.connect(self._add)
        self.remove_btn.clicked.connect(self._remove)
        self.label_edit.textChanged.connect(self._edited)
        self.attr_edit.textChanged.connect(self._edited)
        self.color_btn.clicked.connect(self._pick_color)

        self._refill()

    # ------------------------------------------------------------------ data

    def types(self):
        """The edited list (labels trimmed, empty ones dropped)."""
        return [t for t in self._types if t.label.strip()]

    def _refill(self, select=0):
        """Refill the list and select row ``select``."""
        self.list.blockSignals(True)
        self.list.clear()
        for t in self._types:
            self.list.addItem(QListWidgetItem(color_icon(t.color), t.label or tr("(ohne Namen)")))
        self.list.blockSignals(False)
        if self._types:
            self.list.setCurrentRow(max(0, min(select, len(self._types) - 1)))
        self._select(self.list.currentRow())

    def _current(self):
        """The note type selected in the list (None if none)."""
        row = self.list.currentRow()
        return self._types[row] if 0 <= row < len(self._types) else None

    def _select(self, _row):
        """A row was selected: show its values in the form."""
        t = self._current()
        self._right.setEnabled(t is not None)
        self._loading = True
        self.label_edit.setText(t.label if t else "")
        self.attr_edit.setText(", ".join(t.attributes) if t else "")
        if t:
            self.color_btn.setIcon(color_icon(t.color, 16))
            n = self.in_use.get(t.key, 0)
            self.info.setText(tr("{n} Notizen verwenden diese Art.", n=n) if n else "")
        self._loading = False

    def _edited(self, *_):
        """A form field changed: copy it into the selected type."""
        t = self._current()
        if t is None or self._loading:
            return
        t.label = self.label_edit.text()
        t.attributes = [a.strip() for a in self.attr_edit.text().split(",") if a.strip()]
        item = self.list.currentItem()
        if item:
            item.setText(t.label or tr("(ohne Namen)"))

    def _pick_color(self):
        """Choose the type's colour."""
        t = self._current()
        if t is None:
            return
        c = QColorDialog.getColor(QColor(t.color), self, tr("Farbe wählen"))
        if c.isValid():
            t.color = c.name()
            self.color_btn.setIcon(color_icon(t.color, 16))
            item = self.list.currentItem()
            if item:
                item.setIcon(color_icon(t.color))

    def _unique_key(self, label):
        """A key based on the label that is not used yet."""
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "type"
        key, n = f"{self.prefix}{slug}", 2
        taken = {t.key for t in self._types}
        while key in taken:
            key, n = f"{self.prefix}{slug}_{n}", n + 1
        return key

    def _add(self):
        """Add a new note type with a free default name."""
        base, n = tr("Neue Notizart"), 1
        labels = {t.label.lower() for t in self._types} | self.reserved
        label = base
        while label.lower() in labels:
            n += 1
            label = f"{base} {n}"
        color = CUSTOM_TYPE_COLORS[len(self._types) % len(CUSTOM_TYPE_COLORS)]
        self._types.append(NoteTypeData(self._unique_key(label), label, color, []))
        self._refill(select=len(self._types) - 1)
        self.label_edit.setFocus()
        self.label_edit.selectAll()

    def _remove(self):
        """Remove the selected type unless notes still use it."""
        t = self._current()
        if t is None:
            return
        if self.in_use.get(t.key):
            QMessageBox.information(
                self, tr("Notizart in Benutzung"),
                tr("„{label}“ wird noch von {n} Notizen verwendet.\n"
                   "Ändere zuerst deren Notizart.", label=t.label, n=self.in_use[t.key]))
            return
        row = self.list.currentRow()
        del self._types[row]
        self._refill(select=row)


class SettingsDialog(QDialog):
    """Application settings (see module docstring)."""

    def __init__(self, book_types, global_types, usage, builtin_labels, book_open, parent=None):
        """Build the tabs (General, book types, global types)."""
        super().__init__(parent)
        self.setWindowTitle(tr("Einstellungen"))
        self.resize(760, 520)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ------------------------------------------------------- General
        general = QWidget()
        form = QFormLayout(general)

        self.spell_check = QCheckBox(tr("Rechtschreibung prüfen (rote Wellenlinie)"))
        self.spell_check.setChecked(bool(settings.get("spell_enabled")))
        self.spell_combo = QComboBox()
        self.spell_combo.addItem(tr("Automatisch (Sprache der Oberfläche)"), "auto")
        for code, name in LANGUAGES.items():
            self.spell_combo.addItem(name, code)
        self.spell_combo.setCurrentIndex(max(self.spell_combo.findData(settings.get("spell_language")), 0))
        if not engine.available():
            self.spell_check.setEnabled(False)
            self.spell_combo.setEnabled(False)
            note = QLabel(tr("Nicht verfügbar – installiere das Paket mit:  pip install pyspellchecker"))
            note.setObjectName("Hint")
            form.addRow("", note)
        self.spell_check.setToolTip(tr("Unterstreicht unbekannte Wörter im Inspector und im großen Editor"))
        self.spell_combo.setToolTip(tr("Wörterbuch für die Rechtschreibprüfung"))
        form.addRow(self.spell_check)
        form.addRow(tr("Wörterbuch"), self.spell_combo)

        self.focus_check = QCheckBox(tr("Fokus-Modus: nicht verbundene Notizen ausgrauen"))
        self.focus_check.setChecked(bool(settings.get("focus_mode")))
        self.focus_check.setToolTip(tr("Zeigt bei ausgewählter Notiz nur sie selbst und ihre verbundenen Notizen und Fäden"))
        form.addRow(self.focus_check)

        self.autosave_spin = QSpinBox()
        self.autosave_spin.setRange(1, 60)
        self.autosave_spin.setSuffix(tr(" Min."))
        self.autosave_spin.setValue(int(settings.get("autosave_minutes") or 2))
        self.autosave_spin.setToolTip(tr("Wie oft eine Wiederherstellungs-Sicherung geschrieben wird"))
        form.addRow(tr("Automatische Sicherung"), self.autosave_spin)

        # user dictionary
        self.words = QListWidget()
        self.words.setMaximumHeight(110)
        for w in sorted(settings.get("user_words"), key=str.lower):
            self.words.addItem(w)
        self.words.setToolTip(tr("Wörter, die du dem Wörterbuch hinzugefügt hast"))
        remove = QPushButton(tr("Wort entfernen"))
        remove.clicked.connect(lambda: [self.words.takeItem(self.words.row(i)) for i in self.words.selectedItems()])
        form.addRow(tr("Eigenes Wörterbuch"), self.words)
        form.addRow("", remove)
        tabs.addTab(general, tr("Allgemein"))

        # ------------------------------------------------- Book note types
        reserved = list(builtin_labels)
        book = QWidget()
        bl = QVBoxLayout(book)
        if book_open:
            bl.addWidget(QLabel(tr("Diese Notizarten gibt es nur im geöffneten Notizbuch.")))
            self.book_editor = NoteTypesEditor(book_types, "custom_", usage, reserved)
            bl.addWidget(self.book_editor)
        else:
            self.book_editor = None
            bl.addWidget(QLabel(tr("Öffne ein Notizbuch, um dessen eigene Notizarten zu bearbeiten.")))
            bl.addStretch(1)
        tabs.addTab(book, tr("Notizarten – dieses Buch"))

        # ------------------------------------------------ Global note types
        glob = QWidget()
        gl = QVBoxLayout(glob)
        gl.addWidget(QLabel(tr("Diese Notizarten stehen in allen Notizbüchern zur Verfügung.")))
        self.global_editor = NoteTypesEditor(global_types, GLOBAL_PREFIX, usage, reserved)
        gl.addWidget(self.global_editor)
        tabs.addTab(glob, tr("Notizarten – alle Bücher"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Übernehmen"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------- results

    def apply_general(self):
        """Write the General tab into the settings store."""
        settings.set("spell_enabled", self.spell_check.isChecked(), save=False)
        settings.set("spell_language", self.spell_combo.currentData(), save=False)
        settings.set("focus_mode", self.focus_check.isChecked(), save=False)
        settings.set("autosave_minutes", self.autosave_spin.value(), save=False)
        settings.set("user_words", [self.words.item(i).text() for i in range(self.words.count())], save=False)
        settings.save()

    def book_types(self):
        """Edited book note types (None when no book is open)."""
        return self.book_editor.types() if self.book_editor else None

    def global_types(self):
        """Edited global note types."""
        return self.global_editor.types()
