from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ah.documents import last_document_summary_runtime_state


class DocumentPanelWidget(QWidget):
    """UI boundary for full-document ingestion and AH-only summarization."""

    ingest_requested = Signal(str)
    summary_requested = Signal(str, str)
    activate_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source_ref: str | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        title = QLabel("Документ → AH")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)
        intro = QLabel(
            "Полный проход: chunks → perception → единый DOCUMENT batch → canonical AH. "
            "Summary получает только bounded source-scoped AgentContext slices; raw chunks "
            "в Agent LLM не передаются."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Путь к .txt / .md / .docx")
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("Выбрать…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        self.ingest_button = QPushButton("Загрузить в AH")
        self.ingest_button.clicked.connect(self._emit_ingest)
        row.addWidget(self.ingest_button)
        layout.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        stats = QFrame()
        grid = QHBoxLayout(stats)
        grid.setContentsMargins(8, 6, 8, 6)
        self.file_stat = QLabel("Файл: —")
        self.chunk_stat = QLabel("Chunks: —")
        self.coverage_stat = QLabel("Coverage: —")
        self.source_stat = QLabel("Source: —")
        for widget in (self.file_stat, self.chunk_stat, self.coverage_stat, self.source_stat):
            widget.setWordWrap(True)
            grid.addWidget(widget, 1)
        layout.addWidget(stats)

        self.status = QLabel("Документ ещё не загружен")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.context_view = QPlainTextEdit()
        self.context_view.setReadOnly(True)
        self.context_view.setPlaceholderText("Source-scoped AgentContext")
        self.context_view.setMinimumHeight(110)
        layout.addWidget(self.context_view, 1)

        request_row = QHBoxLayout()
        self.summary_request = QLineEdit("Сделай краткое содержание документа в 5–7 предложениях.")
        request_row.addWidget(self.summary_request, 1)
        self.activate_button = QPushButton("Построить контекст")
        self.activate_button.setEnabled(False)
        self.activate_button.clicked.connect(self._emit_activate)
        request_row.addWidget(self.activate_button)
        self.summary_button = QPushButton("Сделать summary")
        self.summary_button.setEnabled(False)
        self.summary_button.clicked.connect(self._emit_summary)
        request_row.addWidget(self.summary_button)
        layout.addLayout(request_row)

        self.continuation_view = QPlainTextEdit()
        self.continuation_view.setReadOnly(True)
        self.continuation_view.setPlaceholderText(
            "Continuation diagnostics: slice, cursor, primary/overlap refs, budget, stop reason, coverage"
        )
        self.continuation_view.setMinimumHeight(115)
        layout.addWidget(self.continuation_view)

        self.summary_view = QPlainTextEdit()
        self.summary_view.setReadOnly(True)
        self.summary_view.setPlaceholderText("Memory-grounded summary")
        self.summary_view.setMinimumHeight(130)
        layout.addWidget(self.summary_view, 1)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите документ", "", "Documents (*.txt *.md *.markdown *.docx);;All files (*)"
        )
        if path:
            self.path_edit.setText(path)

    def _emit_ingest(self) -> None:
        if path := self.path_edit.text().strip():
            self.ingest_requested.emit(path)

    def _emit_activate(self) -> None:
        if self._source_ref:
            self.activate_requested.emit(self._source_ref)

    def _emit_summary(self) -> None:
        if self._source_ref:
            self.summary_requested.emit(self._source_ref, self.summary_request.text().strip())

    def set_busy(self, busy: bool) -> None:
        self.ingest_button.setEnabled(not busy)
        enabled = not busy and self._source_ref is not None
        self.activate_button.setEnabled(enabled)
        self.summary_button.setEnabled(enabled)
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)

    def set_ingestion_result(self, result) -> None:
        self._source_ref = result.source_ref
        self.file_stat.setText(f"Файл: {result.title or '—'}")
        self.chunk_stat.setText(f"Chunks: {len(result.chunks)}")
        self.coverage_stat.setText(f"Coverage: {result.coverage_ratio:.1%}")
        self.source_stat.setText(f"Source: {result.source_ref}")
        self.status.setText(
            f"Готово: {len(result.source_text):,} символов, один DOCUMENT commit."
        )
        self.context_view.clear()
        self.continuation_view.clear()
        self.summary_view.clear()
        self.activate_button.setEnabled(True)
        self.summary_button.setEnabled(True)

    def set_context(self, rendered: str, workspace_refs: tuple[str, ...]) -> None:
        self.context_view.setPlainText(rendered or "AgentContext пуст")
        self.status.setText(f"Source context построен; runtime Workspace: {len(workspace_refs)} refs.")

    def _render_continuation_diagnostics(self) -> None:
        if not self._source_ref:
            self.continuation_view.clear()
            return
        state = last_document_summary_runtime_state(self._source_ref)
        if state is None:
            self.continuation_view.setPlainText("Continuation diagnostics ещё не получены.")
            return
        lines = []
        for item in state.slice_diagnostics:
            lines.append(
                f"slice {item.slice_index:02d}: cursor {item.cursor_start}→{item.cursor_end} | "
                f"primary={len(item.primary_refs)} | overlap={len(item.overlap_refs)} | "
                f"workspace={len(item.workspace_refs)} | ~{item.estimated_tokens} tok | "
                f"done={'yes' if item.done else 'no'}"
            )
        lines.append("")
        lines.append(
            f"stop={state.stop_reason} | source primary coverage="
            f"{state.primary_covered}/{state.source_primary_total} "
            f"({state.source_coverage_ratio:.1%}) | final ~{state.final_estimated_tokens} tok"
        )
        self.continuation_view.setPlainText("\n".join(lines))

    def set_summary(self, text: str) -> None:
        self.summary_view.setPlainText(text)
        self._render_continuation_diagnostics()
        state = (
            last_document_summary_runtime_state(self._source_ref)
            if self._source_ref
            else None
        )
        if state is None:
            self.status.setText("Summary построен из source-scoped AH context.")
        else:
            self.status.setText(
                f"Summary готов: {len(state.slice_diagnostics)} slices, "
                f"coverage {state.source_coverage_ratio:.1%}, stop={state.stop_reason}."
            )
