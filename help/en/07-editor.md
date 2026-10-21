# The full-size editor

Open it with **F2**, the button *Open in large editor* in the Inspector, or *Open in large editor* in a note's context menu.

## Formatting toolbar

| Control | Function |
|---|---|
| Font box, size box | Font family and size |
| **B** *I* U S | Bold (Ctrl+B), italic (Ctrl+I), underline (Ctrl+U), strike-through |
| **A** | Text colour - quick colours, custom colour or *Default colour* |
| Marker | **Highlight colour** behind the text - quick colours, custom colour or *Remove highlight* |
| Alignment | Left, centred, right, justified |
| • | Bullet list on/off |
| 🔗 | Insert a **link** (Ctrl+K) |
| 🖼 | Insert an **image** |
| 💬 | Add a **comment** (Ctrl+Alt+M) |
| ⌫ | Clear formatting of the selection |
| Spelling | Dictionary: Automatic / English / Deutsch / Off |

Without a selection, formatting applies to the word under the cursor.

## Links

Select text, press **Ctrl+K** and enter the address. **Ctrl+click** a link to open it in your **web browser**; hover it to see the address. Right-click a link for *Open link in browser*. Only `http`, `https`, `mailto` and `ftp` links are opened.

## Images

Use the image button, **paste** an image from the clipboard (Ctrl+V) or **drag** an image file into the text. Every image is stored as an attachment of the note, so it is saved inside the notebook file.

## Spell checking

Unknown words get a **red wavy underline**. Right-click a word for suggestions, *Add to dictionary* or *Ignore*. Note titles and tags of the open book are never flagged. English and German are supported; choose the language in the toolbar or in *Settings*. Spell checking needs the optional package `pyspellchecker`.

## Comments sidebar and finishing

The sidebar lists the comments of this note ([more](topic:08-comments)). **F11** toggles full screen. *Apply* stores your work in the note, *Cancel* discards it. The word and character count is shown below the text.
