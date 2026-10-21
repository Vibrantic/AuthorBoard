# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Manuscript export: collect chapters/scenes in order and write Markdown, text,
HTML or PDF.  Also contains the dialog where the user chooses what to export.
"""

from html import escape

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from models import count_words, note_sort_key
from rich_text import embed_images, html_body
from i18n import tr, N_

FORMATS = [
    ("Markdown (.md)", "md"),
    ("Text (.txt)", "txt"),
    ("HTML (.html)", "html"),
    ("PDF (.pdf)", "pdf"),
]


def build_sections(notes, type_keys, store=None):
    """Notes of the chosen types in manuscript order (attribute "Nummer", then title).

    Returns a list of ``(heading, plain_text, html)``.  ``html`` is the formatted
    body of the note (with images embedded as data URIs when ``store`` is given)
    or ``""`` for plain notes; only the HTML/PDF export uses it."""

    chosen = [n for n in notes if n.model.note_type in type_keys]
    chosen.sort(key=lambda n: note_sort_key(n.model))

    sections = []
    for n in chosen:
        html = ""
        if n.model.rich:
            html = html_body(n.model.rich)
            if store is not None:
                html = embed_images(html, store)
        sections.append((n.model.title or tr("Ohne Titel"), n.model.content.strip(), html))
    return sections


def to_markdown(sections, title, author, include_titles):
    """Render sections as Markdown."""
    lines = [f"# {title}", ""]
    if author:
        lines += [f"*{author}*", ""]
    for head, text, _html in sections:
        if include_titles:
            lines += [f"## {head}", ""]
        if text:
            lines += [text, ""]
    return "\n".join(lines)


def to_text(sections, title, author, include_titles):
    """Render sections as plain text."""
    lines = [title.upper(), ""]
    if author:
        lines += [author, ""]
    lines.append("")
    for head, text, _html in sections:
        if include_titles:
            lines += [head, "-" * len(head), ""]
        if text:
            lines += [text, ""]
        lines.append("")
    return "\n".join(lines)


def to_html(sections, title, author, include_titles):

    """Render sections as HTML; rich notes keep their formatting and images."""
    def paragraphs(text):
        out = []
        for block in text.split("\n\n"):
            block = block.strip()
            if block:
                out.append("<p>" + escape(block).replace("\n", "<br>") + "</p>")
        return "".join(out)

    body = [f"<h1 style='text-align:center'>{escape(title)}</h1>"]
    if author:
        body.append(f"<p style='text-align:center'><i>{escape(author)}</i></p>")

    for head, text, html in sections:
        if include_titles:
            body.append(f"<h2>{escape(head)}</h2>")
        body.append(html or paragraphs(text))      # keep formatting / images when present

    return (
        "<html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        "<style>body{font-family:Georgia,serif;font-size:12pt;line-height:1.5;"
        "max-width:42em;margin:2em auto;} h2{margin-top:2em;}</style>"
        "</head><body>" + "".join(body) + "</body></html>"
    )


def render(fmt, sections, title, author, include_titles):
    """Render in the chosen format (md / txt / html)."""
    if fmt == "md":
        return to_markdown(sections, title, author, include_titles)
    if fmt == "txt":
        return to_text(sections, title, author, include_titles)
    return to_html(sections, title, author, include_titles)


def write_pdf(html, filename):
    """Render HTML into a PDF file using Qt's text engine."""
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

    doc = QTextDocument()
    doc.setHtml(html)

    writer = QPdfWriter(filename)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(22, 22, 22, 22), QPageLayout.Unit.Millimeter)
    doc.print_(writer)


class ManuscriptDialog(QDialog):
    """Manuskript aus Kapiteln/Szenen zusammenstellen und exportieren."""

    def __init__(self, notes, note_types, parent=None):
        """Build the dialog with a checkable list of note types."""
        super().__init__(parent)

        self.setWindowTitle(tr("Manuskript exportieren"))
        self.resize(440, 460)

        self.notes = notes

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(10)

        layout.addWidget(QLabel(
            tr("Welche Notizarten sollen ins Manuskript?\n"
            "Die Reihenfolge richtet sich nach dem Attribut „Nummer“.")
        ))

        self.list = QListWidget()
        present = {}
        for n in notes:
            present[n.model.note_type] = present.get(n.model.note_type, 0) + 1

        default = {"chapter", "scene"} & set(present)

        for key, count in present.items():
            info = note_types.get(key)
            label = info.label if info else key
            item = QListWidgetItem(f"{label}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = (key in default) if default else True
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

        form = QFormLayout()
        self.format_combo = QComboBox()
        for label, key in FORMATS:
            self.format_combo.addItem(label, key)
        form.addRow(tr("Format"), self.format_combo)

        self.titles_check = QCheckBox(tr("Titel als Überschriften einfügen"))
        self.titles_check.setChecked(True)
        form.addRow("", self.titles_check)
        layout.addLayout(form)

        self.summary = QLabel("")
        self.summary.setObjectName("Muted")
        layout.addWidget(self.summary)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Exportieren …"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.list.itemChanged.connect(self.update_summary)
        self.update_summary()

    def selected_types(self):
        """Keys of the checked note types."""
        return {
            self.list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.CheckState.Checked
        }

    def update_summary(self, *_):
        """Show how many notes / words would be exported."""
        keys = self.selected_types()
        chosen = [n for n in self.notes if n.model.note_type in keys]
        words = sum(count_words(n.model.content) for n in chosen)
        self.summary.setText(tr("{n} Notizen · {words} Wörter", n=len(chosen), words=words))

    def fmt(self):
        """Chosen format key (md / txt / html / pdf)."""
        return self.format_combo.currentData()

    def include_titles(self):
        """True when titles become headings."""
        return self.titles_check.isChecked()
