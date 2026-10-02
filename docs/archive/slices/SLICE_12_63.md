# v0.12.63 — screen-safe dialog dock

- Main window startup geometry is capped to the primary screen's usable `availableGeometry()` instead of always forcing 1580×980.
- Bottom `Диалог` dock uses a layout-level `QScrollArea`, so controls remain reachable when the dock is vertically squeezed.
- Chat input changed from fixed 90 px to a flexible 48–90 px range.
- Existing QTextBrowser/QPlainTextEdit text scrolling remains unchanged.
- No AH, Ignition, inference, Workspace, perception, or persistence semantics changed.
