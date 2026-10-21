# Development setup

## Run from source

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python main.py
```

Use another data folder while developing so you do not touch your real notebooks:

```bash
AUTHORBOARD_HOME=/tmp/ab-dev python main.py          # PowerShell: $env:AUTHORBOARD_HOME="C:\temp\ab-dev"
```

## Tests

```bash
python tests/run_all.py                 # everything
python tests/test_rich_text.py          # one script
```

The tests are plain scripts using Qt's *offscreen* platform and a temporary `AUTHORBOARD_HOME`.
They create real widgets, simulate mouse and keyboard input with `QTest` and assert on the result.
They are deliberately close to what a user does (import a showcase, create threads, undo ...).

| Script | Covers |
|---|---|
| `test_inspector_stability.py` | the board does not shift when the inspector changes |
| `test_rich_text.py` | comments, links, images, spelling, HTML round trip |
| `test_canvas.py` | locks, thread z-order, focus mode |
| `test_integration.py` | attachments, comments panel, editor, tags, filters, global types, save/load |
| `test_shelf_library.py` / `test_shelf_timeline.py` | bookshelf, library, drag & drop, timeline |
| `test_i18n.py` | English UI, live language switch |
| `test_showcase.py de|en` | both showcase notebooks end-to-end |

## Generated material

| Command | Output |
|---|---|
| `python tools/make_showcase.py` | `showcase/*.json` (German + English example notebooks) |
| `python tools/make_screenshots.py` | `docs/images/*.png` used by README and docs |
| `mkdocs serve` / `mkdocs build` | this documentation (`site/`) |
| `python i18n.py check en` | untranslated texts |

## Code style

* PEP 8, 4 spaces, ~100 columns, type hints optional.
* Docstring for every module, class and function (Google style - `Args:` / `Returns:` when useful). `mkdocstrings` renders them in the [API reference](../reference/index.md).
* Comments explain **why**, not what.
* GPL header at the top of each file (see any module).

## Debugging tips

* Start from a terminal to see Qt warnings and Python tracebacks (exceptions inside Qt slots print but do not crash the app).
* `python -X dev main.py` enables more checks.
* To inspect what is saved, open `books/<id>.json` - it is indented JSON.
* The undo stack holds JSON strings: `MainWindow.undo_stack.states[i]` can be pretty-printed to see what a step contains.
