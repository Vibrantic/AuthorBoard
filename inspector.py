# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The Inspector: edit all properties of the selected note.

Sections (top to bottom): note type + colour, status, lock, title, tags (with
auto-completion), attributes (resizable table), content (rich text with spell
check and comments), attachments, connections (searchable / filterable).

The widget never touches the scene directly.  It edits ``note.model`` and
announces changes through signals; the main window reacts (refresh, undo
checkpoint, ...).
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from attachments import AttachmentTooLarge, human_size
from i18n import N_, tr
from models import STATUS_INFO, AttributeData, count_words
from rich_text import RichTextEdit
from theme import color_icon
from widgets import AttachmentList, GrowHandle, TagEdit


class InspectorWidget(QWidget):
    """Property editor for one note (see module docstring)."""

    note_modified = Signal(object)       # any change of the note's data
    delete_requested = Signal(object)    # "delete note" button
    jump_requested = Signal(object)      # double-click in the connections list
    edit_requested = Signal(object)      # open the full-size editor
    lock_toggled = Signal(object, bool)  # note, new locked state
    tags_committed = Signal(list)        # complete tags -> autocomplete memory

    # Suggestions of the "+ Attribute" menu (translated when shown)
    ATTRIBUTE_SUGGESTIONS = [
        N_("Datum"), N_("Uhrzeit"), N_("Ort"), N_("Status"),
        N_("Alter"), N_("Rolle"), N_("Quelle"), N_("Dauer"),
    ]

    def __init__(self, store):
        """Create the inspector; ``store`` is the shared AttachmentStore."""
        super().__init__()

        self.store = store               # AttachmentStore
        self.note = None                 # the NoteItem being edited
        self._types = {}
        self._loading = False            # True while widgets are filled programmatically
        self._links_all = []             # (kind, other note, label) before filtering

        self.build_ui()
        self.set_note(None)
        self._links_cache_key = None
        self._links_cache_value = None

    # Fixed size hints: the dock must not change width when a note is
    # (de)selected, otherwise the board would shift under the mouse.
    def sizeHint(self):
        """Qt: preferred size of the widget."""
        return QSize(390, 640)

    def minimumSizeHint(self):
        """Qt: smallest sensible size of the widget."""
        return QSize(390, 300)

    # ================================================================ UI

    def _section(self, text):
        """A small upper-case section label."""
        label = QLabel(text.upper())
        label.setObjectName("Section")
        return label

    def build_ui(self):

        """Create all widgets (see the module docstring for the sections)."""
        self.setObjectName("Inspector")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel(
            tr("Keine Notiz ausgewählt.\n\n"
               "Doppelklick auf den Hintergrund erstellt eine Notiz,\n"
               "Shift+Leertaste öffnet die Notizarten-Suche.")
        )
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        outer.addWidget(self.empty_label)

        self.form = QWidget()
        self.form.setObjectName("InspectorBody")

        layout = QVBoxLayout(self.form)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        # ---- type + colour
        layout.addWidget(self._section(tr("Notizart")))
        row = QHBoxLayout()
        self.type_combo = QComboBox()
        self.color_button = QPushButton(tr("Farbe"))
        row.addWidget(self.type_combo, 1)
        row.addWidget(self.color_button)
        layout.addLayout(row)

        # ---- status + lock
        layout.addWidget(self._section(tr("Status")))
        row = QHBoxLayout()
        self.status_combo = QComboBox()
        self.status_combo.addItem(tr("Kein Status"), "")
        for key, (label, col) in STATUS_INFO.items():
            self.status_combo.addItem(color_icon(col), tr(label), key)
        self.lock_check = QCheckBox(tr("Position sperren"))
        row.addWidget(self.status_combo, 1)
        row.addWidget(self.lock_check)
        layout.addLayout(row)

        # ---- title
        layout.addWidget(self._section(tr("Titel")))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr("Titel der Notiz …"))
        layout.addWidget(self.title_edit)

        # ---- tags
        layout.addWidget(self._section(tr("Tags")))
        self.tags_edit = TagEdit()
        self.tags_edit.setPlaceholderText(tr("z. B. magie, kapitel1, held"))
        layout.addWidget(self.tags_edit)
        hint = QLabel(tr("Mehrere Tags mit Komma trennen. Vorschläge erscheinen beim Tippen."))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ---- attributes (resizable)
        layout.addWidget(self._section(tr("Attribute")))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Name"), tr("Wert")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        layout.addWidget(GrowHandle(self.table, "attributes", 130))

        row = QHBoxLayout()
        self.add_attr_button = QToolButton()
        self.add_attr_button.setText(tr("＋ Attribut"))
        self.add_attr_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.add_attr_button)
        for name in self.ATTRIBUTE_SUGGESTIONS:
            menu.addAction(tr(name)).triggered.connect(
                lambda _=False, n=name: self.add_attribute(tr(n)))
        menu.addSeparator()
        menu.addAction(tr("Eigenes Attribut …")).triggered.connect(
            lambda _=False: self.add_attribute(""))
        self.add_attr_button.setMenu(menu)
        self.remove_attr_button = QPushButton(tr("Entfernen"))
        row.addWidget(self.add_attr_button)
        row.addWidget(self.remove_attr_button)
        row.addStretch()
        layout.addLayout(row)

        # ---- content (rich text, spell check, comments)
        layout.addWidget(self._section(tr("Inhalt")))
        self.content_edit = RichTextEdit(self.store)
        self.content_edit.setAcceptRichText(False)      # paste as plain text
        self.content_edit.setPlaceholderText(tr("Schreibe deine Notiz …"))
        self.content_edit.setMinimumHeight(140)
        layout.addWidget(self.content_edit, 1)

        self.words_label = QLabel("")
        self.words_label.setObjectName("Hint")
        layout.addWidget(self.words_label)

        self.editor_button = QPushButton(tr("Im großen Editor öffnen  (F2)"))
        layout.addWidget(self.editor_button)

        # ---- attachments (resizable)
        layout.addWidget(self._section(tr("Anhänge")))
        self.attach_list = AttachmentList()
        self.attach_list.setIconSize(QSize(36, 36))
        layout.addWidget(self.attach_list)
        layout.addWidget(GrowHandle(self.attach_list, "attachments", 90, min_height=50))

        row = QHBoxLayout()
        self.attach_add = QPushButton(tr("＋ Anhang"))
        self.attach_remove = QPushButton(tr("Entfernen"))
        row.addWidget(self.attach_add)
        row.addWidget(self.attach_remove)
        row.addStretch()
        layout.addLayout(row)

        # ---- connections (resizable, searchable, filterable)
        layout.addWidget(self._section(tr("Verbindungen")))
        row = QHBoxLayout()
        self.links_search = QLineEdit()
        self.links_search.setPlaceholderText(tr("Verbindungen suchen …"))
        self.links_search.setClearButtonEnabled(True)
        self.links_kind = QComboBox()
        self.links_kind.addItem(tr("Alle"), "")
        self.links_kind.addItem(tr("Fäden"), "thread")
        self.links_kind.addItem(tr("← erwähnt in"), "in")
        self.links_kind.addItem(tr("→ erwähnt"), "out")
        row.addWidget(self.links_search, 1)
        row.addWidget(self.links_kind)
        layout.addLayout(row)

        self.links_type = QComboBox()
        layout.addWidget(self.links_type)

        self.links_list = QListWidget()
        layout.addWidget(self.links_list)
        layout.addWidget(GrowHandle(self.links_list, "connections", 130))

        links_hint = QLabel(tr("Doppelklick springt zur Notiz. ← → zeigt Erwähnungen im Text."))
        links_hint.setObjectName("Hint")
        layout.addWidget(links_hint)

        # ---- delete
        self.delete_button = QPushButton(tr("Notiz löschen"))
        self.delete_button.setObjectName("Danger")
        layout.addWidget(self.delete_button)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        outer.addWidget(scroll)
        self._scroll = scroll

        self._tooltips()
        self._connect()

    def _tooltips(self):
        """Set the tool-tips of all controls."""
        self.color_button.setToolTip(tr("Notizfarbe ändern"))
        self.type_combo.setToolTip(tr("Art der Notiz – bestimmt Farbe und vorgeschlagene Attribute"))
        self.status_combo.setToolTip(tr("Bearbeitungsstatus – erscheint als Farbpunkt auf der Notiz"))
        self.lock_check.setToolTip(tr("Gesperrte Notizen lassen sich weder verschieben noch in der Größe ändern"))
        self.title_edit.setToolTip(tr("Titel der Notiz"))
        self.tags_edit.setToolTip(
            tr("Tags mit Komma trennen. Sie erscheinen als Chips auf der Notiz\n"
               "und lassen sich im Notizen-Panel filtern."))
        self.table.setToolTip(
            tr("Freie Attribute (z. B. Datum, Uhrzeit, Ort).\n"
               "Doppelklick zum Bearbeiten. „Datum“ und „Uhrzeit“ füllen die Zeitleiste."))
        self.add_attr_button.setToolTip(tr("Attribut hinzufügen: Vorschlag wählen oder eigenen Namen vergeben"))
        self.remove_attr_button.setToolTip(tr("Ausgewählte Attributzeilen entfernen"))
        self.content_edit.setToolTip(tr("Freier Text der Notiz – Rechtsklick: Rechtschreibung, Kommentare, Links"))
        self.editor_button.setToolTip(tr("Großer Editor mit Formatierung, Bildern und Kommentaren (F11 im Editor: Vollbild)"))
        self.attach_list.setToolTip(tr("Angehängte Dateien und Bilder – Doppelklick öffnet, Dateien lassen sich hineinziehen"))
        self.attach_add.setToolTip(tr("Dateien oder Bilder an diese Notiz anhängen"))
        self.attach_remove.setToolTip(tr("Ausgewählte Anhänge entfernen"))
        self.links_search.setToolTip(tr("Verbundene Notizen nach Titel oder Fadenbeschriftung durchsuchen"))
        self.links_kind.setToolTip(tr("Nur Fäden oder nur Erwähnungen im Text anzeigen"))
        self.links_type.setToolTip(tr("Nur Notizen dieser Art anzeigen"))
        self.links_list.setToolTip(tr("Über Fäden verbundene und im Text erwähnte Notizen"))
        self.delete_button.setToolTip(tr("Diese Notiz mit allen ihren Fäden löschen"))

    def _connect(self):
        """Connect all widget signals to the slots below."""
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        self.status_combo.currentIndexChanged.connect(self.on_status_changed)
        self.lock_check.toggled.connect(self.on_lock_toggled)
        self.color_button.clicked.connect(self.pick_color)
        self.title_edit.textChanged.connect(self.on_title_changed)
        self.tags_edit.textChanged.connect(self.on_tags_changed)
        self.tags_edit.editingFinished.connect(self.commit_tags)
        self.table.itemChanged.connect(self.on_table_changed)
        self.remove_attr_button.clicked.connect(self.remove_attribute)
        self.content_edit.textChanged.connect(self.on_content_changed)
        self.content_edit.comments_changed.connect(self._changed)
        self.editor_button.clicked.connect(
            lambda: self.note and self.edit_requested.emit(self.note))
        self.attach_add.clicked.connect(self.add_attachments_dialog)
        self.attach_remove.clicked.connect(self.remove_attachments)
        self.attach_list.files_dropped.connect(self.attach_paths)
        self.attach_list.itemDoubleClicked.connect(self.open_attachment)
        self.links_list.itemDoubleClicked.connect(
            lambda it: self.jump_requested.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.links_search.textChanged.connect(self.apply_links_filter)
        self.links_kind.currentIndexChanged.connect(self.apply_links_filter)
        self.links_type.currentIndexChanged.connect(self.apply_links_filter)
        self.delete_button.clicked.connect(
            lambda: self.note and self.delete_requested.emit(self.note))

    # ============================================================== data

    def set_types(self, types):
        """Set the available note types (dict key -> NoteTypeData)."""

        self._types = types

        self._loading = True
        self.type_combo.clear()
        for t in types.values():
            self.type_combo.addItem(color_icon(t.color), t.label, t.key)

        current = self.links_type.currentData()
        self.links_type.clear()
        self.links_type.addItem(tr("Alle Notizarten"), "")
        for t in types.values():
            self.links_type.addItem(color_icon(t.color), t.label, t.key)
        self.links_type.setCurrentIndex(max(self.links_type.findData(current or ""), 0))
        self._loading = False

        if self.note is not None:
            self.set_note(self.note)

    def set_known_tags(self, tags):
        """Tags suggested by the auto-completion (book specific)."""
        self.tags_edit.set_suggestions(tags)

    def set_note(self, note):
        """Show ``note`` (a NoteItem) or the empty state for ``None``."""

        self.note = note
        self._loading = True

        enabled = note is not None
        self._scroll.setVisible(enabled)
        self.empty_label.setVisible(not enabled)

        if note is None:
            self.title_edit.clear()
            self.tags_edit.clear()
            self.content_edit.set_content("", "")
            self.content_edit.bind([], [])
            self.table.setRowCount(0)
            self.links_list.clear()
            self.attach_list.clear()
            self.words_label.setText("")
        else:
            m = note.model

            self.type_combo.setCurrentIndex(max(self.type_combo.findData(m.note_type), 0))
            self.status_combo.setCurrentIndex(max(self.status_combo.findData(m.status), 0))
            self.lock_check.setChecked(m.locked)
            self.title_edit.setText(m.title)
            self.tags_edit.setText(", ".join(m.tags))

            self.content_edit.bind(m.comments, m.attachments)
            self.content_edit.set_content(m.content, m.rich)

            self._update_color_button()
            self._fill_table()
            self._fill_attachments()
            self._update_words()
            self.refresh_links()

        self._loading = False

    def focus_title(self):
        """Put the cursor into the title field (after creating a note)."""
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _changed(self, *_):
        """Common tail of every edit: repaint the note and notify the window."""
        if self._loading or self.note is None:
            return
        self.note.model_changed()
        self.note_modified.emit(self.note)

    def _update_color_button(self):
        """Show the note colour on the colour button."""
        if self.note is not None:
            self.color_button.setIcon(color_icon(self.note.model.color, 16))

    def _update_words(self):
        """Show the word / character count under the text."""
        if self.note is not None:
            text = self.note.model.content
            self.words_label.setText(
                tr("{w} Wörter · {c} Zeichen", w=count_words(text), c=len(text)))

    # ============================================================= slots

    def on_type_changed(self, index):

        """The note type was changed."""
        if self._loading or not self.note:
            return

        m = self.note.model
        key = self.type_combo.itemData(index)
        old, new = self._types.get(m.note_type), self._types.get(key)
        m.note_type = key

        if new is not None:
            # the colour follows the type as long as it was not changed manually
            if old is None or m.color.lower() == old.color.lower():
                m.color = new.color
                self._update_color_button()

            existing = {a.name.lower() for a in m.attributes}
            for name in new.attributes:
                if name.lower() not in existing:
                    m.attributes.append(AttributeData(name, ""))

            self._loading = True
            self._fill_table()
            self._loading = False

        self._changed()

    def on_status_changed(self, index):
        """The status combo was changed."""
        if self._loading or not self.note:
            return
        self.note.model.status = self.status_combo.itemData(index) or ""
        self._changed()

    def on_lock_toggled(self, checked):
        """The 'lock position' box was toggled -> ask the window to lock/unlock."""
        if self._loading or not self.note:
            return
        self.lock_toggled.emit(self.note, checked)

    def pick_color(self):
        """Choose a custom note colour."""
        if not self.note:
            return
        color = QColorDialog.getColor(QColor(self.note.model.color), self, tr("Notizfarbe"))
        if color.isValid():
            self.note.model.color = color.name()
            self._update_color_button()
            self._changed()

    def on_title_changed(self, text):
        """The title field was edited."""
        if self._loading or not self.note:
            return
        self.note.model.title = text
        self._changed()

    def on_content_changed(self):
        """Store plain text always, HTML only when the text has formatting."""
        if self._loading or not self.note:
            return
        plain, rich = self.content_edit.to_storage()
        self.note.model.content = plain
        self.note.model.rich = rich
        self._update_words()
        self._changed()

    # ---- tags

    @staticmethod
    def _parse_tags(text):
        """Split ``text`` at commas into a de-duplicated tag list."""
        tags, seen = [], set()
        for part in text.split(","):
            tag = part.strip().lstrip("#").strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                tags.append(tag)
        return tags

    def on_tags_changed(self, text):
        """The tag field was edited (every keystroke)."""
        if self._loading or not self.note:
            return
        self.note.model.tags = self._parse_tags(text)
        # Tags before the last comma are finished -> remember for auto-completion
        if "," in text:
            self.tags_committed.emit(self._parse_tags(text.rsplit(",", 1)[0]))
        self._changed()

    def commit_tags(self):
        """Focus left the field: every tag is final."""
        if self.note is not None:
            self.tags_committed.emit(self._parse_tags(self.tags_edit.text()))

    # ---- attributes

    def _append_row(self, name, value):
        """Append a (name, value) row to the attribute table."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(value))
        return row

    def _fill_table(self):
        """Fill the attribute table from the model."""
        was = self._loading
        self._loading = True
        self.table.setRowCount(0)
        for a in self.note.model.attributes:
            self._append_row(a.name, a.value)
        self._loading = was

    def on_table_changed(self, item):
        """A table cell was edited."""
        if self._loading or not self.note:
            return
        self._sync_attributes()

    def _sync_attributes(self):
        """Copy the table content back into the model."""
        attrs = []
        for r in range(self.table.rowCount()):
            n, v = self.table.item(r, 0), self.table.item(r, 1)
            attrs.append(AttributeData((n.text() if n else "").strip(),
                                       v.text() if v else ""))
        self.note.model.attributes = attrs
        self._changed()

    def add_attribute(self, name=""):
        """Add a row (optionally with a suggested name) and start editing."""
        if not self.note:
            return
        self._loading = True
        row = self._append_row(name, "")
        self._loading = False
        self._sync_attributes()
        col = 1 if name else 0
        self.table.setCurrentCell(row, col)
        self.table.editItem(self.table.item(row, col))

    def remove_attribute(self):
        """Remove the selected attribute rows."""
        if not self.note:
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._loading = True
        for r in rows:
            self.table.removeRow(r)
        self._loading = False
        self._sync_attributes()

    # ---- attachments

    def _fill_attachments(self):
        """Rebuild the list; images get a thumbnail, other files a file icon."""
        self.attach_list.clear()
        file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        for att in self.note.model.attachments:
            text = f"{att.name}   ({human_size(att.size)})"
            if att.inline:
                text += "  · " + tr("im Text")
            icon = file_icon
            if att.mime.startswith("image/"):
                img = self.store.image(att.id)
                if img is not None:
                    icon = QIcon(QPixmap.fromImage(
                        img.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)))
            item = QListWidgetItem(icon, text)
            item.setData(Qt.ItemDataRole.UserRole, att.id)
            self.attach_list.addItem(item)

    def add_attachments_dialog(self):
        """Choose files to attach."""
        if not self.note:
            return
        files, _ = QFileDialog.getOpenFileNames(self, tr("Dateien anhängen"), "", tr("Alle Dateien (*)"))
        self.attach_paths(files)

    def attach_paths(self, paths):
        """Attach local files to the current note (also used by drag & drop)."""
        if not self.note:
            return
        added = False
        for p in paths:
            try:
                self.note.model.attachments.append(self.store.add_file(p))
                added = True
            except AttachmentTooLarge as error:
                QMessageBox.warning(self, tr("Anhang zu groß"),
                                    tr("„{name}“ ist größer als 40 MB und wurde nicht angehängt.",
                                       name=str(error)))
            except OSError as error:
                QMessageBox.warning(self, tr("Fehler"), str(error))
        if added:
            self._fill_attachments()
            self._changed()

    def remove_attachments(self):
        """Remove selected attachments from the note (bytes are pruned on save)."""
        if not self.note:
            return
        ids = {i.data(Qt.ItemDataRole.UserRole) for i in self.attach_list.selectedItems()}
        if not ids:
            return
        self.note.model.attachments = [a for a in self.note.model.attachments if a.id not in ids]
        self._fill_attachments()
        self._changed()

    def open_attachment(self, item):
        """Open an attachment with the system's default program."""
        att_id = item.data(Qt.ItemDataRole.UserRole)
        att = next((a for a in self.note.model.attachments if a.id == att_id), None)
        if att is not None:
            self.store.open(att)

    # ---- connections

    def refresh_links(self):
        """Collect threads and text mentions of the current note.

        Optimized: the thread list comes from ``note.links()`` (cheap, only
        that note's pins), and the mention list depends only on the current
        note's title/content plus the scene's overall content — the latter
        is captured by ``scene._mentions_revision``.  If neither has changed
        since the last call, reuse the cached result."""
        if self.note is None:
            self._links_all = []
            self._links_cache_key = None
            self._links_cache_value = None
            self.apply_links_filter()
            return

        scene = self.note.scene()
        revision = getattr(scene, "_mentions_revision", 0) if scene is not None else 0
        key = (self.note.model.id, revision)

        if (self._links_cache_key == key
                and self._links_cache_value is not None):
            self._links_all = self._links_cache_value
            self.apply_links_filter()
            return

        # ---- Cold path: recompute ----
        self._links_all = []

        # 1) Threads — cheap, always fresh.
        for other, label in self.note.links():
            self._links_all.append(("thread", other, label))

        # 2) Mentions — only if the list is visible.
        if not self.links_list.isVisibleTo(self):
            self.apply_links_filter()
            return

        if scene is not None:
            generic = {t.label.lower()
                       for t in getattr(scene, "note_types", {}).values()}
            mine = self.note.model.title.strip().lower()
            my_text = self.note.model.content.lower()
            for other in list(scene.note_lookup.values()):
                if other is self.note:
                    continue
                ot = other.model.title.strip().lower()
                if (len(mine) >= 3 and mine not in generic
                        and mine in other.model.content.lower()):
                    self._links_all.append(("in", other, ""))
                if len(ot) >= 3 and ot not in generic and ot in my_text:
                    self._links_all.append(("out", other, ""))

        self._links_cache_key = key
        self._links_cache_value = list(self._links_all)

        self.apply_links_filter()

    def apply_links_filter(self, *_):
        """Fill the list from ``_links_all`` using search text, kind and type."""

        text = self.links_search.text().strip().lower()
        kind = self.links_kind.currentData() or ""
        type_key = self.links_type.currentData() or ""

        self.links_list.clear()

        for k, other, label in self._links_all:
            title = other.model.title or tr("Ohne Titel")
            if kind and k != kind:
                continue
            if type_key and other.model.note_type != type_key:
                continue
            if text and text not in (title + " " + label).lower():
                continue

            if k == "thread":
                shown = "↔ " + title + (f"   ({label})" if label else "")
            elif k == "in":
                shown = tr("← erwähnt in {name}", name=title)
            else:
                shown = tr("→ erwähnt {name}", name=title)

            item = QListWidgetItem(shown)
            item.setData(Qt.ItemDataRole.UserRole, other)
            self.links_list.addItem(item)
