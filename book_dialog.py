# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Dialog to create/edit the information of a notebook (title, author, genre,
category, colour, word goal, deadline, description and custom fields).
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models import AttributeData
from theme import color_icon
from i18n import tr, N_


class BookInfoDialog(QDialog):
    """Name und eigene Informationen eines Notizbuchs."""

    def __init__(self, book, categories, parent=None, creating=False):
        """Build the form for ``book``; ``creating`` switches the title/button texts."""
        super().__init__(parent)

        self.setWindowTitle(tr("Neues Notizbuch") if creating else tr("Notizbuch-Info"))
        self.resize(520, 640)

        self._color = book.color

        form = QFormLayout()
        form.setSpacing(10)

        self.title_edit = QLineEdit(book.title)
        self.title_edit.setPlaceholderText(tr("Titel des Notizbuchs …"))
        form.addRow(tr("Titel"), self.title_edit)

        self.author_edit = QLineEdit(book.author)
        form.addRow(tr("Autor / Autorin"), self.author_edit)

        self.genre_edit = QLineEdit(book.genre)
        self.genre_edit.setPlaceholderText(tr("z. B. Fantasy, Krimi, Roman"))
        form.addRow(tr("Genre"), self.genre_edit)

        self.category_combo = QComboBox()
        for c in categories:
            self.category_combo.addItem(c.name, c.id)
        idx = self.category_combo.findData(book.category_id)
        self.category_combo.setCurrentIndex(max(idx, 0))
        form.addRow(tr("Kategorie"), self.category_combo)

        self.color_button = QPushButton(tr("Buchfarbe"))
        self.color_button.setIcon(color_icon(self._color, 16))
        self.color_button.clicked.connect(self.pick_color)
        form.addRow(tr("Farbe"), self.color_button)

        self.target_spin = QSpinBox()
        self.target_spin.setRange(0, 5_000_000)
        self.target_spin.setSingleStep(1000)
        self.target_spin.setSuffix(tr(" Wörter"))
        self.target_spin.setSpecialValueText(tr("kein Ziel"))
        self.target_spin.setValue(book.target_words)
        form.addRow(tr("Wortziel"), self.target_spin)

        self.deadline_edit = QLineEdit(book.deadline)
        self.deadline_edit.setPlaceholderText(tr("z. B. 30.11.2026"))
        form.addRow(tr("Abgabetermin"), self.deadline_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setAcceptRichText(False)
        self.desc_edit.setPlainText(book.description)
        self.desc_edit.setPlaceholderText(tr("Klappentext, Prämisse, Idee …"))
        self.desc_edit.setMinimumHeight(90)
        form.addRow(tr("Beschreibung"), self.desc_edit)

        # Eigene Felder
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Name"), tr("Wert")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setMinimumHeight(110)
        for a in book.attributes:
            self._append_row(a.name, a.value)

        add_btn = QPushButton(tr("＋ Feld"))
        add_btn.clicked.connect(lambda: self._add_row())
        del_btn = QPushButton(tr("Entfernen"))
        del_btn.clicked.connect(self._remove_row)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        fields_box = QWidget()
        fl = QVBoxLayout(fields_box)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.table)
        fl.addLayout(btn_row)
        form.addRow(tr("Eigene Felder"), fields_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            tr("Erstellen") if creating else tr("Übernehmen")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.title_edit.setToolTip(tr("Name des Notizbuchs – erscheint auf dem Buchrücken"))
        self.author_edit.setToolTip(tr("Autor oder Autorin (wird auch ins Manuskript übernommen)"))
        self.genre_edit.setToolTip(tr("Genre zur Orientierung und für die Suche im Regal"))
        self.category_combo.setToolTip(tr("In welchem Regal das Buch steht"))
        self.color_button.setToolTip(tr("Farbe des Buchrückens"))
        self.target_spin.setToolTip(tr("Ziel-Wortzahl – der Fortschritt erscheint als grüner Balken am Buchrücken"))
        self.deadline_edit.setToolTip(tr("Freier Text, z. B. ein Datum"))
        self.desc_edit.setToolTip(tr("Klappentext, Prämisse oder Idee"))
        self.table.setToolTip(tr("Eigene Informationen zum Buch (z. B. Arbeitstitel, Reihe, Lektorin)"))
        add_btn.setToolTip(tr("Neues eigenes Feld hinzufügen"))
        del_btn.setToolTip(tr("Ausgewählte Felder entfernen"))

        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def pick_color(self):
        """Choose the spine colour."""
        c = QColorDialog.getColor(QColor(self._color), self, tr("Buchfarbe"))
        if c.isValid():
            self._color = c.name()
            self.color_button.setIcon(color_icon(self._color, 16))

    def _append_row(self, name, value):
        """Append a row to the custom-fields table."""
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(value))
        return r

    def _add_row(self):
        """Add an empty custom field and start editing its name."""
        r = self._append_row("", "")
        self.table.setCurrentCell(r, 0)
        self.table.editItem(self.table.item(r, 0))

    def _remove_row(self):
        """Remove the selected custom fields."""
        rows = sorted({i.row() for i in self.table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def apply(self, book):
        """Write the form values into ``book`` (call after the dialog was accepted)."""
        book.title = self.title_edit.text().strip() or tr("Unbenannt")
        book.author = self.author_edit.text().strip()
        book.genre = self.genre_edit.text().strip()
        book.category_id = self.category_combo.currentData()
        book.color = self._color
        book.target_words = self.target_spin.value()
        book.deadline = self.deadline_edit.text().strip()
        book.description = self.desc_edit.toPlainText()

        attrs = []
        for r in range(self.table.rowCount()):
            n = self.table.item(r, 0)
            v = self.table.item(r, 1)
            name = (n.text() if n else "").strip()
            value = v.text() if v else ""
            if name or value.strip():
                attrs.append(AttributeData(name, value))
        book.attributes = attrs
