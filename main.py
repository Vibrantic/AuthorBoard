# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""AuthorBoard - application entry point and main window.

``MainWindow`` is the "controller": it owns the scene, the inspector, the
library and all application state (undo stack, attachment store, tag memory,
current book) and wires the widgets together through signals.

Reading guide
-------------
1. ``__init__`` / ``create_*``   build the UI
2. Undo / Redo / Dirty           snapshot based history (see undo.py)
3. Autosave                      crash recovery files
4. Shelf / books                 switching between bookshelf and board
5. Project load / save           ``build_project_data`` <-> ``restore_project``
6. Editor, comments, settings, help
7. Filters / tree                the left "Notes" panel

Run with ``python main.py``.
"""

import json
import os
import re
import sys
from collections import Counter

from PySide6.QtCore import (
    QEvent,
    QLibraryInfo,
    QLocale,
    QRectF,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QTranslator,
    QRunnable,
)

from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models import (
    BUILTIN_NOTE_TYPES,
    attribute_value,
    builtin_note_types,
    BUILTIN_TYPE_KEYS,
    STATUS_INFO,
    NoteTypeData,
    ProjectData,
    count_words,
    note_timeline_key,
    note_word_count,
)
from storage import Storage
from attachments import AttachmentStore
from settings import GLOBAL_PREFIX, settings
from spellcheck import engine
from rich_text import COMMENT_PREFIX, remove_comment_marker
from comments_panel import CommentsPanel, RightPanel
from settings_dialog import SettingsDialog
from help_dialog import HelpDialog
from about_dialog import AboutDialog
from undo import Snapshot, UndoStack
from export import build_markdown
from canvas import BoardScene, BoardView
from note_item import NoteItem
from inspector import InspectorWidget
from palette import CommandPalette
from editor_dialog import NoteEditorDialog
from library import Library
from shelf import ShelfPage
from book_dialog import BookInfoDialog
from stats import build_stats_html
from timeline import TimelineWidget, date_to_days
from manuscript import (
    ManuscriptDialog,
    build_sections,
    render,
    to_html,
    write_pdf,
)
from theme import (
    CUSTOM_TYPE_COLORS,
    STYLESHEET,
    apply_dark_palette,
    color_icon,
)
import i18n
from i18n import tr, N_
from storage import FORMAT_VERSION, Storage

SETTINGS_ORG = "AuthorBoard"
SETTINGS_APP = "AuthorBoard"

_windows = []          # Hauptfenster am Leben halten (Sprachwechsel erzeugt ein neues)
_qt_translator = None


def install_qt_translation(app, code):
    """Qt-eigene Texte (Standarddialoge, Schaltflächen) in die Sprache übersetzen."""

    global _qt_translator

    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None

    translator = QTranslator()
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)

    if translator.load(f"qtbase_{code}", path):
        app.installTranslator(translator)
        _qt_translator = translator


def initial_language():
    """Gespeicherte Sprache, sonst Systemsprache (falls vorhanden), sonst Englisch."""

    langs = i18n.available_languages()

    saved = QSettings(SETTINGS_ORG, SETTINGS_APP).value("language", "")
    if saved in langs:
        return saved

    system = QLocale.system().name().split("_")[0]
    if system in langs:
        return system

    return "en" if "en" in langs else i18n.SOURCE_LANG


RECOVERY_PATH = os.path.join(os.path.expanduser("~"), ".authorboard_recovery.json")
AUTOSAVE_INTERVAL_MS = 120_000


class _AutosaveWorker(QRunnable):
    """Write an autosave file on a worker thread.

    The dict is built on the UI thread (it reads the scene) and passed here
    as plain Python data — no Qt objects, no scene references.  The write is
    atomic (tmp + os.replace) so a crash or a mid-write kill leaves the
    previous autosave intact.
    """
    def __init__(self, data: dict, path: str):
        """Store the dict and the target path; nothing else."""
        super().__init__()
        self.data = data
        self.path = path
        self.setAutoDelete(True)

    def run(self):
        """Worker entry point: serialise and replace the target file."""
        import json as _json
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            # Autosave is best-effort; never crash the worker.
            pass


class MainWindow(QMainWindow):

    """The application window - see the module docstring."""
    def __init__(self):
        """Create state, UI, timers and signal connections; start on the bookshelf."""
        super().__init__()

        self.current_file = None
        self._closing_for_switch = False
        self.library = Library()
        self.current_book = None
        self.attachments = AttachmentStore()   # bytes of all attachments of the open book
        self.known_tags = set()                # tag auto-completion memory (per book)
        self._help = None                      # help window (created on first use)


        # Gemeinsames Notizarten-Register (wird auch von Szene/Inspector genutzt)
        self.note_types = {t.key: t for t in builtin_note_types()}

        # Undo/Redo + Änderungsstatus
        self.undo_stack = UndoStack()
        self.saved_state = None
        self.dirty = False
        self._restoring = False

        # Per-note JSON cache for structural-sharing snapshots (Optimization.md 3.1)
        self._note_json_cache = {}

        # Dirty flags for refresh_views (Optimization.md 2.2)
        self._dirty_flags = {
            "tags": True, "tree": True, "stats": True,
            "timeline": True, "aux": True, "links": True,
        }

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh_views)

        # Incremental tree state.
        self._tree_items = {}       # note_id -> (item, revision, parent_key)
        self._tree_groups = {}      # type_key -> group QTreeWidgetItem

        self._checkpoint_timer = QTimer(self)
        self._checkpoint_timer.setSingleShot(True)
        self._checkpoint_timer.setInterval(350)
        self._checkpoint_timer.timeout.connect(self.checkpoint)

        self._autosave_pool = QThreadPool(self)
        self._autosave_pool.setMaxThreadCount(1)
        self._autosave_in_flight = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(int(settings.get("autosave_minutes") or 2) * 60_000)
        self._autosave_timer.timeout.connect(self.autosave)
        self._autosave_timer.start()

        self.setup_window()
        self.create_canvas()
        self.create_docks()
        self.create_menu()
        self.create_toolbar()
        self.apply_theme()

        self.stats_label = QLabel("")
        self.statusBar().addPermanentWidget(self.stats_label)

        self.scene.note_selected.connect(self.on_note_selected)
        self.scene.notes_changed.connect(self.schedule_refresh)
        self.scene.notes_changed.connect(self.schedule_checkpoint)
        self.scene.interaction_finished.connect(self.schedule_checkpoint)
        self.scene.edit_requested.connect(self.open_editor)
        self.scene.note_created.connect(
            lambda _n: QTimer.singleShot(60, self.inspector.focus_title)
        )

        self.inspector.note_modified.connect(self.schedule_refresh)
        self.inspector.note_modified.connect(self.schedule_checkpoint)
        self.inspector.delete_requested.connect(self.confirm_delete_note)
        self.inspector.jump_requested.connect(self.jump_to_note)
        self.inspector.edit_requested.connect(self.open_editor)
        self.inspector.lock_toggled.connect(lambda n, on: self.scene.set_note_locked(n, on))
        self.inspector.tags_committed.connect(self.remember_tags)
        self.comments_panel.open_requested.connect(lambda n, cid: self.open_editor(n, cid))
        self.comments_panel.delete_requested.connect(self.delete_comment)
        self.comments_panel.focus_requested.connect(self.focus_note_from_comment)

        self.shelf.open_requested.connect(self.open_book)
        self.shelf.new_book_requested.connect(self.create_book)

        self.inspector.set_types(self.note_types)
        self.refresh_type_combo()
        self.refresh_views()
        self.reset_history()

        self.statusBar().showMessage(
            tr("Doppelklick: Notiz  ·  Rechtsklick auf Pin ziehen: verbinden  ·  "
            "Shift+Leertaste: Notizart suchen  ·  Mittlere Maustaste: verschieben")
        )

        QApplication.instance().installEventFilter(self)

        # Startseite = Bücherregal
        self._dock_vis = {
            self.tree_dock: True,
            self.inspector_dock: True,
            self.timeline_dock: False,
        }
        self._hide_docks()
        self.stack.setCurrentWidget(self.shelf)
        self.apply_mode()

        QTimer.singleShot(300, self.check_recovery)

    # ------------------------------------------------------------ Aufbau

    def setup_window(self):
        """Initial title and size."""
        self.update_title()
        self.resize(1800, 1000)

    def update_title(self):
        """Window title: book name (+ ``*`` when there are unsaved changes)."""
        if self.on_shelf():
            self.setWindowTitle(tr("AuthorBoard — Bibliothek"))
            return
        if self.current_book:
            name = self.current_book.title
        else:
            name = os.path.basename(self.current_file) if self.current_file else tr("Unbenannt")
        mark = " *" if self.dirty else ""
        self.setWindowTitle("AuthorBoard — " + name + mark)

    def create_canvas(self):

        """Create the board scene/view and the shelf page in a stacked widget."""
        self.scene = BoardScene(self)
        self.scene.note_types = self.note_types
        self.scene.focus_mode = bool(settings.get("focus_mode"))

        self.scene.setSceneRect(-100000, -100000, 200000, 200000)

        self.view = BoardView(self.scene)
        self.shelf = ShelfPage(self.library, self)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.shelf)
        self.stack.addWidget(self.view)
        self.setCentralWidget(self.stack)

    def create_docks(self):

        # --- Notizen: Suche + Filter + Baum ---

        """Create the left Notes dock, the right Inspector/Comments dock and the Timeline dock."""
        panel = QWidget()
        panel.setObjectName("SidePanel")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 10, 10, 0)
        lay.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("Suchen (Titel, Inhalt, Tags, Attribute) …"))
        self.search_edit.setClearButtonEnabled(True)
        lay.addWidget(self.search_edit)

        self.type_filter = QComboBox()
        self.tag_filter = QComboBox()
        self.status_filter = QComboBox()
        self.status_filter.addItem(tr("Alle Status"), "")
        for key, (label, col) in STATUS_INFO.items():
            self.status_filter.addItem(color_icon(col), tr(label), key)

        lay.addWidget(self.type_filter)
        lay.addWidget(self.tag_filter)
        lay.addWidget(self.status_filter)

        self.search_edit.setToolTip(
            tr("Durchsucht Titel, Inhalt, Tags, Attribute und Notizart.\n"
            "Mehrere Wörter müssen alle vorkommen (Strg+F).")
        )
        self.type_filter.setToolTip(tr("Nur Notizen dieser Art hervorheben"))
        self.tag_filter.setToolTip(tr("Nur Notizen mit diesem Tag hervorheben"))
        self.status_filter.setToolTip(tr("Nur Notizen mit diesem Bearbeitungsstatus hervorheben"))

        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setToolTip(tr("Treffer im aktuellen Filter / alle Notizen"))
        lay.addWidget(self.count_label)

        self.tree = QTreeWidget()
        self.tree.setToolTip(tr("Klick wählt die Notiz aus und zentriert das Board darauf"))
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        lay.addWidget(self.tree, 1)

        self.tree_dock = QDockWidget(tr("Notizen"), self)
        self.tree_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)
        self.tree_dock.setMinimumWidth(260)

        # --- Inspector ---

        self.inspector = InspectorWidget(self.attachments)
        self.comments_panel = CommentsPanel()

        # Inspector and Comments share one dock (tabs)
        self.right_panel = RightPanel()
        self.right_panel.addTab(self.inspector, tr("Inspector"))
        self.right_panel.addTab(self.comments_panel, tr("Kommentare"))
        self.right_panel.setToolTip(tr("Zwischen Inspector und Kommentarliste umschalten"))

        self.inspector_dock = QDockWidget(tr("Inspector"), self)
        self.inspector_dock.setWidget(self.right_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)
        self.inspector_dock.setMinimumWidth(390)

        # --- Zeitleiste ---

        self.timeline = TimelineWidget()
        self.timeline_dock = QDockWidget(tr("Zeitleiste"), self)
        self.timeline_dock.setWidget(self.timeline)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.timeline_dock)
        self.timeline_dock.hide()

        self.timeline.note_activated.connect(self.jump_to_note)
        self.timeline_dock.visibilityChanged.connect(
            lambda v: self.refresh_timeline() if v else None
        )

        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        self.search_edit.textChanged.connect(self.on_filter_changed)
        self.type_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.tag_filter.currentIndexChanged.connect(self.on_filter_changed)
        self.status_filter.currentIndexChanged.connect(self.on_filter_changed)

    def _action(self, text, shortcut, slot):
        """Create a QAction with optional shortcut."""
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _tip(self, action, text):
        """Give an action a tool-tip that also appears in the status bar."""
        action.setToolTip(text)
        action.setStatusTip(text)

    def create_menu(self):

        # --- Datei ---
        """Build the menus and the list of actions that only make sense on the board."""
        file_menu = self.menuBar().addMenu(tr("Datei"))

        self.act_shelf = self._action(tr("Bücherregal (Startseite)"), "Ctrl+B", self.show_shelf)
        self.act_new = self._action(tr("Neues Notizbuch …"), "Ctrl+N", self.create_book)
        self.act_open = self._action(tr("Datei öffnen …"), "Ctrl+O", self.load_project)
        self.act_save = self._action(tr("Speichern"), "Ctrl+S", self.save_project)
        self.act_save_as = self._action(
            tr("Kopie speichern unter …"), "Ctrl+Shift+S", self.save_project_as
        )
        self.act_book_info = self._action(
            tr("Notizbuch-Info …"), None, self.edit_book_info
        )
        self.act_backup = self._action(
            tr("Sicherung laden …"), None, self.load_backup
        )

        file_menu.addAction(self.act_shelf)
        file_menu.addSeparator()
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addAction(self.act_book_info)
        file_menu.addAction(self.act_backup)
        file_menu.addSeparator()

        export_menu = file_menu.addMenu(tr("Exportieren"))
        self.act_export_ms = self._action(
            tr("Manuskript (Kapitel/Szenen) …"), None, self.export_manuscript
        )
        self.act_export_md = self._action(
            tr("Gliederung als Markdown …"), None, self.export_markdown
        )
        self.act_export_png = self._action(
            tr("Board als Bild (PNG) …"), None, self.export_png
        )
        export_menu.addAction(self.act_export_ms)
        export_menu.addAction(self.act_export_md)
        export_menu.addAction(self.act_export_png)

        file_menu.addSeparator()
        file_menu.addAction(self._action(tr("Beenden"), "Ctrl+Q", self.close))

        # --- Bearbeiten ---
        edit_menu = self.menuBar().addMenu(tr("Bearbeiten"))

        self.act_undo = self._action(tr("Rückgängig"), "Ctrl+Z", self.undo)
        self.act_redo = self._action(tr("Wiederholen"), None, self.redo)
        self.act_redo.setShortcuts(
            [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")]
        )

        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()

        # Das Kürzel Shift+Leertaste wird per Event-Filter behandelt
        # (damit man in Textfeldern weiter normal tippen kann).
        self.act_palette = self._action(
            tr("Notizart suchen …\tShift+Leertaste"), None, self.open_palette
        )
        self.act_duplicate = self._action(
            tr("Notiz duplizieren"), "Ctrl+D", self.duplicate_selected
        )
        self.act_editor = self._action(
            tr("Notiz im großen Editor öffnen"), "F2", self.open_editor
        )
        self.act_find = self._action(tr("Suche im Board"), "Ctrl+F", self.focus_search)

        edit_menu.addAction(self.act_palette)
        edit_menu.addAction(self.act_duplicate)
        edit_menu.addAction(self.act_editor)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_find)

        # --- Ansicht ---
        view_menu = self.menuBar().addMenu(tr("Ansicht"))
        self.act_fit = self._action(tr("Alles anzeigen"), "Ctrl+0", self.view.fit_all)
        self.act_zoom = self._action(tr("Zoom zurücksetzen"), "Ctrl+1", self.view.reset_zoom)
        self.act_arrange = self._action(tr("Nach Notizart anordnen"), None, self.arrange_notes)
        self.act_stats = self._action(tr("Statistik …"), "Ctrl+I", self.show_stats)

        view_menu.addAction(self.act_fit)
        view_menu.addAction(self.act_zoom)
        view_menu.addSeparator()
        view_menu.addAction(self.act_arrange)

        self.act_snap = QAction(tr("Am Raster ausrichten"), self)
        self.act_snap.setCheckable(True)
        self.act_snap.toggled.connect(self.set_snap)
        view_menu.addAction(self.act_snap)

        view_menu.addSeparator()
        self.lang_menu = view_menu.addMenu(tr("Sprache"))
        self.lang_menu.menuAction().setToolTip(tr("Sprache der Oberfläche wechseln"))
        self._lang_group = QActionGroup(self)
        self._lang_actions = {}
        for code, name in i18n.available_languages().items():
            act = QAction(name, self)
            act.setCheckable(True)
            act.setChecked(code == i18n.current_language())
            act.triggered.connect(lambda _=False, c=code: self.switch_language(c))
            self._lang_group.addAction(act)
            self.lang_menu.addAction(act)
            self._lang_actions[code] = act

        view_menu.addSeparator()
        self.act_timeline = self.timeline_dock.toggleViewAction()
        self.act_timeline.setText(tr("Zeitleiste"))
        view_menu.addAction(self.act_timeline)
        view_menu.addAction(self.act_stats)

        # --- extra actions: lock, focus mode, settings, help ---
        self.act_lock = self._action(tr("Notiz sperren / entsperren"), "Ctrl+L", self.toggle_lock_selected)
        self.act_settings = self._action(tr("Einstellungen …"), "Ctrl+,", self.open_settings)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_lock)
        edit_menu.addAction(self.act_settings)

        self.act_focus = QAction(tr("Fokus-Modus"), self)
        self.act_focus.setCheckable(True)
        self.act_focus.setChecked(bool(settings.get("focus_mode")))
        self.act_focus.toggled.connect(self.set_focus_mode)
        view_menu.addAction(self.act_focus)

        help_menu = self.menuBar().addMenu(tr("Hilfe"))
        self.act_help = self._action(tr("Dokumentation"), "F1", self.open_help)
        self.act_about = self._action(tr("Über AuthorBoard …"), None, self.open_about)
        help_menu.addAction(self.act_help)
        help_menu.addSeparator()
        help_menu.addAction(self.act_about)

        self._tip(self.act_lock, tr("Gesperrte Notizen bleiben an ihrem Platz (Strg+L)"))
        self._tip(self.act_settings, tr("Rechtschreibung, Notizarten, Fokus-Modus und mehr (Strg+,)"))
        self._tip(self.act_focus, tr("Bei ausgewählter Notiz nur verbundene Notizen und Fäden hervorheben"))
        self._tip(self.act_help, tr("Durchsuchbare Dokumentation öffnen (F1)"))
        self._tip(self.act_about, tr("Version, Lizenz und Hinweise zur Software"))

        # Aktionen, die nur im Board sinnvoll sind
        self.board_actions = [
            self.act_save, self.act_save_as, self.act_book_info, self.act_backup,
            self.act_export_ms, self.act_export_md, self.act_export_png,
            self.act_palette, self.act_duplicate, self.act_editor, self.act_find,
            self.act_fit, self.act_zoom, self.act_arrange, self.act_snap,
            self.act_stats, self.act_timeline, self.act_lock, self.act_focus,
        ]

        self._tip(self.act_shelf, tr("Zurück zur Startseite mit dem Bücherregal (Strg+B)"))
        self._tip(self.act_new, tr("Neues Notizbuch anlegen (Strg+N)"))
        self._tip(self.act_open, tr("Beliebige Board-Datei öffnen (Strg+O)"))
        self._tip(self.act_save, tr("Notizbuch speichern (Strg+S)"))
        self._tip(self.act_save_as, tr("Eine Kopie des Boards als Datei speichern (Strg+Umschalt+S)"))
        self._tip(self.act_book_info, tr("Titel, Autor, Genre, Wortziel und eigene Felder des Notizbuchs bearbeiten"))
        self._tip(self.act_backup, tr("Eine ältere automatische Sicherung zurückholen"))
        self._tip(self.act_export_ms, tr("Kapitel und Szenen in Reihenfolge als Manuskript exportieren"))
        self._tip(self.act_export_md, tr("Gliederung aller Notizen als Markdown-Datei exportieren"))
        self._tip(self.act_export_png, tr("Das ganze Board als Bild speichern"))
        self._tip(self.act_undo, tr("Letzte Änderung rückgängig machen (Strg+Z)"))
        self._tip(self.act_redo, tr("Rückgängig gemachte Änderung wiederholen (Strg+Y)"))
        self._tip(self.act_palette, tr("Notizart suchen und neue Notiz anlegen (Umschalt+Leertaste)"))
        self._tip(self.act_duplicate, tr("Ausgewählte Notizen kopieren (Strg+D)"))
        self._tip(self.act_editor, tr("Notiz in einem großen Editor mit Wortzähler öffnen (F2)"))
        self._tip(self.act_find, tr("Ins Suchfeld springen (Strg+F)"))
        self._tip(self.act_fit, tr("Zoom so wählen, dass alle Notizen sichtbar sind (Strg+0)"))
        self._tip(self.act_zoom, tr("Zoom auf 100 % zurücksetzen (Strg+1)"))
        self._tip(self.act_arrange, tr("Notizen in Spalten nach Notizart ordnen, Kapitel nach Nummer"))
        self._tip(self.act_snap, tr("Notizen beim Verschieben am Raster einrasten lassen"))
        self._tip(self.act_stats, tr("Wörter, Notizarten, Status und Schreibziel auswerten (Strg+I)"))
        self._tip(self.act_timeline, tr("Notizen mit Datum auf einer horizontalen Zeitleiste anzeigen"))

        self.update_undo_actions()

    def create_toolbar(self):

        """Build the toolbar."""
        bar = QToolBar(tr("Werkzeuge"))
        bar.setMovable(False)
        self.addToolBar(bar)

        bar.addAction(self.act_shelf)
        bar.addAction(self.act_new)
        bar.addAction(self.act_save)
        bar.addSeparator()
        bar.addAction(self.act_undo)
        bar.addAction(self.act_redo)
        bar.addSeparator()
        self.act_add_note = self._action(tr("＋ Notiz   (Shift+Leertaste)"), None, self.open_palette)
        self._tip(self.act_add_note, tr("Notizart suchen und neue Notiz anlegen (Umschalt+Leertaste)"))
        bar.addAction(self.act_add_note)
        bar.addAction(self.act_fit)
        self.board_actions.append(self.act_add_note)

    def apply_theme(self):
        """Apply the dark style sheet."""
        self.setStyleSheet(STYLESHEET)

    # ----------------------------------------------------- Event-Filter

    def eventFilter(self, obj, event):

        """Qt: filter events of another object (return True to swallow them)."""
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Space
            and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            and not (event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
            ))
            and not event.isAutoRepeat()
            and QApplication.activeWindow() is self
            and not self.on_shelf()
            and not self._text_input_focused()
        ):
            self.open_palette()
            return True

        return super().eventFilter(obj, event)

    def _text_input_focused(self):
        """True when a text field has the focus (then Shift+Space must type a space)."""
        w = QApplication.focusWidget()
        return isinstance(
            w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
        ) or (isinstance(w, QComboBox) and w.isEditable())

    # ------------------------------------------------ Undo / Redo / Dirty

    def _snapshot(self):
        """Build a Snapshot with structural sharing against the previous one."""
        project = self.build_project_data(for_file=False)
        notes_json, conn_json, meta_json = Storage.snapshot_parts(
            project, self._note_json_cache
        )
        # Update the cache with the new (id -> (json, signature)) mapping.
        # The signature is just the JSON itself; identity comparison is what
        # matters for sharing, and the dict keeps the same string objects.
        self._note_json_cache = {
            nid: (js, js) for nid, js in notes_json.items()
        }
        return Snapshot(notes_json, conn_json, meta_json)

    def capture_state(self):
        """Serialise the board for undo / dirty detection (structural sharing)."""
        project = self.build_project_data(for_file=False)
        notes_json, conn_json, meta_json = Storage.snapshot_parts(
            project, self._note_json_cache)
        self._note_json_cache = {nid: (js, js) for nid, js in notes_json.items()}
        return Snapshot(notes_json, conn_json, meta_json)

    def schedule_checkpoint(self, *_):
        """Request an undo checkpoint shortly after the last change (debounced)."""
        if self._restoring:
            return
        self._checkpoint_timer.start()
        self.update_undo_actions()

    def checkpoint(self):
        """Aktuellen Zustand in den Verlauf aufnehmen (falls verändert)."""
        self._checkpoint_timer.stop()
        if self._restoring:
            return
        self.undo_stack.push(self.capture_state())
        self.update_undo_actions()
        self.update_dirty()

    def _on_interaction_finished(self):
        """Mouse released: checkpoint only if the state actually changed."""
        snap = self.capture_state()
        cur = self.undo_stack.current
        if cur is None or not cur.equal(snap):
            self._checkpoint_timer.start()

    def update_dirty(self):
        """Compare the current state with the saved state."""
        cur = self.undo_stack.current
        self.dirty = self.saved_state is None or not cur.equal(self.saved_state)
        self.update_title()

    def update_undo_actions(self):
        """Enable/disable Undo and Redo."""
        board = not self.on_shelf()
        pending = self._checkpoint_timer.isActive()
        self.act_undo.setEnabled(board and (self.undo_stack.can_undo() or pending))
        self.act_redo.setEnabled(board and self.undo_stack.can_redo() and not pending)

    def undo(self):
        """Step back in the history."""
        self.checkpoint()
        state = self.undo_stack.undo()
        if state is not None:
            self.apply_state(state)
            self.statusBar().showMessage(tr("Rückgängig"), 2000)

    def redo(self):
        """Step forward in the history."""
        self.checkpoint()
        state = self.undo_stack.redo()
        if state is not None:
            self.apply_state(state)
            self.statusBar().showMessage(tr("Wiederholt"), 2000)

    def reset_history(self):
        """Start a fresh history (after loading a book)."""
        self._note_json_cache = {}
        state = self.capture_state()
        self.undo_stack.reset(state)
        self.saved_state = state
        self.update_undo_actions()
        self.update_dirty()

    def apply_state(self, state):
        """Rebuild the board from a snapshot, changing only the notes that differ."""
        from models import ConnectionData, NoteTypeData

        selected = [i.model.id for i in self.scene.selectedItems()
                    if isinstance(i, NoteItem)]
        old = self.undo_stack.current
        changed = state.changed_note_ids(old) if old is not None else set(state.notes)

        self._restoring = True
        try:
            for nid in list(changed):
                item = self.scene.note_lookup.get(nid)
                if item is not None:
                    self.scene.remove_note(item)
            for nid in changed:
                js = state.notes.get(nid)
                if js is None:
                    continue
                nd = Storage.from_dict({
                    "version": FORMAT_VERSION,
                    "notes": [json.loads(js)],
                    "connections": [],
                }).notes[0]
                if nd.note_type not in self.note_types:
                    self.note_types[nd.note_type] = NoteTypeData(
                        nd.note_type, nd.note_type, nd.color)
                self.scene.add_note_item(nd)
            for c in list(self.scene.connection_items):
                self.scene.remove_connection(c)
            for cd in (json.loads(state.connections) if state.connections else []):
                start = self.scene.pin_lookup.get(cd["start_pin_id"])
                end = self.scene.pin_lookup.get(cd["end_pin_id"])
                if start is None or end is None:
                    continue
                self.scene.add_connection(
                    ConnectionData(
                        id=cd["id"], start_pin_id=cd["start_pin_id"],
                        end_pin_id=cd["end_pin_id"],
                        color=cd.get("color", ""), label=cd.get("label", ""),
                    ), start, end)
            self.scene.clearSelection()
            for note_id in selected:
                note = self.scene.note_lookup.get(note_id)
                if note is not None:
                    note.setSelected(True)
        finally:
            self._restoring = False

        self._note_json_cache = {nid: (js, js) for nid, js in state.notes.items()}
        self.schedule_refresh()
        self.update_undo_actions()
        self.update_dirty()

    # ------------------------------------------- Ungespeicherte Änderungen

    def maybe_save(self):
        """True, wenn fortgefahren werden darf (gespeichert/verworfen)."""
        self.checkpoint()
        if not self.dirty:
            return True

        name = (
            self.current_book.title if self.current_book
            else os.path.basename(self.current_file) if self.current_file
            else tr("Unbenannt")
        )

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("Ungespeicherte Änderungen"))
        box.setText(tr("Möchtest du die Änderungen an „{name}“ speichern?", name=name))
        box.setInformativeText(tr("Sonst gehen deine Änderungen verloren."))

        save = box.addButton(tr("Speichern"), QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton(tr("Verwerfen"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Abbrechen"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)

        box.exec()
        clicked = box.clickedButton()

        if clicked is save:
            self.save_project()
            return not self.dirty

        return clicked is discard

    def switch_language(self, code):
        """Sprache wechseln: neues Hauptfenster in der neuen Sprache öffnen."""

        if code == i18n.current_language():
            return

        book = self.current_book
        legacy_file = None

        if not self.on_shelf():
            if not self.maybe_save():
                self._lang_actions[i18n.current_language()].setChecked(True)
                return
            self.finish_book()
            self.clear_autosave()
            if book is None:
                legacy_file = self.current_file

        QSettings(SETTINGS_ORG, SETTINGS_APP).setValue("language", code)
        i18n.set_language(code)
        install_qt_translation(QApplication.instance(), code)

        new = MainWindow()
        new.setGeometry(self.geometry())
        new.show()
        _windows.append(new)

        if book is not None:
            found = next((b for b in new.library.books if b.id == book.id), None)
            if found is not None:
                new.open_book(found)
        elif legacy_file and os.path.exists(legacy_file):
            new.load_file(legacy_file)
            new.show_board()

        self._closing_for_switch = True
        self.close()

    def _teardown(self):
        """Stop timers and remove the global event filter before closing."""
        QApplication.instance().removeEventFilter(self)
        self._autosave_timer.stop()
        if self in _windows:
            _windows.remove(self)

    def closeEvent(self, event):

        """Qt event handler: the window is closing."""
        if self._closing_for_switch:
            self._teardown()
            event.accept()
            return

        if self.on_shelf():
            self.library.save()
            self._teardown()
            event.accept()
            return

        if self.maybe_save():
            self.finish_book()
            self.clear_autosave()
            self._teardown()
            event.accept()
        else:
            event.ignore()

    # ---------------------------------------------------- Autosave

    def autosave_path(self):
        """Where the recovery copy of the current board is written."""
        if self.current_file:
            return self.current_file + ".autosave"
        return RECOVERY_PATH

    def autosave(self):
        """Timer: write a recovery copy when there are unsaved changes.

        Building the dict must happen on the UI thread (it reads the scene).
        The JSON write itself runs on a worker thread so the app doesn't
        freeze while 2–20 MB of JSON is serialised.  Overlapping requests are
        dropped: if a previous autosave is still in flight, the timer skips
        this tick and waits for the next one.
        """
        if self.on_shelf():
            return

        self.checkpoint()

        if not self.dirty:
            return

        if self._autosave_in_flight:
            return

        try:
            data = Storage.to_dict(self.build_project_data())
        except Exception:
            return

        self._autosave_in_flight = True
        worker = _AutosaveWorker(data, self.autosave_path())
        self._autosave_pool.start(worker)

        # Reset the in-flight flag once the worker is finished.
        # QThreadPool has no per-runner finished signal, so poll: cheap
        # because it only fires on the autosave timer (every 2 min).
        QTimer.singleShot(500, self._poll_autosave_done)

    def _poll_autosave_done(self):
        """Reset ``_autosave_in_flight`` when the pool is idle again."""
        if self._autosave_pool.activeThreadCount() == 0:
            self._autosave_in_flight = False
        else:
            QTimer.singleShot(500, self._poll_autosave_done)

    def clear_autosave(self):
        """Delete recovery copies (after saving or leaving)."""
        self._autosave_in_flight = False
        # Wait briefly for any in-flight autosave to finish, so it doesn't
        # recreate the file after we delete it.  This happens on save / leave,
        # not on a hot path.
        self._autosave_pool.waitForDone(2000)
        paths = [RECOVERY_PATH]
        if self.current_file:
            paths.append(self.current_file + ".autosave")
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def check_recovery(self):

        """At startup: offer to restore a recovery file of a crashed session."""
        if not os.path.exists(RECOVERY_PATH) or self.scene.note_lookup:
            return

        answer = QMessageBox.question(
            self,
            tr("Wiederherstellung"),
            tr("Es wurde eine automatische Sicherung einer nicht gespeicherten "
            "Sitzung gefunden.\nWiederherstellen?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.restore_project(Storage.load(RECOVERY_PATH))
            except Exception as error:
                QMessageBox.critical(self, tr("Fehler beim Laden"), str(error))
                return
            self.reset_history()
            self.saved_state = None      # als „geändert“ markieren
            self.update_dirty()
            self.show_board()
        else:
            self.clear_autosave()

    # --------------------------------------------------- Notizarten

    def refresh_type_combo(self):

        """Refill the 'note type' filter combo."""
        current = self.type_filter.currentData()

        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(tr("Alle Notizarten"), "")

        for t in self.note_types.values():
            self.type_filter.addItem(color_icon(t.color), t.label, t.key)

        idx = self.type_filter.findData(current if current else "")
        self.type_filter.setCurrentIndex(max(idx, 0))
        self.type_filter.blockSignals(False)

    def register_custom_type(self, label):

        """Create a book note type from the command palette."""
        for t in self.note_types.values():
            if t.label.lower() == label.lower():
                return t.key

        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "type"
        key = f"custom_{slug}"

        n = 2
        while key in self.note_types:
            key = f"custom_{slug}_{n}"
            n += 1

        color = CUSTOM_TYPE_COLORS[
            (len(self.note_types) - len(BUILTIN_NOTE_TYPES))
            % len(CUSTOM_TYPE_COLORS)
        ]

        self.note_types[key] = NoteTypeData(key, label, color)

        self.inspector.set_types(self.note_types)
        self.refresh_type_combo()

        return key

    def open_palette(self):

        """Show the Shift+Space palette and create the chosen note."""
        dialog = CommandPalette(self.note_types, self)

        if dialog.exec() != CommandPalette.DialogCode.Accepted:
            return

        key = dialog.selected_key

        if dialog.new_label:
            key = self.register_custom_type(dialog.new_label)

        if key:
            self.scene.create_note(key, self.cursor_scene_pos())

    def cursor_scene_pos(self):

        """Scene position under the mouse (or the view centre)."""
        vp = self.view.viewport()
        p = vp.mapFromGlobal(QCursor.pos())

        if not vp.rect().contains(p):
            p = vp.rect().center()

        return self.view.mapToScene(p)

    def focus_search(self):
        """Ctrl+F: focus the search field."""
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # --------------------------------------------- Autoren-Funktionen

    def selected_notes(self):
        """The selected NoteItems."""
        return [i for i in self.scene.selectedItems() if isinstance(i, NoteItem)]

    def duplicate_selected(self):

        """Ctrl+D: duplicate the selected notes."""
        notes = self.selected_notes()

        if not notes:
            self.statusBar().showMessage(tr("Keine Notiz ausgewählt."), 3000)
            return

        copies = [self.scene.duplicate_note(n) for n in notes]

        self.scene.clearSelection()
        for c in copies:
            c.setSelected(True)

    def open_editor(self, note=None, focus_comment=None):
        """Open the full-size editor for ``note`` (default: the inspected note).

        ``focus_comment`` is a comment id: the editor selects the commented words."""

        if not isinstance(note, NoteItem):
            note = self.inspector.note

        if note is None:
            self.statusBar().showMessage(tr("Keine Notiz ausgewählt."), 3000)
            return

        dialog = NoteEditorDialog(note.model, self.attachments, self,
                                  focus_comment=focus_comment if isinstance(focus_comment, str) else None)

        if dialog.exec() != NoteEditorDialog.DialogCode.Accepted:
            return

        m = note.model
        m.title = dialog.result_title()
        m.content = dialog.result_content()
        m.rich = dialog.result_rich()
        m.comments[:] = dialog.result_comments()
        m.attachments = dialog.result_attachments()
        note.model.touch()
        note.update()

        if self.inspector.note is note:
            self.inspector.set_note(note)

        self.schedule_refresh()
        self.schedule_checkpoint()

    def delete_comment(self, note, comment_id):
        """Delete a comment (from the comments panel) incl. its text marker."""
        m = note.model
        m.comments[:] = [c for c in m.comments if c.id != comment_id]
        if m.rich:
            m.rich = remove_comment_marker(m.rich, comment_id)
            m.touch()
        note.update()
        if self.inspector.note is note:
            self.inspector.set_note(note)
        self.schedule_refresh()
        self.schedule_checkpoint()

    def remember_tags(self, tags):
        """Add finished tags to the book's auto-completion memory."""
        before = len(self.known_tags)
        self.known_tags.update(tags)
        if len(self.known_tags) != before:
            self.inspector.set_known_tags(sorted(self.known_tags))

    def toggle_lock_selected(self):
        """Ctrl+L: lock the selected notes (or unlock them if all are locked)."""
        notes = self.selected_notes()
        if not notes:
            self.statusBar().showMessage(tr("Keine Notiz ausgewählt."), 3000)
            return
        target = not all(n.model.locked for n in notes)
        for n in notes:
            self.scene.set_note_locked(n, target)

    def set_focus_mode(self, on):
        """View menu: toggle focus mode and remember the choice."""
        self.scene.set_focus_mode(on)
        settings.set("focus_mode", on)

    # ---------------------------------------------------- Settings / Help / About

    def book_type_list(self):
        """Note types that belong to the open notebook only."""
        return [t for t in self.note_types.values()
                if t.key not in BUILTIN_TYPE_KEYS and not t.key.startswith(GLOBAL_PREFIX)]

    def open_settings(self):
        """Show the settings window and apply its result."""

        usage = Counter(n.model.note_type for n in self.scene.note_lookup.values())
        dialog = SettingsDialog(
            self.book_type_list(), settings.global_types(), usage,
            [t.label for t in builtin_note_types()],
            book_open=not self.on_shelf(), parent=self)

        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        dialog.apply_general()
        settings.set_global_types(dialog.global_types())
        book_types = dialog.book_types()
        if book_types is None:
            book_types = self.book_type_list()
        self.reset_types(book_types, keep_unknown=True)

        # side effects of the general settings
        self.act_focus.setChecked(bool(settings.get("focus_mode")))
        self.scene.set_focus_mode(bool(settings.get("focus_mode")))
        self._autosave_timer.setInterval(int(settings.get("autosave_minutes") or 2) * 60_000)
        engine.clear_cache()
        self.inspector.content_edit.refresh_spelling()

        self.scene.update()
        self.refresh_views()
        self.schedule_checkpoint()

    def open_help(self):
        """Open (or raise) the documentation window."""
        if self._help is None:
            self._help = HelpDialog(self)
        self._help.show()
        self._help.raise_()
        self._help.activateWindow()

    def open_about(self):
        """Show the About dialog."""
        AboutDialog(self, self.open_help).exec()

    def jump_to_note(self, note):

        """Select a note and centre the board on it."""
        if note is None or note.scene() is not self.scene:
            return

        self.scene.clearSelection()
        note.setSelected(True)
        self.view.centerOn(note)

    def focus_note_from_comment(self, note):
        """Single-click in the Comments panel: select the note and centre the
        board on it.  The inspector updates automatically because the
        selection changed."""
        if note is None or note.scene() is not self.scene:
            return
        self.scene.clearSelection()
        note.setSelected(True)
        self.view.centerOn(note)

    def arrange_notes(self):
        """Arrange notes in columns by type, then fit the view."""
        self.scene.arrange_by_type()
        self.view.fit_all()

    def set_snap(self, on):
        """Toggle snapping to the grid."""
        self.scene.snap_to_grid = on

    def export_markdown(self):

        """File -> Export -> Outline as Markdown."""
        base = os.path.splitext(self.current_file)[0] if self.current_file else tr("Board")

        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Gliederung exportieren"), base + ".md", "Markdown (*.md)"
        )

        if not filename:
            return

        title = os.path.basename(base)
        text = build_markdown(
            list(self.scene.note_lookup.values()), self.note_types, title
        )

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as error:
            QMessageBox.critical(self, tr("Fehler beim Export"), str(error))
            return

        self.statusBar().showMessage(tr("Exportiert: {path}", path=filename), 5000)

    def export_png(self):

        """File -> Export -> Board as image."""
        rect = self.scene.content_rect()

        if rect is None:
            self.statusBar().showMessage(tr("Das Board ist leer."), 3000)
            return

        base = os.path.splitext(self.current_file)[0] if self.current_file else tr("Board")

        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Board als Bild exportieren"), base + ".png", "PNG (*.png)"
        )

        if not filename:
            return

        rect = rect.adjusted(-60, -60, 60, 60)

        scale = 2.0
        while rect.width() * scale > 9000 or rect.height() * scale > 9000:
            scale /= 2

        image = QImage(
            max(1, int(rect.width() * scale)),
            max(1, int(rect.height() * scale)),
            QImage.Format.Format_ARGB32,
        )
        image.fill(QColor("#15161a"))

        # Auswahlrahmen nicht mitrendern
        selected = list(self.scene.selectedItems())
        self.scene.blockSignals(True)
        self.scene.clearSelection()

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.scene.render(painter, QRectF(image.rect()), rect)
        painter.end()

        for item in selected:
            item.setSelected(True)
        self.scene.blockSignals(False)

        if not image.save(filename):
            QMessageBox.critical(self, tr("Fehler beim Export"), tr("Bild konnte nicht gespeichert werden."))
            return

        self.statusBar().showMessage(tr("Exportiert: {path}", path=filename), 5000)

    # ------------------------------------------------- Baum / Filter

    def current_filter(self):
        """(search text, type, tag, status) from the filter widgets."""
        return (
            self.search_edit.text(),
            self.type_filter.currentData() or "",
            self.tag_filter.currentData() or "",
            self.status_filter.currentData() or "",
        )

    def schedule_refresh(self, *_):
        """Refresh derived views shortly after changes (debounced)."""
        # Anything that changed invalidates all derived views
        for k in self._dirty_flags:
            self._dirty_flags[k] = True
        self._refresh_timer.start()

    def on_filter_changed(self, *_):
        """A filter widget changed: re-filter board and tree."""
        self.scene.set_filter(*self.current_filter())
        self.refresh_tree()

    def refresh_views(self):
        """Refresh everything that is derived from the notes, using dirty flags."""
        flags = self._dirty_flags
        if flags["tags"]:
            self.refresh_tag_combo()
            flags["tags"] = False
        self.scene.set_filter(*self.current_filter())
        if flags["tree"]:
            self.refresh_tree()
            flags["tree"] = False
        if flags["links"]:
            self.inspector.refresh_links()
            flags["links"] = False
        if flags["stats"]:
            self.update_stats_label()
            flags["stats"] = False
        if flags["timeline"] and self.timeline_dock.isVisible():
            self.refresh_timeline()
            flags["timeline"] = False
        if flags["aux"]:
            self.refresh_aux()
            flags["aux"] = False

    def refresh_aux(self):
        """Housekeeping after every change: orphan comments, spell vocabulary,
        tag suggestions and the comments panel."""
        notes = list(self.scene.note_lookup.values())

        pruned = False
        for n in notes:
            m = n.model
            if m.comments:
                keep = [c for c in m.comments if COMMENT_PREFIX + c.id in (m.rich or "")]
                if len(keep) != len(m.comments):
                    m.comments[:] = keep
                    pruned = True

        engine.set_book_words([n.model.title for n in notes]
                              + [t for n in notes for t in n.model.tags])
        self.inspector.set_known_tags(sorted(self.known_tags))
        self.comments_panel.set_notes(notes)
        self.right_panel.setTabText(
            1, tr("Kommentare") + (f" ({self.comments_panel.total()})" if self.comments_panel.total() else ""))

        if pruned:
            self.schedule_checkpoint()

    def refresh_tag_combo(self):

        """Refill the tag filter combo from the tags in use."""
        current = self.tag_filter.currentData() or ""

        tags = {}
        for note in self.scene.note_lookup.values():
            for tag in note.model.tags:
                tags.setdefault(tag.lower(), tag)

        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem(tr("Alle Tags"), "")

        for low in sorted(tags):
            self.tag_filter.addItem(f"#{tags[low]}", tags[low])

        idx = self.tag_filter.findData(current)
        self.tag_filter.setCurrentIndex(max(idx, 0))
        self.tag_filter.blockSignals(False)

    def refresh_tree(self):
        """Rebuild the left tree incrementally.

        The tree is only rebuilt from scratch when the filter widgets change
        (``on_filter_changed``); every other update re-uses the existing
        ``QTreeWidgetItem`` per note and only adds/removes/updates the ones
        whose ``NoteData._revision`` changed.  Group items are kept across
        refreshes, so the tree keeps scroll position and expansion state.
        """
        # --- 1. Which notes match the current filter? ---
        matching = {}
        for note in self.scene.note_lookup.values():
            if self.scene.note_matches(note):
                matching[note.model.id] = note

        # --- 2. Remove items for notes that are gone or no longer match ---
        for nid in list(self._tree_items):
            item, _rev, _pkey = self._tree_items[nid]
            if nid not in matching:
                parent = item.parent()
                if parent is not None:
                    parent.removeChild(item)
                del self._tree_items[nid]

        # --- 3. Add / update items for matching notes ---
        groups = {}   # type_key -> group item
        new_items = {}

        for nid, note in matching.items():
            key = note.model.note_type

            # Create or fetch the group item for this type.
            group = groups.get(key) or self._tree_groups.get(key)
            if group is None:
                info = self.note_types.get(key)
                group = QTreeWidgetItem([info.label if info else key])
                group.setIcon(0, color_icon(info.color if info else "#888888"))
                group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.tree.addTopLevelItem(group)
            groups[key] = group

            old = self._tree_items.get(nid)
            rev = note.model._revision

            if old is not None and old[1] == rev and old[2] == key:
                # Unchanged: reuse the item as-is.
                new_items[nid] = old
                continue

            if old is not None:
                # Item exists but the note (or its group) changed: update in place.
                item = old[0]
                if old[2] != key:
                    # Type changed: move to a different parent.
                    old_parent = item.parent()
                    if old_parent is not None:
                        old_parent.removeChild(item)
                    group.addChild(item)
            else:
                item = QTreeWidgetItem([""])
                group.addChild(item)

            # Update text + icon + tooltip from the note.
            item.setText(0, note.model.title or tr("Ohne Titel"))
            st = STATUS_INFO.get(note.model.status)
            if st:
                item.setIcon(0, color_icon(st[1], 10))
            else:
                item.setIcon(0, QIcon())
            if note.model.tags:
                item.setToolTip(0, "  ".join(f"#{t}" for t in note.model.tags))
            else:
                item.setToolTip(0, "")
            item.setData(0, Qt.ItemDataRole.UserRole, nid)

            new_items[nid] = (item, rev, key)

        # Drop empty groups (all their notes were filtered out).
        for key in list(self._tree_groups):
            group = self._tree_groups[key]
            if group.childCount() == 0 and key not in groups:
                idx = self.tree.indexOfTopLevelItem(group)
                if idx >= 0:
                    self.tree.takeTopLevelItem(idx)
                del self._tree_groups[key]

        # Reorder top-level groups to match note_types order.
        order = list(self.note_types.keys()) + [
            k for k in groups if k not in self.note_types
        ]
        for i, key in enumerate(order):
            group = groups.get(key) or self._tree_groups.get(key)
            if group is None:
                continue
            current = self.tree.indexOfTopLevelItem(group)
            if current != i:
                self.tree.takeTopLevelItem(current)
                self.tree.insertTopLevelItem(i, group)
            self._tree_groups[key] = group

        # Update group labels with counts.
        for key, group in self._tree_groups.items():
            info = self.note_types.get(key)
            label = info.label if info else key
            group.setText(0, f"{label}  ({group.childCount()})")

        self._tree_items = new_items

        # Signals blocked during the update; new selection gets set by
        # the caller (on_note_selected / select_in_tree).
        keep = self.inspector.note.model.id if self.inspector.note else None
        if keep:
            self.select_in_tree(keep)

        total = len(self.scene.note_lookup)
        shown = len(new_items)
        self.count_label.setText(tr("{shown} von {total} Notizen", shown=shown, total=total))

    def select_in_tree(self, note_id):

        """Highlight a note in the tree."""
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == note_id:
                    self.tree.blockSignals(True)
                    self.tree.setCurrentItem(child)
                    self.tree.blockSignals(False)
                    return

        self.tree.blockSignals(True)
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)

    def on_note_selected(self, note):

        """The scene's selection changed: show the note in the inspector."""
        QTimer.singleShot(0, self.view.unsetCursor)
        self.inspector.set_note(note)

        if note is not None:
            self.select_in_tree(note.model.id)
        else:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(None)
            self.tree.blockSignals(False)

    def on_tree_item_clicked(self, item, column):

        """Tree click: select the note and centre the board on it."""
        note_id = item.data(0, Qt.ItemDataRole.UserRole)
        note = self.scene.note_lookup.get(note_id)

        if not note:
            return

        self.scene.clearSelection()
        note.setSelected(True)
        self.view.centerOn(note)

    def confirm_delete_note(self, note):

        """Ask before deleting a note via the inspector button."""
        answer = QMessageBox.question(
            self,
            tr("Notiz löschen"),
            tr("„{title}“ wirklich löschen?",
               title=note.model.title or tr("Ohne Titel")),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.scene.remove_note(note)

    # ------------------------------------------------ Regal / Notizbücher

    def on_shelf(self):
        """True while the bookshelf (not a board) is shown."""
        stack = getattr(self, "stack", None)
        return stack is not None and stack.currentWidget() is self.shelf

    def apply_mode(self):
        """Enable/disable actions and the status label for bookshelf vs. board."""
        shelf = self.on_shelf()
        for a in self.board_actions:
            a.setEnabled(not shelf)
        self.stats_label.setVisible(not shelf)
        self.update_undo_actions()
        self.update_title()

    def _hide_docks(self):
        """Hide all docks (bookshelf mode)."""
        for d in (self.tree_dock, self.inspector_dock, self.timeline_dock):
            d.hide()

    def _remember_docks(self):
        """Remember which docks are visible."""
        self._dock_vis = {
            d: d.isVisible()
            for d in (self.tree_dock, self.inspector_dock, self.timeline_dock)
        }

    def _restore_docks(self):
        """Show the remembered docks again."""
        for d, visible in self._dock_vis.items():
            d.setVisible(visible)

    def show_board(self):
        """Switch the central widget to the board."""
        self.stack.setCurrentWidget(self.view)
        self._restore_docks()
        self.apply_mode()
        self.view.setFocus()

    def show_shelf(self):
        """Zurück zum Regal (fragt bei ungespeicherten Änderungen)."""

        if self.on_shelf():
            return True

        if not self.maybe_save():
            return False

        self.finish_book()
        self.clear_autosave()

        self._remember_docks()
        self._hide_docks()

        self.reset_types([])
        self.scene.reset()
        self.attachments.replace_all({})
        self.known_tags = set()
        self.current_book = None
        self.current_file = None
        self.reset_history()
        self.refresh_views()

        self.stack.setCurrentWidget(self.shelf)
        self.shelf.refresh()
        self.apply_mode()
        return True

    def finish_book(self):
        """Statistik des Notizbuchs ins Regal übernehmen."""

        if self.current_book is not None and not self.dirty:
            self.library.update_stats(
                self.current_book, len(self.scene.note_lookup), self.total_words()
            )
        self.library.save()

    def create_book(self, category_id=""):

        """Ask for book info and open the new notebook."""
        if not isinstance(category_id, str):
            category_id = ""

        if not self.show_shelf():
            return

        book = self.library.new_book(category_id)
        dialog = BookInfoDialog(book, self.library.categories, self, creating=True)

        if dialog.exec() != BookInfoDialog.DialogCode.Accepted:
            return

        dialog.apply(book)
        self.library.add_book(book)
        self.library.save()
        self.shelf.refresh()

        self.open_book(book)

    def open_book(self, book):

        """Load a book from the library and show its board."""
        if not self.on_shelf() and not self.show_shelf():
            return

        path = self.library.book_path(book)
        self.current_book = book

        if os.path.exists(path):
            if not self.load_file(path):
                self.current_book = None
                return
        else:
            self.reset_types([])
            self.scene.reset()
            self.attachments.replace_all({})
            self.known_tags = set()
            self.current_file = path
            self.reset_history()
            self.refresh_views()

        self.library.begin_session(book, self.total_words())
        self.library.save()

        self.show_board()
        self.view.fit_all()
        self.update_stats_label()

    def edit_book_info(self):

        """File -> Notebook info: edit title, author, goal …"""
        book = self.current_book

        if book is None:
            self.statusBar().showMessage(
                tr("Dieses Board gehört zu keinem Notizbuch "
                "(im Regal über „Importieren …“ aufnehmen)."), 5000
            )
            return

        dialog = BookInfoDialog(book, self.library.categories, self)

        if dialog.exec() != BookInfoDialog.DialogCode.Accepted:
            return

        old = book.category_id
        dialog.apply(book)

        if book.category_id != old:
            self.library.move_book(
                book, book.category_id, len(self.library.books_in(book.category_id))
            )

        self.library.save()
        self.update_title()
        self.update_stats_label()

    def total_words(self):
        """Number of words in all note texts (cached per note)."""
        return sum(
            note_word_count(n.model) for n in self.scene.note_lookup.values()
        )

    def update_stats_label(self):

        """Status bar text: notes, words, goal %, today."""
        words = self.total_words()
        text = tr("{n} Notizen · {words} Wörter", n=len(self.scene.note_lookup), words=words)

        book = self.current_book
        if book is not None:
            if book.target_words:
                pct = int(words * 100 / book.target_words)
                text += tr(" · Ziel {pct} %", pct=pct)
            text += tr(" · Heute {delta}", delta=f"{self.library.today_delta(book, words):+d}")

        self.stats_label.setText(text + "   ")

    def refresh_timeline(self):

        """Collect dated notes and give them to the timeline widget."""
        if not self.timeline_dock.isVisible():
            return

        entries, undated = [], 0

        for note in self.scene.note_lookup.values():
            key = note_timeline_key(note.model)
            if key is None:
                undated += 1
                continue

            when = attribute_value(note.model, "Datum")
            time_text = attribute_value(note.model, "Uhrzeit")
            if time_text:
                when += " " + time_text

            info = self.note_types.get(note.model.note_type)
            entries.append((
                note, date_to_days(key), when,
                info.label if info else note.model.note_type,
            ))

        self.timeline.set_entries(entries, undated)

    def show_stats(self):

        """Show the statistics dialog."""
        notes = list(self.scene.note_lookup.values())
        book = self.current_book

        html = build_stats_html(
            notes, self.note_types, len(self.scene.connection_items), book,
            self.library.today_delta(book, self.total_words()) if book else None,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Statistik") + (" — " + book.title if book else ""))
        dialog.resize(480, 640)

        lay = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setHtml(html)
        lay.addWidget(browser)

        dialog.exec()

    def export_manuscript(self):

        """File -> Export -> Manuscript."""
        notes = list(self.scene.note_lookup.values())

        if not notes:
            self.statusBar().showMessage(tr("Das Board ist leer."), 3000)
            return

        dialog = ManuscriptDialog(notes, self.note_types, self)

        if dialog.exec() != ManuscriptDialog.DialogCode.Accepted:
            return

        keys = dialog.selected_types()
        if not keys:
            self.statusBar().showMessage(tr("Keine Notizart ausgewählt."), 3000)
            return

        fmt = dialog.fmt()
        sections = build_sections(notes, keys, self.attachments)

        book = self.current_book
        title = book.title if book else (
            os.path.splitext(os.path.basename(self.current_file))[0]
            if self.current_file else tr("Manuskript")
        )
        author = book.author if book else ""

        filters = {
            "md": "Markdown (*.md)", "txt": "Text (*.txt)",
            "html": "HTML (*.html)", "pdf": "PDF (*.pdf)",
        }

        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Manuskript exportieren"), f"{title}.{fmt}", filters[fmt]
        )

        if not filename:
            return

        if not filename.lower().endswith("." + fmt):
            filename += "." + fmt

        try:
            if fmt == "pdf":
                write_pdf(
                    to_html(sections, title, author, dialog.include_titles()),
                    filename,
                )
            else:
                text = render(fmt, sections, title, author, dialog.include_titles())
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(text)
        except Exception as error:
            QMessageBox.critical(self, tr("Fehler beim Export"), str(error))
            return

        self.statusBar().showMessage(tr("Exportiert: {path}", path=filename), 5000)

    def load_backup(self):
        """Ältere automatische Sicherung ins Board laden (rückgängig machbar)."""

        start = ""
        if self.current_book:
            start = self.library.backup_folder(self.current_book)

        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Sicherung laden"), start, "AuthorBoard (*.json)"
        )

        if not filename:
            return

        answer = QMessageBox.question(
            self,
            tr("Sicherung laden"),
            tr("Den aktuellen Stand durch diese Sicherung ersetzen?\n"
            "(Mit Strg+Z lässt sich das rückgängig machen.)"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.checkpoint()

        try:
            project = Storage.load(filename)
            self.restore_project(project, fit=False, reset_filter=False, blobs="merge")
        except Exception as error:
            QMessageBox.critical(self, tr("Fehler beim Laden"), str(error))
            return

        self.checkpoint()
        self.statusBar().showMessage(tr("Sicherung geladen"), 4000)

    # ------------------------------------------------------ Projekt

    def reset_types(self, custom_types, keep_unknown=False):
        """Rebuild the note type registry: built-in, then global (settings),
        then the notebook's own types.  The dict is updated in place because the
        scene shares it.  ``keep_unknown`` re-registers types that notes use but
        that are no longer defined (e.g. a deleted global type)."""

        self.note_types.clear()
        for t in builtin_note_types():
            self.note_types[t.key] = t
        for t in settings.global_types():
            self.note_types[t.key] = t
        for t in custom_types:
            if t.key not in self.note_types:
                self.note_types[t.key] = t

        if keep_unknown:
            for n in self.scene.note_lookup.values():
                key = n.model.note_type
                if key not in self.note_types:
                    self.note_types[key] = NoteTypeData(key, key, n.model.color)

        self.inspector.set_types(self.note_types)
        self.refresh_type_combo()


    def build_project_data(self, for_file=True):
        """Collect the current board into a :class:`ProjectData`.

        ``for_file=True`` (saving) also includes the attachment bytes that are
        still referenced and the tag memory; undo snapshots pass False."""

        project = ProjectData()
        notes = list(self.scene.note_lookup.values())

        # Global types travel with the file only when notes use them
        used = {n.model.note_type for n in notes}
        project.custom_types = [
            t for t in self.note_types.values()
            if t.key not in BUILTIN_TYPE_KEYS
            and (not t.key.startswith(GLOBAL_PREFIX) or t.key in used)
        ]

        pin_ids = set()

        for note in notes:
            pos = note.pos()
            note.model.x, note.model.y = pos.x(), pos.y()

            for pin in note.pins:
                p = pin.pos()
                pin.model.x, pin.model.y = p.x(), p.y()
                pin_ids.add(pin.model.id)

            project.notes.append(note.model)

        for connection in self.scene.connection_items:
            d = connection.model
            if d.start_pin_id in pin_ids and d.end_pin_id in pin_ids:
                project.connections.append(d)

        if for_file:
            project.known_tags = sorted(self.known_tags)
            project.blobs = self.attachments.subset(
                AttachmentStore.referenced_ids(project.notes))

        return project

    def save_project(self):

        """Ctrl+S: save (asks for a file name only for files outside the library)."""
        if not self.current_file:
            self.save_project_as()
            return

        self._write(self.current_file)

    def save_project_as(self):

        """Save a copy under a new name."""
        if self.current_book:
            # Notizbuch: Kopie exportieren, das Buch bleibt im Regal
            filename, _ = QFileDialog.getSaveFileName(
                self, tr("Kopie speichern unter"),
                self.current_book.title + ".json", "AuthorBoard (*.json)"
            )
            if not filename:
                return
            if not filename.lower().endswith(".json"):
                filename += ".json"
            try:
                Storage.save(self.build_project_data(), filename)
            except Exception as error:
                QMessageBox.critical(self, tr("Fehler beim Speichern"), str(error))
                return
            self.statusBar().showMessage(tr("Kopie gespeichert: {path}", path=filename), 5000)
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, tr("Projekt speichern"), self.current_file or "",
            "AuthorBoard (*.json)"
        )

        if not filename:
            return

        if not filename.lower().endswith(".json"):
            filename += ".json"

        self._write(filename)

    def _write(self, filename):

        """Write the board to ``filename`` (with backup + bookkeeping)."""
        self.checkpoint()

        try:
            if self.current_book:
                self.library.backup(self.current_book)
            Storage.save(self.build_project_data(), filename)
        except Exception as error:
            QMessageBox.critical(self, tr("Fehler beim Speichern"), str(error))
            return

        self.clear_autosave()

        self.current_file = filename
        self.saved_state = self.undo_stack.current
        self.update_dirty()

        if self.current_book:
            self.library.update_stats(
                self.current_book, len(self.scene.note_lookup), self.total_words()
            )
            self.library.save()
            self.update_stats_label()

        self.statusBar().showMessage(tr("Gespeichert: {path}", path=filename), 5000)

    def load_project(self):
        """Beliebige Board-Datei öffnen (ohne Regal)."""

        if not self.on_shelf() and not self.maybe_save():
            return

        filename, _ = QFileDialog.getOpenFileName(
            self, tr("Projekt laden"), "", "AuthorBoard (*.json)"
        )

        if not filename:
            return

        if not self.on_shelf():
            self.finish_book()

        previous = self.current_book
        self.current_book = None

        if self.load_file(filename):
            self.show_board()
            self.view.fit_all()
        else:
            self.current_book = previous

    def load_file(self, filename):

        """Load a board file (offers a newer autosave); returns True on success."""
        source = filename
        recovered = False

        auto = filename + ".autosave"
        try:
            newer = (
                os.path.exists(auto)
                and os.path.getmtime(auto) > os.path.getmtime(filename)
            )
        except OSError:
            newer = False

        if newer:
            answer = QMessageBox.question(
                self,
                tr("Automatische Sicherung"),
                tr("Es gibt eine neuere automatische Sicherung dieser Datei.\n"
                "Sicherung laden?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                source = auto
                recovered = True

        try:
            project = Storage.load(source)
            self.restore_project(project)
        except Exception as error:
            QMessageBox.critical(self, tr("Fehler beim Laden"), str(error))
            return False

        self.current_file = filename
        self.reset_history()

        if recovered:
            self.saved_state = None
            self.update_dirty()

        self.statusBar().showMessage(tr("Geladen: {path}", path=filename), 5000)
        return True

    def restore_project(self, project, fit=True, reset_filter=True, blobs="replace"):
        """Replace the board by ``project``.

        ``blobs`` controls the attachment store: "replace" (loading a book),
        "merge" (restoring a backup), "keep" (undo/redo - snapshots carry no bytes)."""

        if blobs == "replace":
            self.attachments.replace_all(project.blobs)
            self.known_tags = set(project.known_tags) | {
                t for n in project.notes for t in n.tags}
        elif blobs == "merge":
            self.attachments.blobs.update(project.blobs)

        self.reset_types(project.custom_types)

        # Notizen mit unbekannter Art als eigene Art registrieren
        for note_data in project.notes:
            if note_data.note_type not in self.note_types:
                self.note_types[note_data.note_type] = NoteTypeData(
                    note_data.note_type, note_data.note_type, note_data.color
                )

        self.inspector.set_types(self.note_types)
        self.refresh_type_combo()

        self._tree_items.clear()
        self._tree_groups.clear()

        self.scene.reset()

        if reset_filter:
            for w in (self.search_edit, self.type_filter,
                      self.tag_filter, self.status_filter):
                w.blockSignals(True)
            self.search_edit.clear()
            self.type_filter.setCurrentIndex(0)
            self.tag_filter.setCurrentIndex(0)
            self.status_filter.setCurrentIndex(0)
            for w in (self.search_edit, self.type_filter,
                      self.tag_filter, self.status_filter):
                w.blockSignals(False)

        for note_data in project.notes:
            self.scene.add_note_item(note_data)

        for cd in project.connections:
            start = self.scene.pin_lookup.get(cd.start_pin_id)
            end = self.scene.pin_lookup.get(cd.end_pin_id)

            if start is None or end is None:
                continue

            self.scene.add_connection(cd, start, end)

        self.refresh_views()

        if fit:
            self.timeline._fitted = False
            self.refresh_timeline()
            self.view.fit_all()


def main():

    """Create the application, set language and theme, show the main window."""
    app = QApplication(sys.argv)
    app.setApplicationName("AuthorBoard")
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.svg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))      # needs the Qt SVG plugin (part of PySide6)
    app.setStyle("Fusion")
    apply_dark_palette(app)

    i18n.set_language(initial_language())
    install_qt_translation(app, i18n.current_language())

    window = MainWindow()
    _windows.append(window)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
