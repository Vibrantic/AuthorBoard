# Changelog

## 1.1.0

Performance, small UX fixes, and one new feature.

**Performance**

- Board rendering
  - Level-of-detail tiers for notes, threads and pins, chosen per frame from the current zoom and the number of visible items.
  - Threads whose endpoints are off-screen are skipped; the view publishes the visible rect and the visible counts once per paint (throttled while panning).
  - Cached paper paths, note tooltips, search haystacks, thread paths and label rectangles.
  - Tiled-pixmap grid; device-coordinate item cache; cheaper bounding rectangles.
  - Reapplying the search / focus filter only touches items whose opacity actually changed.
- Timeline
  - Bucketed O(N) level assignment (previously O(N²); a 5000-note timeline frame drops from ~2.2 s to ~44 ms).
  - Cached level and visible-set computations per view state; off-screen entries are not painted.
- Data
  - Undo snapshots share per-note JSON strings across history entries; undo / redo re-adds only the notes that changed.
  - Refresh paths use dirty flags; the notes tree is updated incrementally from a per-note revision; per-note word counts and mention lookups are cached.
- Autosave is written on a worker thread and no longer blocks the UI.
- Fit-all is clamped to the minimum zoom, so the mouse wheel can always zoom back in.

**UX**

- Threads below 100 % zoom are hidden by default and shown only when a note is selected (its connected threads). Invisible threads are click-through.
- Clicking a comment in the Comments panel selects and centres the note that holds it, without opening the editor. Double-click still opens the editor and jumps to the commented words.
- Focus mode no longer gets stuck after the first note click when the deselect click landed on a note.
- Dimmed notes correctly return to full opacity when the selection is cleared.
- Mouse cursor no longer sticks as the closed-hand or resize-diagonal icon after panning or resizing with a release over a child item.

**Internal**

- `tools/make_stress.py` — generates boards of various shapes (grid, clusters, hub, long-range threads) for benchmarking.
- `tools/profile_board.py` — headless timing of the hot paths.
- `tools/bsp_probe.py` — BSP vs NoIndex comparison for `QGraphicsScene`.

## 1.0.0

First complete release.

- Bookshelf start page with colourable, draggable shelves and notebooks
- Board with typed sticky notes, pins, labelled coloured threads, search and filters
- Locking of notes and pins, focus mode, threads in front of notes
- Inspector with resizable attribute / attachment / connection lists, tag auto-completion
- Attachments (files and images) stored inside the notebook
- Full-size rich-text editor (fonts, colours, highlighter, links, images)
- Comments with hover pop-up and a Comments tab
- Spell checking for English and German
- Horizontal timeline, statistics, manuscript / outline / image export
- Undo / redo, save prompt, autosave with recovery, automatic backups
- Custom note types per book and global
- English and German interface, searchable in-app documentation, About dialog
- Showcase notebooks (English and German)