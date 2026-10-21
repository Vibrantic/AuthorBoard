# Extending AuthorBoard

Recipes for the most common extensions. Each recipe lists **all** places to touch.

## Add a built-in note type

1. `models.py` -> append a `NoteTypeData("recipe", N_("Rezept"), "#ffe0b2", [N_("Portionen"), N_("Dauer")])` to `BUILTIN_NOTE_TYPES`.
2. `python i18n.py update en` and translate the new texts in `locales/en.json`.
3. Mention it in `help/en/05-note-types.md` and `help/de/05-note-types.md`.

Nothing else is needed: palette, filters, inspector, tree and export all iterate over the registry.

## Add a setting

1. `settings.py` -> add the key and default to `DEFAULTS`.
2. `settings_dialog.py` -> add a widget in the *General* tab and write it in `apply_general()`.
3. Read it with `settings.get("key")` where it is used. React to changes in `MainWindow.open_settings`.

## Add a new attribute with special meaning (like *Date*)

Add the canonical German name and its synonyms to `models._ATTR_SYNONYMS`, then read it with `attribute_value(note, "Name")`.

## Add an export format

1. Write a renderer in `manuscript.py` (`to_xxx(sections, title, author, include_titles)` where `sections` is a list of `(heading, plain, html)`).
2. Register it in `FORMATS` and `render()` (and the file filter in `MainWindow.export_manuscript`).
3. Add a test that calls the renderer.

## Add a field to notes (e.g. "mood")

1. `models.NoteData` -> new field with a default.
2. `storage.py` -> write it in `to_dict`, read it with `.get(..., default)` in `from_dict` (older files must still load).
3. `inspector.py` -> widget + slot that edits `note.model.<field>` and calls `self._changed()`.
4. Because it is part of `ProjectData`, **undo, autosave and saving work automatically**.
5. Optional: paint it in `NoteItem.paint`, search it in `models.note_matches`, export it in `export.py`.

## Add a context-menu action on notes

`canvas.BoardScene.show_context_menu` -> `elif isinstance(item, NoteItem):` branch. Modify the model, then emit `self.notes_changed.emit()` and `self.interaction_finished.emit()` so a checkpoint is created.

## Add a dock / panel

Create the widget, wrap it in a `QDockWidget` in `MainWindow.create_docks`, add it to `_hide_docks` / `_remember_docks` / `_restore_docks` if it should be hidden on the bookshelf, and a toggle action (`dock.toggleViewAction()`).

## Add a language

```bash
python i18n.py new fr "Français"
```

Translate `locales/fr.json`. Optionally copy `help/en` to `help/fr`. For a spell-check language add it to `spellcheck.LANGUAGES` (pyspellchecker ships `en, de, es, fr, pt, it, ru, ar, eu, lv, nl`).

## Add a help topic

Create `help/en/19-topic.md` (and `help/de/...`) starting with `# Title`. It appears in the list automatically (sorted by file name). Link to it with `[text](topic:19-topic)`.

## Change how threads look

All thread painting is in `connection_item.ConnectionItem.paint` / `_draw_thread`. `THREAD_Z` and `OVER_NOTE_OPACITY` are class constants.
