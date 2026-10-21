# The board: scene and items

## Classes

| Class | File | Role |
|---|---|---|
| `BoardScene` | `canvas.py` | owns all items, lookup tables, gestures, filter / focus mode |
| `BoardView` | `canvas.py` | zoom (wheel), pan (middle button), Delete key, `fit_all` |
| `NoteItem` | `note_item.py` | sticky note; paints text, icons; handles resize |
| `PinItem` | `pin_item.py` | child of a note; `paint_pin_head()` is shared |
| `ConnectionItem` | `connection_item.py` | thread between two pins |

## Stacking order (z values)

```text
notes ........ 10 ... _top_z   (a note clicked gets the next number; wraps long before the threads)
threads ...... ConnectionItem.THREAD_Z = 100_000   (always above every note)
drag preview . 1_000_000
pins ......... children of their note (z=100 *inside* the note)
```

Because threads are above notes, a thread would cover the pins and swallow clicks on them. Three details fix this:

1. `ConnectionItem.paint` **re-paints the two pin heads** on top of the thread.
2. `ConnectionItem.shape()` subtracts small discs around the pins, so clicks reach the pins.
3. `BoardScene._item_at()` looks for a pin first.

**Fainter over notes:** `paint` computes the union of the rectangles of all notes under the thread
(`_notes_under_thread`) and draws the thread twice - full opacity clipped *outside* that area, half opacity clipped *inside* it.

## The right-button gesture

`BoardScene.mousePressEvent/MoveEvent/ReleaseEvent` implement it (the left button is left to Qt):

1. press on a pin -> `_begin_connect` creates a dashed preview line item
2. move -> `_update_connect` re-routes the line and highlights the pin underneath
3. release on another pin -> `create_connection`; release without moving -> `show_context_menu`

`BoardView.contextMenuEvent` is overridden to do nothing, otherwise Qt would also show its own context menu on some platforms.

## Moving and following

* `NoteItem.itemChange(ItemPositionHasChanged)` stores the position in the model and calls `update_connections()`.
  (**HasChanged**, not *Change*: in *Change* the new position is not yet applied and threads would lag behind.)
* Pins are child items, so they move with the note automatically - this is why a *locked* pin still follows the note.
* Locking is just the flag `ItemIsMovable` (`NoteItem.set_locked`, `PinItem.set_locked`) plus the model field.

## Filter and focus mode

`BoardScene.reapply_filter()` is the **only** place that sets opacities:

```text
note opacity = 0.18  if the search/filter does not match
             = 0.15  if focus mode is on and the note is not in {selected notes + direct neighbours}
             = 1.0   otherwise
thread opacity = 1.0 only if (filter matches both ends) and (focus mode off or a selected note is an end)
                 else 0.08
```

It runs after every selection change, filter change and connection change.

## Grid, snapping, background

`drawBackground` paints the grid (minor lines hidden when zoomed out). Snapping is implemented in `NoteItem.itemChange(ItemPositionChange)`.
