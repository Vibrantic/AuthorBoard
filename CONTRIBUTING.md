# Contributing to AuthorBoard

Thank you for your interest! This project is licensed under the GPL-3.0-or-later; by contributing you agree that your contribution is released under the same license.

## Getting started

```bash
pip install -r requirements.txt -r requirements-dev.txt
python tests/run_all.py     # all tests must pass
```

Read the *Architecture* section of the developer docs first (`mkdocs serve`).

## Guidelines

1. **Small, focused changes.** One feature or fix per pull request.
2. **Docstrings and comments.** Every module, class and function has a docstring; comment the *why* of non-obvious code. The docs are generated from them.
3. **User-visible text goes through `tr("German source text")`.** German is the source language; add the English translation to `locales/en.json` (`python i18n.py update en`, `python i18n.py check en`). Data tables use `N_("text")` and translate with `tr()` where they are displayed.
4. **Keep undo working.** State that users can change must be part of `ProjectData` / `storage.py` so undo snapshots, autosave and saving see it.
5. **Add or extend a test** in `tests/` (headless Qt). Run `python tests/run_all.py`.
6. **Update the manuals** (`help/en`, `help/de`) and, for architectural changes, `docs/`.
7. Style: PEP 8, 4 spaces, line length around 100, English identifiers and docstrings.

## Reporting bugs

Describe what you did, what you expected and what happened. Include the terminal output of `python main.py` and, if possible, a (small) notebook file that reproduces the problem.
