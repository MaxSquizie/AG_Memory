# GUI diagnostic performance — v0.36

Этот срез не меняет AH/Ignition/Workspace/AgentContext. Изменён только operator-facing diagnostic GUI.

## Почему тормозило

До v0.36 одновременно выполнялись:

- VisPy canvas refresh до 30 Hz;
- MainWindow status/Workspace/all-nodes refresh каждые 300 ms;
- LLM diagnostics refresh каждые 300 ms;
- повторный GraphInspector.snapshot() для status и ещё один для выбранного inspector;
- ACTIVE semantic projection всех canonical nodes при каждом all-nodes refresh;
- полный rebuild QTableWidget rows/cells;
- QPlainTextEdit.toPlainText() для сравнения больших prompt/log документов перед каждым setPlainText();
- построение Parser/Requests/Agent диагностик даже когда соответствующая вкладка не открыта.

## Что изменено

- text/table diagnostic cadence: 1 Hz;
- hidden docks are lazy;
- inactive LLM diagnostic tabs are lazy;
- docks reuse the immutable snapshot already built by the canvas;
- all-nodes semantic projection cached per UID and recomputed only for new/forced nodes;
- all-nodes stable rows update existing runtime cells instead of allocating a whole table each tick;
- live tables no longer use ResizeToContents;
- QPlainTextEdit payloads use a Python-side content cache rather than copying QTextDocument with toPlainText();
- Requests tab truncates its duplicate prompt preview; exact Agent CONTEXT / FINAL prompt remain untruncated in their dedicated tabs;
- selected-node inspector reuses the same status snapshot.

All caching is presentation-only and cannot affect cognitive state.
