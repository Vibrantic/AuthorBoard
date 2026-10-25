# FlowView

**FlowView** is a separate, non-modal window that shows the **neighbourhood of a note**: the root and its directly connected notes. It walks the connection graph **one hop at a time**, without leaving the board.

## Opening it

- **Right-click a note → Open FlowView**.
- Or **View → FlowView** (Ctrl+T) with a note selected.

There is only **one** FlowView window: opening it for another note re-roots the existing window instead of opening a second one.

## What it shows

- **Two columns**: root on the left, its direct neighbours in pin order on the right.
- **Edges** are drawn orthogonally; each edge owns its own routing channel, so no two vertical lines ever overlap.
- **Right-click an edge**: color, label (e.g. "brother of") or delete.
- **Double-click a node**: open the full-size editor.
- **▶ arrow** on a neighbour: makes it the new root and re-lays out the view around it.

## The Inspector

The Inspector in FlowView is the **same** as on the board: title, tags, attributes, text, attachments and connections of the currently inspected note. Changes land in the board immediately.

## Minimap

In the bottom-left corner sits an **overview of the whole connected component**:

- **Filled dots** are the current root and its neighbours (click = jump there).
- **Hollow dots** are up to `MAX_DOTS − |active|` further notes, ordered by BFS distance; the count is capped so the minimap stays readable on large boards.
- **Hover** any dot to see the note title.

## Path highlight

- Click a **hollow dot** → AuthorBoard draws the **shortest path** from the root to that note as an amber line.
- Everything not on the path **dims**, so the next step is immediately obvious.
- When you reach the destination (it becomes the root), the highlight clears – the walk is done.
- Selecting a different hollow dot recomputes the path from the current root.
- **While a path is active**, clicks inside FlowView **do not** change the selection, so you can't break the walk by accident. The **▶ arrows** still work.

## The note list

Beside the minimap is a **searchable, resizable list** of every note the minimap shows:

- **● entries**: active notes; clicking re-roots the view on them.
- **○ entries**: silhouettes; clicking toggles the path highlight.
- The selected silhouette is tinted **amber**, matching the minimap path color.
- **Enter** clears the search, **Esc** clears it and returns focus to the list.

## Back and forward

The **◀ / ▶** buttons at the bottom-left of the minimap:

- With an active path highlight: **step one hop back / forward** along the path.
- Without an active path: walk the **root history**, undoing or redoing your last re-root.

## Navigation and synchronization

- **Ctrl+0** or *right-click empty background → Reset view* restores zoom and pan.
- FlowView, the minimap and the note list are **always in sync**: whichever one you click, all three show the same root, the same neighbours and the same path.
- The board and FlowView share the same notes – edits to a note appear on both sides immediately.

## Tips

- Use FlowView as a **reading path**: click a distant note in the list, then step through with ◀/▶ until you arrive. The board stays undisturbed because you never leave the view.
- For a quick **overview of the neighbourhood**, the minimap alone is enough. Open FlowView when you actually want to read the notes.