# Bookshelf & library

## Data (`library.py`)

```text
~/.authorboard/
  library.json          {"categories":[{id,name,color}], "books":[{id,title,author,...,note_count,word_count}]}
  books/<book id>.json  the notebook (see data model)
  backups/<book id>/    timestamped copies
  settings.json         global settings (settings.py)
```

* `Library` has **no GUI code**. Callers modify it and call `save()`.
* `Book` stores metadata plus cached `note_count` / `word_count` so the shelf can draw spines without opening files.
* `Library.backup(book)` copies the old file before each save (at most every `BACKUP_MIN_INTERVAL` seconds; `BACKUP_KEEP` newest are kept).
* `begin_session` / `today_delta` implement the "Today +n" counter: the word count at the first opening each day is the baseline.

## The shelf page (`shelf.py`)

`ShelfScene.rebuild()` clears and re-creates everything: for each category a `CategoryHeader`, rows of `BookItem`s (wrapping to the viewport width), an `AddBookItem` and `ShelfRow` boards.
It records `rows[cat_id]` and `cat_ranges[cat_id]` - the y ranges - which the drop handlers use.

**Dragging a book:** `BookItem` is movable; on release `ShelfScene.drop_book` finds the nearest row, computes the insertion index among the books of that category and calls `Library.move_book`, then rebuilds *deferred* (`QTimer.singleShot(0, rebuild)`) because the item that received the event must not be deleted while it is still handling it.

**Dragging a shelf:** `CategoryHeader` handles the mouse itself: on press it collects all items with the same `cat_id` (`block_items`), on move it offsets them vertically, on release `drop_category` compares the dragged centre with the other shelves' centres to get the new index (`Library.move_category_to`).

**Shelf colour:** `ShelfRow` derives back panel, side walls and plank from one colour using `QColor.darker/lighter`.

## Import with book information

`ShelfPage.import_files` loads the file (to validate and count words), copies it into the library and reads the optional `"book"` object to fill title, author, genre, colour, word goal, deadline, custom fields and category (`Library.apply_meta`).
