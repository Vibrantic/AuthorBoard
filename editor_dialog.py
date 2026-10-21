# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The full-size note editor.

A modal dialog around :class:`rich_text.RichTextEdit` with a formatting
toolbar: font, size, bold / italic / underline / strike-through, text colour,
highlight colour, alignment, bullet list, links, images, comments and the spell
check language.  A sidebar lists the comments of the note.

The dialog edits *copies* (title, comments, attachments); the main window reads
the ``result_*`` accessors only when the user presses *Apply*.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QKeySequence,
    QTextCharFormat,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from i18n import N_, tr
from models import AttachmentData, CommentData, count_words
from rich_text import RichTextEdit
from settings import settings
from spellcheck import LANGUAGES, engine
from theme import color_icon

# Quick colours offered in the text colour / highlight menus
TEXT_COLORS = [("#ff5c5c", N_("Rot")), ("#ff9f43", N_("Orange")), ("#ffd54f", N_("Gelb")),
               ("#4cc38a", N_("Grün")), ("#4da6ff", N_("Blau")), ("#b388ff", N_("Violett")),
               ("#f1f1f1", N_("Weiß")), ("#222222", N_("Schwarz"))]
HIGHLIGHT_COLORS = [("#fff176", N_("Gelb")), ("#a5d6a7", N_("Grün")), ("#f8bbd0", N_("Rosa")),
                    ("#90caf9", N_("Blau")), ("#ffcc80", N_("Orange"))]


