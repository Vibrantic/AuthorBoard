# Accessibility in AuthorBoard

AuthorBoard is built with **Qt 6 (PySide6)**, which means it inherits many of the native accessibility features of your operating system. We want AuthorBoard to be a tool that is usable by everyone, including writers with visual, motor, or cognitive disabilities.

This document outlines the current accessibility support, known limitations, and our roadmap for improvements.

## Current Support

### 1. Keyboard Navigation
We believe that a writing tool should be fully usable without a mouse. 
- **Global Shortcuts:** Nearly every feature has a keyboard shortcut. (See *Help → Keyboard Shortcuts* or the `16-shortcuts.md` manual for a full list).
- **Tab Navigation:** You can navigate through the interface, dialogs, and forms using the `Tab` and `Shift+Tab` keys.
- **Focus Indicators:** Active buttons and text fields show a clear blue focus ring (the accent color).
- **The Board:** While the board is primarily mouse-driven, you can create notes via `Shift+Space`, navigate the note list via arrow keys, and open the editor via `F2`.

### 2. Screen Readers (Windows, macOS, Linux)
Because AuthorBoard uses native Qt widgets, it supports the OS-level Accessibility APIs:
- **Windows:** UI Automation (UIA) and Microsoft Active Accessibility (MSAA).
- **macOS:** VoiceOver.
- **Linux:** AT-SPI2 (Assistive Technology Service Provider Interface).

*Note: Custom-drawn elements (like the sticky notes on the board and the books on the shelf) rely on tooltips and standard keyboard focus. If you use a screen reader, we recommend using the **Notes Panel** (left dock) or the **Tree View** to navigate your notes, rather than the visual board.*

### 3. Visual Design & Color
- **Dark Mode:** AuthorBoard features a native, high-contrast dark theme designed to reduce eye strain during long writing sessions.
- **Color Independence:** Status indicators (Draft, Revise, Done) are not just colors; they are accompanied by text in the tooltips, Inspector, and Notes Panel.
- **Zooming:** 
  - You can zoom the board in and out using `Ctrl + Mouse Wheel` or `Ctrl+0` / `Ctrl+1`.
  - The font size in the Rich Text Editor can be adjusted in the toolbar.
  - You can change the UI scaling using your OS display settings.

### 4. Focus & Cognitive Load
- **Focus Mode:** Toggling *View → Focus Mode* dims everything on the board except the currently selected note and its connections, reducing visual noise.
- **Distraction-Free Editor:** Press `F11` inside the large editor to enter full-screen mode, hiding all other UI elements.
- **High Information Density:** The interface uses native OS tooltips to explain what buttons do without cluttering the screen.

## Known Limitations

- **The Board (Canvas):** Because the board is a custom 2D graphics scene, screen readers cannot easily parse it as a spatial map. We recommend screen reader users rely on the **Notes Panel** (left sidebar) to read and select notes, rather than trying to navigate the board visually.
- **Custom Graphics:** The books on the bookshelf and the pins/threads on the board are drawn programmatically. They are accessible via tooltips and the right-click menu, but they do not have native UIA accessibility roles.
- **Font Scaling:** The UI text scales with your OS settings, but the text *inside* the sticky notes on the board is fixed-size (unless you zoom the board). 

## Roadmap / How to Help

We are actively looking to improve accessibility. Here is what we want to do next:
- [ ] **High Contrast Mode:** Add an option to force a high-contrast theme (black background, white text) independent of the OS settings.
- [ ] **Board Accessibility:** Add keyboard navigation directly on the board (e.g., use arrow keys to jump between notes, `Enter` to open).
- [ ] **Screen Reader Focus:** Ensure the inspector clearly announces when a new note is selected.
- [ ] **UI Scaling Slider:** Allow scaling the UI fonts (100%, 125%, 150%) directly inside the app settings without changing OS settings.

If you are a developer with experience in Qt Accessibility (`QAccessible`), or if you are a user who relies on assistive technology and wants to provide feedback, please open an issue or start a discussion!

## Feedback

If you encounter an accessibility barrier while using AuthorBoard, please let us know. 
- Open an issue with the label `accessibility`.
- Describe the barrier and what assistive technology you are using (e.g., NVDA on Windows, VoiceOver on macOS, or high-contrast mode).
