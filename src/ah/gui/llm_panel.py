from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from enum import Enum
import ctypes
import json
import os
import sys

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ah.bootstrap import RuntimeServices
from ah.llm import OllamaBackend, OllamaClient, OllamaClientError
from ah.projection.contracts import AgentContext, AgentContextDiagnostic


def _working_set_bytes(pid: int | None) -> int | None:
    """Return resident working-set bytes without adding a runtime dependency.

    The GUI is primarily used on Windows, where Task Manager reports process
    working set. Linux support keeps tests/development useful. Failure to sample is
    diagnostic-only and must never affect the cognitive runtime.
    """
    if pid is None or pid <= 0:
        return None
    try:
        if sys.platform == "win32":
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return None
            try:
                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(counters)
                ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
                return int(counters.WorkingSetSize) if ok else None
            finally:
                kernel32.CloseHandle(handle)

        if sys.platform.startswith("linux"):
            fields = Path(f"/proc/{pid}/statm").read_text(encoding="ascii").split()
            if len(fields) >= 2:
                return int(fields[1]) * int(os.sysconf("SC_PAGE_SIZE"))

        if sys.platform == "darwin":
            import resource

            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            # macOS reports ru_maxrss in bytes for this API surface.
            return int(usage.ru_maxrss)
    except (OSError, ValueError, AttributeError):
        return None
    return None


def _format_ram(value: int | None) -> str:
    return "n/a" if value is None else f"{value / 2**30:.2f} GiB"


