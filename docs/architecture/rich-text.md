# Rich text, comments, attachments, spell check

All of it lives in `RichTextEdit` (`rich_text.py`), a `QTextEdit` subclass used by the inspector (compact, plain paste)
and by the full-size editor (toolbar).

## Where the formatting is stored

`QTextEdit.toHtml()` -> `NoteData.rich`. See [Plain text vs rich text](data-model.md#plain-text-vs-rich-text).
The inspector's text box calls `to_storage()` on every change; it only stores HTML when `has_rich_content()` is true.

## Images

* Inserted images become attachments (`insert_image_bytes` -> `AttachmentStore.add_bytes(inline=True)`).
* The HTML refers to them as `<img src="attachment:<id>">`.
* Qt asks `RichTextEdit.loadResource(...)` for those URLs; we answer from the store.
* For HTML/PDF export, `embed_images()` replaces the URLs by `data:image/png;base64,...`.
* Paste and drag & drop go through `insertFromMimeData`.

## Links

Anchors with an `href` (`QTextCharFormat.setAnchorHref`). `Ctrl+click` -> `open_link()`, which only allows the schemes in `SAFE_SCHEMES`.

## Comments

!!! info "Design decision"
    A comment must stick to a **range** of text and survive the HTML round trip. We tested the options:

    * `anchorNames` -> exported as an *empty* `<a name>` at the start only - the range is lost.
    * `anchorHref` -> keeps the range but collides with real links.
    * **character-format tool tip** (`QTextCharFormat.setToolTip`) -> exported as `title="..."`, **keeps the exact range** and coexists with links, colours and fonts. ✔

So a commented range has the tool tip `ab-comment:<id>` (`COMMENT_PREFIX`). The text of the comment is a `CommentData` in `note.comments`.

Helper functions:

| Function | Purpose |
|---|---|
| `comment_ranges(doc)` | `{id: [(start, end), ...]}` by scanning the fragments |
| `RichTextEdit.add_comment_dialog` | asks for the text, merges the tool-tip format into the selection |
| `RichTextEdit.delete_comment` / `_clear_marker` | removes the marker fragment by fragment |
| `remove_comment_marker(html, id)` | same, on an HTML string (used by the comments panel) |
| `RichTextEdit.focus_comment(id)` | selects the range and scrolls to it |
| `MainWindow.refresh_aux` | drops comments whose marker string is gone from `note.rich` |

**Hover pop-up:** `viewportEvent` handles `QEvent.ToolTip`, finds the comment under the pointer with `_comment_at` and calls `QToolTip.showText`.

**Display:** `DocHighlighter` (a `QSyntaxHighlighter`) paints an amber background + dashed underline over commented ranges. It is an overlay - never saved.

## Spell checking

`spellcheck.py`:

* `SpellEngine` wraps *pyspellchecker* (optional import). Language = setting `spell_language` (`auto` follows the UI language).
* `is_misspelled(word)` is cached per (language, word); user words, book vocabulary (note titles, tags) and session-ignored words are skipped.
* `suggestions(word)` ranks candidates by word frequency and keeps the capitalisation.
* `DocHighlighter.highlightBlock` underlines unknown words with `SpellCheckUnderline`.
* The context menu (`contextMenuEvent`) offers suggestions, *Add to dictionary* and *Ignore*.

## The full-size editor

`NoteEditorDialog` works on **copies** of the comment and attachment lists (`bind`). The toolbar merges `QTextCharFormat`s into the selection (`_merge`); to *remove* a property (default colour, no highlight) it uses `setCharFormat` with the property cleared, because `mergeCharFormat` cannot clear properties.
