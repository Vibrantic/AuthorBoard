# AuthorBoard - developer documentation

AuthorBoard is a desktop application for authors written in **Python 3** with **Qt 6 (PySide6)**.
This documentation explains **how the program works internally** so that you can fix bugs, add features
or learn from the code without having to read everything first.

!!! tip "Where to start"
    1. Read the [Architecture overview](architecture/overview.md) - it shows the building blocks and how they talk to each other.
    2. Skim [Data model & file format](architecture/data-model.md) - nearly every feature is "some data + a view of it".
    3. Use [Extending AuthorBoard](guides/extending.md) for recipes (new note type, export format, language ...).
    4. The [API reference](reference/index.md) is generated from the docstrings in the source.

## What the program does

| Area | Summary | Main modules |
|---|---|---|
| Bookshelf | Start page with shelves and books | `shelf.py`, `library.py` |
| Board | Sticky notes, pins, threads | `canvas.py`, `note_item.py`, `pin_item.py`, `connection_item.py` |
| Inspector | Property editor, attachments, connections | `inspector.py`, `widgets.py` |
| Writing | Rich text, images, links, comments, spelling | `rich_text.py`, `editor_dialog.py`, `spellcheck.py` |
| Timeline | Dated notes on a horizontal axis | `timeline.py` |
| Persistence | JSON files, undo snapshots, backups | `models.py`, `storage.py`, `undo.py` |
| App shell | Window, menus, wiring | `main.py` |
| i18n & help | Translations, manual, About | `i18n.py`, `help_dialog.py`, `about_dialog.py` |

## Conventions

* User-visible text is written in **German** inside `tr("...")` calls; English lives in `locales/en.json`.
* Every module / class / function has a docstring. Qt override methods (`mousePressEvent`, `paint`, ...) keep Qt's camelCase names.
* Data classes in `models.py` have **no Qt dependency**, which makes them easy to test and serialise.
* Widgets do not reach into each other: they emit **signals**, and `MainWindow` connects them.

## License

GPL-3.0-or-later. The software is provided *as is*, without warranty (see `LICENSE`).