class LLMControlWidget(QWidget):
    """Operational + diagnostic panel for the one shared local LLM process.

    Prompt editors are live files outside AH memory. Diagnostic tabs are runtime-only:
    raw model output, decoded PerceptionResult, agent output and worker logs never enter
    AH/H and never affect AgentContext.
    """

    PROBE_PROMPTS = (
        "probe_system",
        "act_type",
        "predicate_start",
        "predicate_end",
        "predicate_symbol",
        "predicate_symbol_verify",
        "negation",
        "actant_start",
        "actant_end",
        "role_family",
        "role_participant",
        "role_description",
        "role_circumstance",
        "frame_relation",
        "relative_role",
        "role_cue",
        "lexeme_hypothesis",
        "antecedent_choice",
        "content_addressee",
        "control_subject",
        "template_hidden_valency",
        "clarification_answer",
        "query_mode",
        "requested_role",
    )

    start_requested = Signal()
    stop_requested = Signal()
    restart_requested = Signal()
    prompts_saved = Signal()
    ollama_model_changed = Signal(str)

    def __init__(
        self,
        services: RuntimeServices,
        config_path: str | Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.config_path = Path(config_path).resolve() if config_path is not None else None
        # Diagnostics are scoped to the most recently submitted GUI turn. This
        # prevents Parser/Agent tabs from showing the previous turn while a new
        # request is already running. Sequence floors are runtime-only UI state.
        self._turn_scope_initialized = False
        self._turn_active = False
        self._turn_source_text = ""
        self._turn_request_floor = 0
        self._turn_parser_floor = 0
        self._turn_memory_trace_text: str | None = None
        self._last_parser_render_key = None
        self._last_active_request_key = None
        self._last_completed_request_sequence = None

        root = QVBoxLayout(self)
        info = QFormLayout()
        self.status_label = QLabel()
        self.model_label = QLabel()
        self.model_label.setTextInteractionFlags(self.model_label.textInteractionFlags())
        self.role_label = QLabel("Одна модель / один процесс → Perception probes + Agent")
        self.loader_label = QLabel()
        self.device_policy_label = QLabel()
        self.cuda_label = QLabel()
        self.placement_label = QLabel()
        self.ram_label = QLabel()
        self.history_label = QLabel()
        self.perception_cfg_label = QLabel()
        self.agent_cfg_label = QLabel()
        self.stage_label = QLabel()
        self.ollama_model_row = QWidget()
        ollama_row_layout = QHBoxLayout(self.ollama_model_row)
        ollama_row_layout.setContentsMargins(0, 0, 0, 0)
        self.ollama_model_combo = QComboBox()
        self.ollama_refresh_button = QPushButton("Обновить")
        self.ollama_refresh_button.clicked.connect(self._refresh_ollama_models)
        self.ollama_model_combo.currentTextChanged.connect(self._on_ollama_model_selected)
        ollama_row_layout.addWidget(self.ollama_model_combo, 1)
        ollama_row_layout.addWidget(self.ollama_refresh_button)
        self.ollama_endpoint_label = QLabel()
        self.backend_label = QLabel()
        info.addRow("Статус", self.status_label)
        info.addRow("Backend", self.backend_label)
        info.addRow("Модель", self.model_label)
        info.addRow("Ollama model", self.ollama_model_row)
        info.addRow("Ollama URL", self.ollama_endpoint_label)
        info.addRow("Роли", self.role_label)
        info.addRow("Loader", self.loader_label)
        info.addRow("Device policy", self.device_policy_label)
        info.addRow("CUDA", self.cuda_label)
        info.addRow("Placement / VRAM", self.placement_label)
        info.addRow("Process RAM", self.ram_label)
        info.addRow("History buffer", self.history_label)
        info.addRow("Perception", self.perception_cfg_label)
        info.addRow("Agent", self.agent_cfg_label)
        info.addRow("Stage", self.stage_label)
        root.addLayout(info)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.restart_button = QPushButton("Restart")
        self.start_button.clicked.connect(self.start_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.restart_button.clicked.connect(self.restart_requested)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.restart_button)
        root.addLayout(buttons)

        self.tabs = QTabWidget()
        self.probe_prompt_widget = QWidget()
        probe_layout = QVBoxLayout(self.probe_prompt_widget)
        self.probe_selector = QComboBox()
        self.probe_selector.addItems(self.PROBE_PROMPTS)
        self.perception_editor = QPlainTextEdit()
        probe_layout.addWidget(self.probe_selector)
        probe_layout.addWidget(self.perception_editor, 1)
        self.probe_selector.currentTextChanged.connect(self._load_selected_probe_prompt)
        self.agent_editor = QPlainTextEdit()
        self.parser_raw_view = self._readonly("Сырой ответ parser LLM появится после perception-вызова")
        self.parser_decoded_view = self._readonly("Decoded PerceptionResult появится после успешного разбора")
        self.agent_raw_view = self._readonly("Сырой ответ agent LLM появится после генерации")
        self.agent_context_view = self._readonly(
            "Точный AgentContext (CURRENT INPUT + ACTIVE MEMORY + INFERENCE RESULTS) появится после turn"
        )
        self.agent_memory_view = self._readonly(
            "Память, реально переданная Agent LLM, и debug-причина включения каждого root появятся после turn"
        )
        self.agent_final_prompt_view = self._readonly(
            "Итоговый Agent prompt после chat-template появится после вызова модели"
        )
        self.requests_view = self._readonly("Последние LLM role calls")
        self.log_view = self._readonly("Лог загрузки / статуса LLM worker")
        self.log_view.setMaximumBlockCount(400)

        self.tabs.addTab(self.probe_prompt_widget, "Perception probe")
        self.tabs.addTab(self.agent_editor, "Agent prompt")
        self.tabs.addTab(self.parser_raw_view, "Parser RAW")
        self.tabs.addTab(self.parser_decoded_view, "Parser decoded")
        self.tabs.addTab(self.agent_raw_view, "Agent RAW")
        self.tabs.addTab(self.agent_context_view, "Agent CONTEXT")
        self.tabs.addTab(self.agent_memory_view, "Memory INPUT")
        self.tabs.addTab(self.agent_final_prompt_view, "Agent FINAL prompt")
        self.tabs.addTab(self.requests_view, "Requests")
        self.tabs.addTab(self.log_view, "Worker log")
        self.tabs.currentChanged.connect(lambda _index: self.refresh_status(force=True))
        root.addWidget(self.tabs, 1)

        save_prompts = QPushButton("Сохранить prompt-файлы")
        save_prompts.clicked.connect(self._save_prompts)
        root.addWidget(save_prompts)

        self.reload_prompts()
        self._sync_ollama_controls()
        self.refresh_status()

    def _is_ollama_backend(self) -> bool:
        return self.services.config.llm.backend.strip().lower() == "ollama"

    def _sync_ollama_controls(self) -> None:
        ollama = self._is_ollama_backend()
        self.ollama_model_row.setVisible(ollama)
        self.ollama_endpoint_label.setVisible(ollama)
        self.loader_label.setVisible(not ollama)
        self.device_policy_label.setVisible(not ollama)
        self.cuda_label.setVisible(not ollama)
        self.placement_label.setVisible(not ollama)
        if ollama:
            self._populate_ollama_models()

    def _populate_ollama_models(self, *, selected: str | None = None) -> None:
        cfg = self.services.config.llm
        models: list[str] = []
        if isinstance(self.services.llm, OllamaBackend):
            models = list(self.services.llm.list_models())
        if not models:
            try:
                models = OllamaClient(cfg.ollama_base_url).list_models()
            except OllamaClientError:
                models = []
        current = selected or cfg.ollama_model
        self.ollama_model_combo.blockSignals(True)
        self.ollama_model_combo.clear()
        if current and current not in models:
            self.ollama_model_combo.addItem(current)
        self.ollama_model_combo.addItems(models)
        if current:
            index = self.ollama_model_combo.findText(current)
            if index >= 0:
                self.ollama_model_combo.setCurrentIndex(index)
        self.ollama_model_combo.blockSignals(False)

    def _refresh_ollama_models(self) -> None:
        try:
            self._populate_ollama_models()
        except OllamaClientError as exc:
            QMessageBox.warning(self, "Ollama", str(exc))

    def _on_ollama_model_selected(self, model_name: str) -> None:
        if not self._is_ollama_backend() or not model_name:
            return
        if model_name == self.services.config.llm.ollama_model:
            return
        self.ollama_model_changed.emit(model_name)


    def begin_turn(self, source_text: str) -> None:
        """Start a new GUI diagnostics scope without touching LLM/AH state."""
        backend = self.services.llm
        records = (
            backend.request_diagnostics()
            if backend is not None and hasattr(backend, "request_diagnostics")
            else ()
        )
        parser = self.services.perception
        parser_history = (
            parser.diagnostics()
            if parser is not None and hasattr(parser, "diagnostics")
            else ()
        )
        self._turn_request_floor = max((r.sequence for r in records), default=0)
        self._turn_parser_floor = max((d.sequence for d in parser_history), default=0)
        self._turn_source_text = source_text
        self._turn_scope_initialized = True
        self._turn_active = True
        self._turn_memory_trace_text = None
        self._last_parser_render_key = None
        self._last_active_request_key = None
        self._last_completed_request_sequence = None
        waiting = f"TURN IN PROGRESS\nSOURCE:\n{source_text}"
        self._set_text(self.parser_raw_view, waiting + "\n\nWaiting for perception diagnostics…")
        self._set_text(self.parser_decoded_view, waiting + "\n\nWaiting for decoded PerceptionResult…")
        self._set_text(self.agent_raw_view, waiting + "\n\nWaiting for agent generation…")
        self._set_text(self.agent_context_view, waiting + "\n\nWaiting for AgentContext…")
        self._set_text(self.agent_memory_view, waiting + "\n\nWaiting for model-visible ACTIVE MEMORY…")
        self._set_text(self.agent_final_prompt_view, waiting + "\n\nWaiting for final Agent prompt…")
        self._set_text(self.requests_view, waiting + "\n\nWaiting for LLM role calls…")
        self.refresh_status()

    def finish_turn(self) -> None:
        """Freeze diagnostics on the just-finished turn until the next submit."""
        self._turn_active = False
        self.refresh_status()

    @staticmethod
    def _readonly(placeholder: str) -> QPlainTextEdit:
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlaceholderText(placeholder)
        return view

    def show_agent_context(
        self,
        context: AgentContext,
        diagnostic: AgentContextDiagnostic | None,
    ) -> None:
        """Expose the exact model-visible memory and a separate debug explanation.

        ``context.rendered`` is the logical user message sent to the Agent role.
        x/t/tick/lifecycle appear only in the debug half of ``Memory INPUT`` and
        are never appended to the LLM prompt.
        """
        self._set_text(
            self.agent_context_view,
            "MODEL-VISIBLE AGENTCONTEXT (exact logical user message before chat-template)\n"
            "=====================================================================\n"
            + context.rendered,
        )

        if context.workspace_blocks:
            visible_memory = "\n".join(f"- {block.semantic}" for block in context.workspace_blocks)
        else:
            visible_memory = "<EMPTY — no Workspace roots were serialized>"
        if context.inference_blocks:
            visible_inference = "\n".join(f"- {block.semantic}" for block in context.inference_blocks)
        else:
            visible_inference = "<EMPTY>"

        chunks = [
            "MODEL-VISIBLE MEMORY PAYLOAD (this part IS sent to Agent LLM)",
            "============================================================",
            "# ACTIVE MEMORY",
            visible_memory,
            "",
            "# INFERENCE RESULTS",
            visible_inference,
            "",
            "DEBUG EXPLANATION (NOT sent to Agent LLM)",
            "=========================================",
        ]
        if diagnostic is None:
            chunks.append("No projection-time diagnostic snapshot was captured.")
        else:
            chunks.append(
                f"projection tick={diagnostic.tick_index}; "
                f"turn-local settle ticks={diagnostic.settle_ticks}; "
                f"Workspace rule: x > {diagnostic.workspace_threshold:.6f}; "
                f"source Workspace roots={len(diagnostic.workspace)}; "
                f"model-visible memory blocks={len(context.workspace_blocks)}"
            )
            if not diagnostic.workspace:
                chunks.append("No ACTIVE roots crossed the Workspace threshold.")
            for row in diagnostic.workspace:
                lifecycle = row.lifecycle_state or "—"
                chunks.extend([
                    "",
                    f"[{row.position:02d}] INCLUDED because x={row.excitation:.6f} > "
                    f"t={diagnostic.workspace_threshold:.6f}",
                    f"root={row.root.uid} | kind={row.kind} | domain={row.domain or '—'} | "
                    f"output={row.output:.6f} | age={row.decay_age} | lifecycle={lifecycle}",
                    "SOURCE WORKSPACE SEMANTIC (debug only):",
                    row.semantic,
                ])
        self._turn_memory_trace_text = "\n".join(chunks)
        self._set_text(self.agent_memory_view, self._turn_memory_trace_text)

    def _probe_prompt_path(self, name: str | None = None) -> Path | None:
        cfg = self.services.config
        if cfg.llm.perception_protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            return cfg.paths.perception_prompt_path
        root = cfg.paths.perception_prompt_dir
        if root is None:
            return None
        selected = name or self.probe_selector.currentText()
        return root / f"{selected}.txt"

    def _agent_prompt_path(self) -> Path | None:
        return self.services.config.paths.agent_prompt_path or self.services.config.paths.system_prompt_path

    def reload_prompts(self) -> None:
        adaptive = self.services.config.llm.perception_protocol in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}
        self.probe_selector.setEnabled(adaptive)
        self._load_selected_probe_prompt()
        self.agent_editor.setPlainText(self._read(self._agent_prompt_path()))

    def _load_selected_probe_prompt(self, *_args) -> None:
        self.perception_editor.setPlainText(self._read(self._probe_prompt_path()))

    @staticmethod
    def _read(path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _save_prompts(self) -> None:
        perception = self._probe_prompt_path()
        agent = self._agent_prompt_path()
        if perception is None or agent is None:
            QMessageBox.warning(self, "LLM prompts", "Пути prompt-файлов не настроены.")
            return
        try:
            perception.parent.mkdir(parents=True, exist_ok=True)
            agent.parent.mkdir(parents=True, exist_ok=True)
            perception.write_text(self.perception_editor.toPlainText(), encoding="utf-8", newline="\n")
            agent.write_text(self.agent_editor.toPlainText(), encoding="utf-8", newline="\n")
        except Exception as exc:
            QMessageBox.critical(self, "LLM prompts", f"{type(exc).__name__}: {exc}")
            return
        self.prompts_saved.emit()

    @staticmethod
    def _set_text(view: QPlainTextEdit, text: str, *, follow_end: bool = False) -> None:
        # QPlainTextEdit.toPlainText() copies the whole QTextDocument. Doing that
        # every poll becomes very expensive for multi-kilobyte prompts/logs. Keep a
        # Python-side cache instead and repaint only when the payload truly changes.
        if view.property("ah_last_plain_text") == text:
            return
        view.setProperty("ah_last_plain_text", text)
        view.setUpdatesEnabled(False)
        try:
            view.setPlainText(text)
            if follow_end:
                cursor = view.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                view.setTextCursor(cursor)
        finally:
            view.setUpdatesEnabled(True)

    @staticmethod
    def _pretty(value) -> str:
        def encode(obj):
            if isinstance(obj, Enum):
                return obj.value
            return str(obj)
        return json.dumps(value, ensure_ascii=False, indent=2, default=encode)

    def _refresh_parser_diagnostics(self, *, force: bool = False) -> None:
        parser = self.services.perception
        if parser is None or not hasattr(parser, "diagnostics"):
            self._set_text(self.parser_raw_view, "")
            self._set_text(self.parser_decoded_view, "")
            return
        history = parser.diagnostics()
        if self._turn_scope_initialized:
            history = tuple(d for d in history if d.sequence > self._turn_parser_floor)
        if not history:
            if self._turn_scope_initialized and not self._turn_active:
                text = f"SOURCE:\n{self._turn_source_text}\n\nNo perception diagnostic was produced for this turn."
                self._set_text(self.parser_raw_view, text)
                self._set_text(self.parser_decoded_view, text)
            return
        diag = history[-1]
        render_key = (
            diag.sequence,
            len(diag.attempts),
            diag.final_error,
            diag.decoded is not None,
        )
        if not force and render_key == self._last_parser_render_key:
            return
        self._last_parser_render_key = render_key
        raw_parts = [f"SOURCE:\n{diag.source_text}"]
        for index, attempt in enumerate(diag.attempts, start=1):
            retry = f" retry={attempt.retry_index}" if attempt.retry_index else ""
            raw_parts.append(f"\n--- PROBE {index}: {attempt.role}{retry} ---")
            if attempt.prompt:
                raw_parts.append(f"\nINPUT:\n{attempt.prompt}")
            raw_parts.append(f"\nRAW:\n{attempt.raw_text}")
            if attempt.normalized_answer is not None:
                raw_parts.append(f"\nACCEPTED: {attempt.normalized_answer}")
            if attempt.error:
                raw_parts.append(f"\nVALIDATION ERROR: {attempt.error}")
        if diag.final_error:
            raw_parts.append(f"\nFINAL ERROR: {diag.final_error}")
        self._set_text(self.parser_raw_view, "\n".join(raw_parts))

        if diag.decoded is None:
            decoded = {"status": "INVALID", "error": diag.final_error}
        elif diag.final_error:
            decoded = {
                "status": "INVALID",
                "error": diag.final_error,
                "perception": asdict(diag.decoded),
            }
        else:
            decoded = {"status": "OK", "perception": asdict(diag.decoded)}
        self._set_text(self.parser_decoded_view, self._pretty(decoded))

    @staticmethod
    def _extract_context_section(rendered: str, heading: str) -> str:
        lines = rendered.splitlines()
        try:
            start = lines.index(heading) + 1
        except ValueError:
            return ""
        out: list[str] = []
        for line in lines[start:]:
            if line.startswith("# "):
                break
            out.append(line)
        return "\n".join(out).strip()

    def _refresh_request_diagnostics(self, *, force: bool = False) -> None:
        backend = self.services.llm
        if backend is None or not hasattr(backend, "request_diagnostics"):
            return

        current = self.tabs.currentWidget()
        active = (
            backend.active_request_diagnostic()
            if hasattr(backend, "active_request_diagnostic")
            else None
        )
        if (
            active is not None
            and active.role.startswith("agent")
            and (not self._turn_scope_initialized or active.sequence > self._turn_request_floor)
            and current in {self.agent_context_view, self.agent_memory_view}
        ):
            active_key = (active.sequence, active.role, len(active.prompt))
            if force or active_key != self._last_active_request_key:
                self._last_active_request_key = active_key
                if current is self.agent_context_view:
                    self._set_text(
                        self.agent_context_view,
                        f"REQUEST #{active.sequence} (IN FLIGHT)\nROLE: {active.role}\n\n"
                        "MODEL-VISIBLE AGENTCONTEXT (exact logical user message before chat-template)\n"
                        "=====================================================================\n"
                        + active.prompt,
                    )
                elif current is self.agent_memory_view and self._turn_memory_trace_text is None:
                    active_memory = self._extract_context_section(active.prompt, "# ACTIVE MEMORY")
                    inference = self._extract_context_section(active.prompt, "# INFERENCE RESULTS")
                    self._set_text(
                        self.agent_memory_view,
                        "MODEL-VISIBLE MEMORY PAYLOAD (LIVE; this part IS being sent to Agent LLM)\n"
                        "==================================================================\n"
                        "# ACTIVE MEMORY\n" + (active_memory or "<EMPTY>")
                        + "\n\n# INFERENCE RESULTS\n" + (inference or "<EMPTY>")
                        + "\n\nDEBUG EXPLANATION (NOT sent to Agent LLM)\n"
                          "=========================================\n"
                          "The exact x/t trace is attached when the turn returns; "
                          "the semantic payload above is already the live request.",
                    )

        records = backend.request_diagnostics()
        if self._turn_scope_initialized:
            records = tuple(r for r in records if r.sequence > self._turn_request_floor)
        if not records:
            if self._turn_scope_initialized and not self._turn_active:
                text = f"SOURCE:\n{self._turn_source_text}\n\nNo LLM requests were recorded for this turn."
                if current is self.agent_raw_view:
                    self._set_text(self.agent_raw_view, text)
                elif current is self.agent_context_view:
                    self._set_text(self.agent_context_view, text)
                elif current is self.agent_memory_view and self._turn_memory_trace_text is None:
                    self._set_text(self.agent_memory_view, text)
                elif current is self.agent_final_prompt_view:
                    self._set_text(self.agent_final_prompt_view, text)
                elif current is self.requests_view:
                    self._set_text(self.requests_view, text)
            return

        agent = next(
            (record for record in reversed(records) if record.role.startswith("agent")),
            None,
        )
        if agent is not None:
            if current is self.agent_raw_view:
                text = (
                    f"REQUEST #{agent.sequence}\nROLE: {agent.role}\n\n"
                    f"RAW RESPONSE:\n{agent.response_text}"
                )
                if agent.error:
                    text += f"\n\nERROR:\n{agent.error}"
                self._set_text(self.agent_raw_view, text)
            elif current is self.agent_context_view:
                self._set_text(
                    self.agent_context_view,
                    f"REQUEST #{agent.sequence}\nROLE: {agent.role}\n\n"
                    "MODEL-VISIBLE AGENTCONTEXT (exact logical user message before chat-template)\n"
                    "=====================================================================\n"
                    + agent.prompt,
                )
            elif current is self.agent_memory_view and self._turn_memory_trace_text is None:
                active_memory = self._extract_context_section(agent.prompt, "# ACTIVE MEMORY")
                inference = self._extract_context_section(agent.prompt, "# INFERENCE RESULTS")
                fallback = (
                    "MODEL-VISIBLE MEMORY PAYLOAD (this part IS sent to Agent LLM)\n"
                    "============================================================\n"
                    "# ACTIVE MEMORY\n" + (active_memory or "<EMPTY>")
                    + "\n\n# INFERENCE RESULTS\n" + (inference or "<EMPTY>")
                    + "\n\nDEBUG EXPLANATION (NOT sent to Agent LLM)\n"
                      "=========================================\n"
                      "Projection-time x/t trace is not available for this request."
                )
                self._set_text(self.agent_memory_view, fallback)
            elif current is self.agent_final_prompt_view:
                if agent.rendered_prompt:
                    token_line = (
                        f"INPUT TOKENS: {agent.input_tokens}\n"
                        if agent.input_tokens is not None
                        else ""
                    )
                    final_prompt = (
                        f"REQUEST #{agent.sequence}\nROLE: {agent.role}\n"
                        + token_line
                        + "\nEXACT CHAT-TEMPLATE INPUT SENT TO MODEL:\n"
                        + agent.rendered_prompt
                    )
                else:
                    final_prompt = (
                        f"REQUEST #{agent.sequence}\nROLE: {agent.role}\n\n"
                        f"SYSTEM MESSAGE:\n{agent.system}\n\n"
                        f"USER / AGENTCONTEXT MESSAGE:\n{agent.prompt}"
                    )
                self._set_text(self.agent_final_prompt_view, final_prompt)
        elif self._turn_scope_initialized and current in {
            self.agent_raw_view, self.agent_context_view, self.agent_memory_view, self.agent_final_prompt_view
        }:
            state = "Waiting for agent generation…" if self._turn_active else "No agent response was produced for this turn."
            base = f"SOURCE:\n{self._turn_source_text}\n\n{state}"
            if current is self.agent_raw_view:
                self._set_text(self.agent_raw_view, base)
            elif current is self.agent_context_view:
                self._set_text(self.agent_context_view, base)
            elif current is self.agent_memory_view and self._turn_memory_trace_text is None:
                self._set_text(self.agent_memory_view, base)
            elif current is self.agent_final_prompt_view:
                self._set_text(self.agent_final_prompt_view, base)

        if current is self.requests_view:
            chunks: list[str] = []
            for record in records[-12:]:
                prompt_preview = record.prompt
                if len(prompt_preview) > 4000:
                    prompt_preview = prompt_preview[:4000] + "\n… <truncated in Requests tab; exact Agent prompt has its own tabs>"
                response_preview = record.response_text
                if len(response_preview) > 1200:
                    response_preview = response_preview[:1200] + "\n… <truncated in Requests tab>"
                chunks.append(
                    f"#{record.sequence} {record.role} req={record.req_id}\n"
                    f"PROMPT:\n{prompt_preview}\n\n"
                    f"RESPONSE:\n{response_preview}"
                    + (f"\nERROR: {record.error}" if record.error else "")
                )
            self._set_text(self.requests_view, "\n\n==============================\n\n".join(chunks))

    def refresh_status(self, *, force: bool = False) -> None:
        if not force and not self.isVisible():
            return
        backend = self.services.llm
        cfg = self.services.config
        self._sync_ollama_controls()
        self.backend_label.setText(cfg.llm.backend)
        if self._is_ollama_backend():
            self.model_label.setText(cfg.llm.ollama_model or "<not configured>")
            self.ollama_endpoint_label.setText(cfg.llm.ollama_base_url)
        else:
            self.model_label.setText(str(cfg.paths.llm_model_dir or "<not configured>"))
            self.ollama_endpoint_label.clear()
        self.history_label.setText(
            f"{cfg.llm.history_messages} сообщений — "
            + ("stateless" if cfg.llm.history_messages == 0 else "history enabled")
        )
        self.perception_cfg_label.setText(
            f"{cfg.llm.perception_protocol}, retry={cfg.llm.perception_probe_retry_attempts}, "
            f"acts≤{cfg.llm.perception_max_acts}, actants≤{cfg.llm.perception_max_actants_per_act}, "
            f"predicate S/T={'lexical deterministic' if cfg.llm.perception_protocol == 'adaptive_v3' else cfg.llm.perception_predicate_symbol_language}, "
            f"T={cfg.llm.perception.temperature:g}"
        )
        self.loader_label.setText(f"{cfg.llm.loader_type} (text-only)")
        if not self._is_ollama_backend():
            self.device_policy_label.setText(
                f"device_map={cfg.llm.device_map}; dtype={cfg.llm.dtype}; 4bit={'ON' if cfg.llm.use_4bit else 'OFF'}"
            )
        self.cuda_label.setText("not probed")
        self.placement_label.setText("not loaded")
        self.agent_cfg_label.setText(
            f"T={cfg.llm.agent.temperature:g}, max_new={cfg.llm.agent.max_new_tokens}, "
            f"top_p={cfg.llm.agent.top_p:g}, top_k={cfg.llm.agent.top_k}"
        )
        gui_ram = _working_set_bytes(os.getpid())
        self.ram_label.setText(f"GUI={_format_ram(gui_ram)} | LLM=n/a")
        if backend is None:
            self.status_label.setText("DISABLED")
            self.stage_label.setText("-")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.restart_button.setEnabled(False)
            return

        status = backend.status()
        llm_ram = _working_set_bytes(status.pid)
        if self._is_ollama_backend():
            self.ram_label.setText(f"GUI={_format_ram(gui_ram)} | Ollama remote")
        else:
            self.ram_label.setText(
                f"GUI={_format_ram(gui_ram)} | LLM={_format_ram(llm_ram)}"
            )
        if self._is_ollama_backend():
            model_text = cfg.llm.ollama_model or "<not configured>"
        else:
            model_text = status.model_dir or status.configured_model_dir or "<not configured>"
            if status.running and status.model_dir != status.configured_model_dir:
                model_text += f"  (config → {status.configured_model_dir}; restart required)"
        self.model_label.setText(model_text)
        self.status_label.setText(
            ("READY" if status.ready else "RUNNING" if status.running else "STOPPED")
            + (f" | pid={status.pid}" if status.pid else "")
            + (f" | ctx={status.context_window}" if status.context_window else "")
            + (f" | transformers={status.transformers_version}" if status.transformers_version else "")
        )
        if self._is_ollama_backend():
            self.loader_label.setText("ollama (HTTP)")
            if status.cuda_summary:
                self.cuda_label.setText(status.cuda_summary)
            if status.placement_summary:
                self.placement_label.setText(status.placement_summary)
        elif status.loader_type:
            self.loader_label.setText(f"{status.loader_type} (text-only)")
            if status.cuda_summary:
                self.cuda_label.setText(status.cuda_summary)
            if status.placement_summary:
                quant = " | NF4 4-bit" if status.effective_4bit else ""
                self.placement_label.setText(status.placement_summary + quant)
        self.stage_label.setText(
            status.current_stage
            + (f" | last role={status.last_role}" if status.last_role else "")
            + f" | requests={status.request_count}"
        )
        self.start_button.setEnabled(not status.running)
        self.stop_button.setEnabled(status.running)
        self.restart_button.setEnabled(True)
        current = self.tabs.currentWidget()
        if current is self.log_view:
            self._set_text(self.log_view, "\n".join(status.recent_log), follow_end=True)
        if current in {self.parser_raw_view, self.parser_decoded_view}:
            self._refresh_parser_diagnostics(force=force)
        elif current in {
            self.agent_raw_view,
            self.agent_context_view,
            self.agent_memory_view,
            self.agent_final_prompt_view,
            self.requests_view,
        }:
            self._refresh_request_diagnostics(force=force)
