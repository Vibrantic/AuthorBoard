# Main window & lifecycle

`MainWindow` (in `main.py`) is long but organised in sections. This page is a map.

## Start-up

```text
main()                      QApplication, dark palette, language, window icon
 └─ MainWindow.__init__
      create_canvas         BoardScene + BoardView + ShelfPage in a QStackedWidget
      create_docks          Notes tree (left), Inspector|Comments tabs (right), Timeline (bottom)
      create_menu/toolbar   actions; board-only actions are collected in board_actions
      signal wiring         scene / inspector / panels  ->  MainWindow slots
      reset_history         first undo state
      show bookshelf        docks hidden, apply_mode()
      QTimer(300ms)         check_recovery(): offer to restore a crashed session
```

## Opening and leaving a book

| Step | Method |
|---|---|
| user double-clicks a book | `ShelfPage.open_requested` -> `open_book(book)` |
| load file (offers newer autosave) | `load_file` -> `Storage.load` -> `restore_project` |
| start the day's word counter | `Library.begin_session` |
| show the board | `show_board` (restores docks, `apply_mode`) |
| back to the bookshelf | `show_shelf` -> `maybe_save` -> `finish_book` -> `scene.reset` |

`restore_project(project, fit, reset_filter, blobs)` is the single place where a `ProjectData` becomes items.
The `blobs` argument tells it what to do with attachment bytes: `"replace"` (load a book), `"merge"` (restore a backup), `"keep"` (undo/redo - snapshots carry none).

## Building the project from the board

`build_project_data(for_file)` goes the other way: it copies positions back into the models and collects notes and valid threads.
`for_file=True` additionally includes the referenced attachment bytes and the tag memory.

## Editor, comments, settings, help

* `open_editor(note, focus_comment)` shows `NoteEditorDialog` on **copies** and writes the result back only on *Apply*.
* `delete_comment` removes a comment *and* its marker from the HTML (`rich_text.remove_comment_marker`).
* `open_settings` collects `SettingsDialog` results and rebuilds the type registry with `reset_types(..., keep_unknown=True)`.
* `refresh_aux` (after every refresh): drops comments whose text was deleted, updates the spell-check vocabulary (note titles, tags), tag suggestions and the comments tab.

## Language switch

`switch_language(code)` saves the book, sets the new language and **creates a new `MainWindow`** (all texts are built at construction time), re-opens the book, then closes the old window with `_closing_for_switch = True` so `closeEvent` does not ask again. Windows are kept alive in the module list `_windows`.

## Event filter

An application-wide filter turns **Shift+Space** into "open the palette" - but only when no text field has focus (`_text_input_focused`), so you can still type capital letters with spaces.