class NoteEditorDialog(QDialog):
    """Rich-text editor for one note (see module docstring)."""

    def __init__(self, model, store, parent=None, focus_comment=None):
        """Build the dialog for ``model`` (a NoteData); ``focus_comment`` selects that comment's words."""
        super().__init__(parent)

        self.setWindowTitle(tr("Notiz bearbeiten"))
        self.resize(1100, 760)
        self.store = store

        # Working copies - the model is only touched through result_*()
        self._comments = [CommentData(c.id, c.text, c.quote, c.created) for c in model.comments]
        self._attachments = [AttachmentData(a.id, a.name, a.mime, a.size, a.inline)
                             for a in model.attachments]
        self._plain, self._rich = model.content, model.rich

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(8)

        self.title_edit = QLineEdit(model.title)
        self.title_edit.setPlaceholderText(tr("Titel …"))
        self.title_edit.setStyleSheet("font-size: 16pt; font-weight: 600;")
        layout.addWidget(self.title_edit)

        self.edit = RichTextEdit(store)
        self.edit.setStyleSheet("font-size: 13pt; padding: 14px;")
        self.edit.bind(self._comments, self._attachments)
        self.edit.set_content(model.content, model.rich)

        layout.addWidget(self._build_toolbar())

        # editor | comments sidebar
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.edit)
        split.addWidget(self._build_sidebar())
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)

        self.words = QLabel("")
        self.words.setObjectName("Muted")
        self.words.setToolTip(tr("F11: Vollbild (ablenkungsfrei)"))
        layout.addWidget(self.words)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Übernehmen"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.edit.textChanged.connect(self.update_words)
        self.edit.currentCharFormatChanged.connect(self._sync_toolbar)
        self.edit.comments_changed.connect(self._fill_comments)
        self.update_words()
        self._fill_comments()

        full = QAction(self)
        full.setShortcut(QKeySequence("F11"))
        full.triggered.connect(self.toggle_fullscreen)
        self.addAction(full)

        self.edit.setFocus()
        if focus_comment:
            # let the dialog show first, then select the commented words
            QTimer.singleShot(60, lambda: self.edit.focus_comment(focus_comment))

    # ============================================================ toolbar

    def _build_toolbar(self):
        """Two toolbar rows (text formatting / insert + spelling) in one widget,
        so nothing is hidden behind an overflow menu on narrow windows."""
        bar = QToolBar()
        bar.setMovable(False)
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(bar)

        self.font_combo = QFontComboBox()
        self.font_combo.setMaximumWidth(190)
        self.font_combo.setToolTip(tr("Schriftart"))
        self.font_combo.activated.connect(self._set_font_family)
        bar.addWidget(self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 96)
        self.size_spin.setValue(max(6, self.edit.fontInfo().pointSize()))
        self.size_spin.setToolTip(tr("Schriftgröße"))
        self.size_spin.valueChanged.connect(self._set_font_size)
        bar.addWidget(self.size_spin)
        bar.addSeparator()

        def action(text, tip, slot, shortcut=None, checkable=False):
            a = QAction(text, self)
            a.setToolTip(tip + (f" ({shortcut})" if shortcut else ""))
            a.setCheckable(checkable)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            bar.addAction(a)
            return a

        self.act_bold = action("B", tr("Fett"), self._toggle_bold, "Ctrl+B", True)
        self.act_italic = action("I", tr("Kursiv"), self._toggle_italic, "Ctrl+I", True)
        self.act_underline = action("U", tr("Unterstrichen"), self._toggle_underline, "Ctrl+U", True)
        self.act_strike = action("S", tr("Durchgestrichen"), self._toggle_strike, None, True)
        for a, css in ((self.act_bold, "font-weight:bold"), (self.act_italic, "font-style:italic"),
                       (self.act_underline, "text-decoration:underline"),
                       (self.act_strike, "text-decoration:line-through")):
            bar.widgetForAction(a).setStyleSheet(css)
        bar.addSeparator()

        self.text_color_button = self._color_button(
            bar, "A", tr("Textfarbe"), TEXT_COLORS, self._apply_text_color, tr("Standardfarbe"))
        self.highlight_button = self._color_button(
            bar, "🖍", tr("Textmarker (Hintergrundfarbe)"), HIGHLIGHT_COLORS,
            self._apply_highlight, tr("Markierung entfernen"))
        bar.addSeparator()

        group = QActionGroup(self)
        for text, tip, align in (("⯇", tr("Linksbündig"), Qt.AlignmentFlag.AlignLeft),
                                 ("≡", tr("Zentriert"), Qt.AlignmentFlag.AlignHCenter),
                                 ("⯈", tr("Rechtsbündig"), Qt.AlignmentFlag.AlignRight),
                                 ("☰", tr("Blocksatz"), Qt.AlignmentFlag.AlignJustify)):
            a = action(text, tip, lambda _=False, al=align: self.edit.setAlignment(al))
            group.addAction(a)
        action("•", tr("Aufzählung ein/aus"), self._toggle_list)

        # second row
        bar = QToolBar()
        bar.setMovable(False)
        box.addWidget(bar)

        action("🔗", tr("Link einfügen (markierten Text verlinken)"), self.insert_link, "Ctrl+K")
        action("🖼", tr("Bild einfügen (wird als Anhang gespeichert)"), self.insert_image)
        action("💬", tr("Kommentar zur Markierung hinzufügen"), self.edit.add_comment_dialog, "Ctrl+Alt+M")
        action("⌫", tr("Formatierung entfernen"), self.clear_formatting)
        bar.addSeparator()

        # spell-check language
        bar.addWidget(QLabel(" " + tr("Rechtschreibung:") + " "))
        self.spell_combo = QComboBox()
        self.spell_combo.addItem(tr("Automatisch"), "auto")
        for code, name in LANGUAGES.items():
            self.spell_combo.addItem(name, code)
        self.spell_combo.addItem(tr("Aus"), "off")
        current = "off" if not settings.get("spell_enabled") else settings.get("spell_language")
        self.spell_combo.setCurrentIndex(max(self.spell_combo.findData(current), 0))
        self.spell_combo.setToolTip(
            tr("Sprache der Rechtschreibprüfung") if engine.available()
            else tr("Rechtschreibprüfung nicht verfügbar: pip install pyspellchecker"))
        self.spell_combo.setEnabled(engine.available())
        self.spell_combo.activated.connect(self._set_spell_language)
        bar.addWidget(self.spell_combo)
        return container

    def _color_button(self, bar, text, tip, colors, apply, reset_text):
        """A tool button with a drop-down of quick colours + custom + reset."""
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tip)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        for col, name in colors:
            menu.addAction(color_icon(col), tr(name)).triggered.connect(
                lambda _=False, c=col: apply(QColor(c)))
        menu.addSeparator()
        menu.addAction(tr("Eigene Farbe …")).triggered.connect(
            lambda _=False: self._pick_custom(apply))
        menu.addAction(reset_text).triggered.connect(lambda _=False: apply(None))
        btn.setMenu(menu)
        bar.addWidget(btn)
        return btn

    def _pick_custom(self, apply):
        """Ask for a custom colour and pass it to ``apply``."""
        c = QColorDialog.getColor(QColor("#ffd54f"), self, tr("Farbe wählen"))
        if c.isValid():
            apply(c)

    # ------------------------------------------------------- formatting

    def _merge(self, fmt):
        """Apply ``fmt`` to the selection (or the word under the cursor)."""
        cursor = self.edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(cursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)

    def _set_font_family(self, _index):
        """Toolbar: apply the chosen font family."""
        fmt = QTextCharFormat()
        fmt.setFontFamilies([self.font_combo.currentFont().family()])
        self._merge(fmt)
        self.edit.setFocus()

    def _set_font_size(self, size):
        """Toolbar: apply the chosen font size."""
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self._merge(fmt)

    def _toggle_bold(self, on):
        """Toolbar: bold on/off."""
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if on else QFont.Weight.Normal)
        self._merge(fmt)

    def _toggle_italic(self, on):
        """Toolbar: italic on/off."""
        fmt = QTextCharFormat()
        fmt.setFontItalic(on)
        self._merge(fmt)

    def _toggle_underline(self, on):
        """Toolbar: underline on/off."""
        fmt = QTextCharFormat()
        fmt.setFontUnderline(on)
        self._merge(fmt)

    def _toggle_strike(self, on):
        """Toolbar: strike-through on/off."""
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(on)
        self._merge(fmt)

    def _apply_text_color(self, color):
        """``None`` resets to the default text colour."""
        cursor = self.edit.textCursor()
        if color is None:
            # clearing a property needs setCharFormat, merge cannot remove it
            if not cursor.hasSelection():
                cursor.select(cursor.SelectionType.WordUnderCursor)
            fmt = QTextCharFormat(cursor.charFormat())
            fmt.clearForeground()
            cursor.setCharFormat(fmt)
        else:
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._merge(fmt)

    def _apply_highlight(self, color):
        """Apply a background (highlighter) colour; ``None`` removes it."""
        cursor = self.edit.textCursor()
        if color is None:
            if not cursor.hasSelection():
                cursor.select(cursor.SelectionType.WordUnderCursor)
            fmt = QTextCharFormat(cursor.charFormat())
            fmt.clearBackground()
            cursor.setCharFormat(fmt)
        else:
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self._merge(fmt)

    def _toggle_list(self):
        """Toolbar: bullet list on/off for the current paragraph."""
        cursor = self.edit.textCursor()
        current = cursor.currentList()
        if current is not None:
            current.remove(cursor.block())
            fmt = cursor.blockFormat()
            fmt.setIndent(0)
            cursor.setBlockFormat(fmt)
        else:
            cursor.createList(QTextListFormat.Style.ListDisc)

    def clear_formatting(self):
        """Remove fonts/colours/bold… from the selection but keep links and comments."""
        cursor = self.edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(cursor.SelectionType.WordUnderCursor)
        old = cursor.charFormat()
        keep = QTextCharFormat()
        if old.isAnchor():
            keep.setAnchor(True)
            keep.setAnchorHref(old.anchorHref())
        if old.toolTip():
            keep.setToolTip(old.toolTip())
        cursor.setCharFormat(keep)

    def _sync_toolbar(self, fmt):
        """Reflect the format at the cursor in the toolbar controls."""
        self.act_bold.setChecked(fmt.fontWeight() > 450)
        self.act_italic.setChecked(fmt.fontItalic())
        self.act_underline.setChecked(fmt.fontUnderline())
        self.act_strike.setChecked(fmt.fontStrikeOut())
        families = fmt.fontFamilies()
        if families:
            self.font_combo.blockSignals(True)
            self.font_combo.setCurrentFont(QFont(families[0] if isinstance(families, list) else str(families)))
            self.font_combo.blockSignals(False)
        if fmt.fontPointSize() > 0:
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(int(fmt.fontPointSize()))
            self.size_spin.blockSignals(False)

    # ------------------------------------------------- links and images

    def insert_link(self):
        """Ask for a URL and link the selected text (or insert the URL)."""
        url, ok = QInputDialog.getText(self, tr("Link einfügen"),
                                       tr("Adresse (URL):"), text="https://")
        if ok and url.strip() and url.strip() != "https://":
            self.edit.set_link(url.strip())

    def insert_image(self):
        """Choose an image file; it is stored as an attachment and shown inline."""
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Bild einfügen"), "",
            tr("Bilder (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"))
        for path in files:
            with open(path, "rb") as f:
                name = path.replace("\\", "/").split("/")[-1]
                self.edit.insert_image_bytes(name, f.read())

    # --------------------------------------------------------- spelling

    def _set_spell_language(self, _index):
        """Toolbar: store the chosen spell-check language and re-check."""
        value = self.spell_combo.currentData()
        if value == "off":
            settings.set("spell_enabled", False)
        else:
            settings.set("spell_enabled", True)
            settings.set("spell_language", value)
        engine.clear_cache()
        self.edit.refresh_spelling()

    # ------------------------------------------------- comments sidebar

    def _build_sidebar(self):
        """Build the comments sidebar (list + delete button)."""
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 0, 0, 0)
        title = QLabel(tr("Kommentare").upper())
        title.setObjectName("Section")
        lay.addWidget(title)
        self.comment_list = QListWidget()
        self.comment_list.setWordWrap(True)
        self.comment_list.setToolTip(tr("Doppelklick markiert die kommentierte Stelle"))
        self.comment_list.itemDoubleClicked.connect(
            lambda it: self.edit.focus_comment(it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.comment_list, 1)
        delete = QPushButton(tr("Kommentar löschen"))
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete_selected_comment)
        lay.addWidget(delete)
        return box

    def _fill_comments(self):
        """Refill the sidebar from the working list of comments."""
        self.comment_list.clear()
        for c in self._comments:
            item = QListWidgetItem(f"“{c.quote}”\n💬 {c.text}")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self.comment_list.addItem(item)

    def _delete_selected_comment(self):
        """Delete the comment selected in the sidebar (and its marker)."""
        item = self.comment_list.currentItem()
        if item:
            comment = self.edit.comment_by_id(item.data(Qt.ItemDataRole.UserRole))
            if comment:
                self.edit.delete_comment(comment)

    # ----------------------------------------------------------- misc

    def toggle_fullscreen(self):
        """F11: switch between full screen and window."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def update_words(self):
        """Update the word / character counter."""
        text = self.edit.toPlainText().replace("\ufffc", "")
        self.words.setText(tr("{w} Wörter · {c} Zeichen", w=count_words(text), c=len(text)))

    def accept(self):
        """Collect the result before closing (comments whose text was deleted are dropped)."""
        self.edit.prune_comments()
        self._plain, self._rich = self.edit.to_storage()
        super().accept()

    # ------------------------------------------------------ results

    def result_title(self):
        """The edited title."""
        return self.title_edit.text()

    def result_content(self):
        """The edited plain text."""
        return self._plain

    def result_rich(self):
        """The edited HTML (empty for plain notes)."""
        return self._rich

    def result_comments(self):
        """The edited list of comments."""
        return self._comments

    def result_attachments(self):
        """The edited list of attachments (incl. newly inserted images)."""
        return self._attachments
