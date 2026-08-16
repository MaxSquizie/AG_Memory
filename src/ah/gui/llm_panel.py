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

    def __init__(self, services: RuntimeServices, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        # Diagnostics are scoped to the most recently submitted GUI turn. This
        # prevents Parser/Agent tabs from showing the previous turn while a new
        # request is already running. Sequence floors are runtime-only UI state.
        self._turn_scope_initialized = False
        self._turn_active = False
        self._turn_source_text = ""
        self._turn_request_floor = 0
        self._turn_parser_floor = 0

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
        info.addRow("Статус", self.status_label)
        info.addRow("Модель", self.model_label)
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
        self.requests_view = self._readonly("Последние LLM role calls")
        self.log_view = self._readonly("Лог загрузки / статуса LLM worker")
        self.log_view.setMaximumBlockCount(400)

        self.tabs.addTab(self.probe_prompt_widget, "Perception probe")
        self.tabs.addTab(self.agent_editor, "Agent prompt")
        self.tabs.addTab(self.parser_raw_view, "Parser RAW")
        self.tabs.addTab(self.parser_decoded_view, "Parser decoded")
        self.tabs.addTab(self.agent_raw_view, "Agent RAW")
        self.tabs.addTab(self.requests_view, "Requests")
        self.tabs.addTab(self.log_view, "Worker log")
        root.addWidget(self.tabs, 1)

        save_prompts = QPushButton("Сохранить prompt-файлы")
        save_prompts.clicked.connect(self._save_prompts)
        root.addWidget(save_prompts)

        self.reload_prompts()
        self.refresh_status()


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
        waiting = f"TURN IN PROGRESS\nSOURCE:\n{source_text}"
        self._set_text(self.parser_raw_view, waiting + "\n\nWaiting for perception diagnostics…")
        self._set_text(self.parser_decoded_view, waiting + "\n\nWaiting for decoded PerceptionResult…")
        self._set_text(self.agent_raw_view, waiting + "\n\nWaiting for agent generation…")
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
        if text == view.toPlainText():
            return
        view.setPlainText(text)
        if follow_end:
            cursor = view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            view.setTextCursor(cursor)

    @staticmethod
    def _pretty(value) -> str:
        def encode(obj):
            if isinstance(obj, Enum):
                return obj.value
            return str(obj)
        return json.dumps(value, ensure_ascii=False, indent=2, default=encode)

    def _refresh_parser_diagnostics(self) -> None:
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

    def _refresh_request_diagnostics(self) -> None:
        backend = self.services.llm
        if backend is None or not hasattr(backend, "request_diagnostics"):
            return
        records = backend.request_diagnostics()
        if self._turn_scope_initialized:
            records = tuple(r for r in records if r.sequence > self._turn_request_floor)
        if not records:
            if self._turn_scope_initialized and not self._turn_active:
                text = f"SOURCE:\n{self._turn_source_text}\n\nNo LLM requests were recorded for this turn."
                self._set_text(self.agent_raw_view, text)
                self._set_text(self.requests_view, text)
            return

        agent = next((record for record in reversed(records) if record.role == "agent"), None)
        if agent is not None:
            text = (
                f"REQUEST #{agent.sequence}\nROLE: {agent.role}\n\n"
                f"RAW RESPONSE:\n{agent.response_text}"
            )
            if agent.error:
                text += f"\n\nERROR:\n{agent.error}"
            self._set_text(self.agent_raw_view, text)
        elif self._turn_scope_initialized:
            state = "Waiting for agent generation…" if self._turn_active else "No agent response was produced for this turn."
            self._set_text(
                self.agent_raw_view,
                f"SOURCE:\n{self._turn_source_text}\n\n{state}",
            )

        chunks: list[str] = []
        for record in records[-12:]:
            response_preview = record.response_text
            if len(response_preview) > 1200:
                response_preview = response_preview[:1200] + "\n… <truncated in Requests tab>"
            chunks.append(
                f"#{record.sequence} {record.role} req={record.req_id}\n"
                f"PROMPT:\n{record.prompt}\n\n"
                f"RESPONSE:\n{response_preview}"
                + (f"\nERROR: {record.error}" if record.error else "")
            )
        self._set_text(self.requests_view, "\n\n==============================\n\n".join(chunks))

    def refresh_status(self) -> None:
        backend = self.services.llm
        cfg = self.services.config
        self.model_label.setText(str(cfg.paths.llm_model_dir or "<not configured>"))
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
        self.ram_label.setText(
            f"GUI={_format_ram(gui_ram)} | LLM={_format_ram(llm_ram)}"
        )
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
        if status.loader_type:
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
        self._set_text(self.log_view, "\n".join(status.recent_log), follow_end=True)
        self._refresh_parser_diagnostics()
        self._refresh_request_diagnostics()
