# v0.12.70 — Team 3 GUI startup dock binding fix

The Team 3 workspace-mode UI is retained unchanged. This patch fixes a startup crash introduced during the v0.12.69 GUI adoption.

## Root cause

`_set_workspace_mode()` controls `config_dock`, `node_dock` and `link_dock`, but the corresponding builder methods created those `QDockWidget` instances only in local variables. The first automatic `GRAPH` mode application therefore raised `AttributeError` during `MainWindow` construction.

## Fix

- bind Configuration dock as `self.config_dock`;
- bind Node Manager dock as `self.node_dock`;
- bind Link Manager dock as `self.link_dock`;
- retain the existing initialization order where all dock builders run before `_build_workspace_mode_menu()`;
- add a regression contract covering all three bindings and the initialization order.

No cognitive runtime, memory, perception, integration, inference or persistence behavior is changed.
