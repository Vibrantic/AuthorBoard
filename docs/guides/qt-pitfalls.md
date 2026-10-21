# Qt lessons & pitfalls

Things that cost time while building AuthorBoard. Read this before debugging a strange Qt behaviour.

| Symptom | Cause | Fix used here |
|---|---|---|
| Threads lag one step behind when dragging a note | `itemChange(ItemPositionChange)` runs *before* the move | use `ItemPositionHasChanged` |
| The board "jumps" when selecting a note | a dock's `sizeHint` depends on its content (empty label vs form) and the view re-anchors on resize | constant `sizeHint` / `minimumSizeHint` (`InspectorWidget`, `RightPanel`), `setResizeAnchor(NoAnchor)` |
| Commented range lost after save/load | `anchorNames` are exported as a *point* | character-format tool tip `ab-comment:<id>` (survives as `title=""`) |
| `mergeCharFormat` cannot remove a colour | it only *sets* properties | `QTextCharFormat.clearForeground()` + `setCharFormat` |
| Crash when a graphics item is deleted inside its own mouse handler | `scene.clear()` while the item handles the event | defer with `QTimer.singleShot(0, ...)` |
| `drawText(rect, flags, text)` type errors with combined enums | PySide6 enums are not ints | use the `drawText(rect, text, QTextOption(...))` overload |
| Thread over a pin steals clicks | threads are above notes | pin heads re-painted by the thread, `shape()` excludes discs around pins, pins searched first |
| Context menu appears twice / at the wrong time | platform differences for right-click | override `BoardView.contextMenuEvent`, show menus from the scene on *release* |
| Tool tips of graphics items are static | `setToolTip` is a plain string | set it in `hoverEnterEvent` / `hoverMoveEvent` |
| `QTextEdit` tool tips at scroll-area level | tool-tip events arrive at the *viewport* | override `viewportEvent`, not `event` |
| Shift+Space types nothing in text fields | a QShortcut consumes the key | app-wide event filter that checks the focus widget |
| Texts built at import time ignore language switches | module constants evaluated once | `N_()` + `tr()` at display time, builder functions |
| Qt dialogs block tests | `exec()` runs a local loop | tests use `QTimer.singleShot` to click a button of `QApplication.activeModalWidget()` |

## Other conventions worth knowing

* **Never keep a Python reference to an item after `scene.clear()`** - the C++ object is deleted. `BoardScene.reset()` emits `note_selected(None)` first so the inspector lets go.
* **Signals during bulk updates:** `restore_project` blocks the scene's signals while clearing; `QWidget.blockSignals(True)` is used around programmatic filter changes.
* **Debounce instead of reacting to every keystroke:** refresh (120 ms) and checkpoint (350 ms) timers in `MainWindow`.
* **Opacity propagates to children:** dimming a note also dims its pins. Dimming is done only through `QGraphicsItem.setOpacity` in `reapply_filter`.
