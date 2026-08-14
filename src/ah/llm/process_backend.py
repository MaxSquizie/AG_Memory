from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any
import json
import os
import subprocess
import sys
import time
import uuid

from ah.config import AppConfig


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMRequestDiagnostic:
    sequence: int
    req_id: str
    role: str
    prompt: str
    system: str
    response_text: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class LLMBackendStatus:
    running: bool
    pid: int | None
    ready: bool
    model_dir: str
    configured_model_dir: str
    loader_type: str | None
    context_window: int | None
    transformers_version: str | None
    cuda_available: bool | None
    cuda_summary: str | None
    placement_summary: str | None
    effective_4bit: bool | None
    current_stage: str
    last_role: str | None
    request_count: int
    recent_log: tuple[str, ...]


class LocalLLMProcessBackend:
    """One local model process shared by perception and agent roles.

    The backend deliberately owns *no conversation history*. Every request is a
    fresh mechanical call consisting only of a role-specific system prompt and the
    current request payload. `llm.history_messages=0` makes that invariant explicit.

    Parser and agent therefore share model weights/VRAM without sharing hidden chat
    context or KV cache between requests. AH AgentContext is supplied explicitly by
    the caller and remains the only cognitive context for the response role.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._proc: subprocess.Popen[str] | None = None
        self._reader: Thread | None = None
        self._ready = Event()
        self._stdin_lock = Lock()
        self._rpc_lock = Lock()
        self._status_lock = Lock()
        self._rpc: dict[str, Queue[dict[str, Any]]] = {}
        self._early: dict[str, dict[str, Any]] = {}
        self._recent_log: deque[str] = deque(maxlen=200)
        self._ready_info: dict[str, Any] = {}
        self._stage = "stopped"
        self._last_role: str | None = None
        self._request_count = 0
        self._request_diagnostics: deque[LLMRequestDiagnostic] = deque(maxlen=50)

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> LLMBackendStatus:
        proc = self._proc
        with self._status_lock:
            info = dict(self._ready_info)
            return LLMBackendStatus(
                running=self.is_running,
                pid=(None if proc is None or proc.poll() is not None else proc.pid),
                ready=self._ready.is_set(),
                model_dir=str(info.get("model_dir") or self.config.paths.llm_model_dir or ""),
                configured_model_dir=str(self.config.paths.llm_model_dir or ""),
                loader_type=(None if info.get("loader_type") is None else str(info.get("loader_type"))),
                context_window=(None if info.get("ctx_total") is None else int(info.get("ctx_total"))),
                transformers_version=(None if info.get("transformers_version") is None else str(info.get("transformers_version"))),
                cuda_available=(None if not isinstance(info.get("cuda"), dict) else bool(info["cuda"].get("available"))),
                cuda_summary=self._format_cuda(info.get("cuda")),
                placement_summary=self._format_placement(info.get("placement")),
                effective_4bit=(None if info.get("effective_4bit") is None else bool(info.get("effective_4bit"))),
                current_stage=self._stage,
                last_role=self._last_role,
                request_count=self._request_count,
                recent_log=tuple(self._recent_log),
            )

    @staticmethod
    def _format_cuda(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        devices = value.get("devices") or []
        parts = []
        for d in devices:
            if not isinstance(d, dict):
                continue
            total = d.get("total_bytes")
            total_text = f" {float(total)/2**30:.1f} GiB" if isinstance(total, (int, float)) else ""
            parts.append(f"cuda:{d.get('index')} {d.get('name')}{total_text}")
        prefix = f"available={bool(value.get('available'))}; torch CUDA={value.get('torch_cuda_version')}"
        return prefix + (("; " + "; ".join(parts)) if parts else "")

    @staticmethod
    def _format_placement(value: Any) -> str | None:
        if not isinstance(value, dict):
            return None
        devices = value.get("devices") or []
        chunks = ["devices=" + ", ".join(map(str, devices))] if devices else ["devices=unknown"]
        for m in value.get("cuda_memory") or []:
            if not isinstance(m, dict):
                continue
            allocated = float(m.get("allocated_bytes", 0)) / 2**30
            reserved = float(m.get("reserved_bytes", 0)) / 2**30
            chunks.append(f"cuda:{m.get('index')} allocated={allocated:.2f} GiB reserved={reserved:.2f} GiB")
        return "; ".join(chunks)

    def request_diagnostics(self) -> tuple[LLMRequestDiagnostic, ...]:
        """Return a thread-safe snapshot of recent role calls for GUI diagnostics.

        These records are runtime-only. They are never persisted into AH/H and never
        participate in AgentContext.
        """
        with self._status_lock:
            return tuple(self._request_diagnostics)

    def _record_request(
        self,
        *,
        req_id: str,
        role: str,
        prompt: str,
        system: str,
        response_text: str,
        error: str | None = None,
    ) -> None:
        with self._status_lock:
            self._request_diagnostics.append(
                LLMRequestDiagnostic(
                    sequence=self._request_count,
                    req_id=req_id,
                    role=role,
                    prompt=prompt,
                    system=system,
                    response_text=response_text,
                    error=error,
                )
            )

    def build_command(self) -> list[str]:
        cfg = self.config
        model_dir = cfg.paths.llm_model_dir
        if model_dir is None:
            raise ValueError("paths.llm_model_dir is not configured")

        if cfg.llm.engine_script is not None:
            cmd = [sys.executable, "-u", str(cfg.llm.engine_script), "--serve", "--base_model", str(model_dir)]
            cmd += ["--loader_type", cfg.llm.loader_type]
            cmd += ["--device_map", cfg.llm.device_map]
            cmd += ["--max_new_tokens", str(cfg.llm.max_new_tokens)]
            cmd += ["--temperature", str(cfg.llm.temperature)]
            cmd += ["--top_p", str(cfg.llm.top_p)]
            cmd += ["--top_k", str(cfg.llm.top_k)]
            cmd += ["--repetition_penalty", str(cfg.llm.repetition_penalty)]
            if cfg.paths.tokenizer_dir:
                cmd += ["--tokenizer_dir", str(cfg.paths.tokenizer_dir)]
            if cfg.paths.adapter_dir:
                cmd += ["--adapter_path", str(cfg.paths.adapter_dir)]
            if cfg.llm.use_4bit:
                cmd += ["--use_4bit"]
            if cfg.llm.ctx_total > 0:
                cmd += ["--ctx_total", str(cfg.llm.ctx_total)]
            if cfg.llm.enable_thinking:
                cmd += ["--enable_thinking"]
            if not cfg.llm.strip_thinking:
                cmd += ["--no-strip_thinking"]
            return cmd

        cmd = [sys.executable, "-u", "-m", "ah.llm.worker", "--serve", "--model-dir", str(model_dir)]
        cmd += ["--loader-type", cfg.llm.loader_type]
        cmd += ["--device-map", cfg.llm.device_map]
        cmd += ["--dtype", cfg.llm.dtype]
        if cfg.paths.tokenizer_dir:
            cmd += ["--tokenizer-dir", str(cfg.paths.tokenizer_dir)]
        if cfg.paths.adapter_dir:
            cmd += ["--adapter-dir", str(cfg.paths.adapter_dir)]
        if cfg.llm.use_4bit:
            cmd += ["--use-4bit"]
        if cfg.llm.ctx_total > 0:
            cmd += ["--ctx-total", str(cfg.llm.ctx_total)]
        if cfg.llm.trust_remote_code:
            cmd += ["--trust-remote-code"]
        if cfg.llm.local_files_only:
            cmd += ["--local-files-only"]
        if cfg.llm.enable_thinking:
            cmd += ["--enable-thinking"]
        if cfg.llm.strip_thinking:
            cmd += ["--strip-thinking"]
        return cmd

    def start(self) -> None:
        if self.is_running:
            return
        if self.config.llm.history_messages != 0:
            raise ValueError("Only stateless LLM requests (history_messages=0) are supported")
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        self._ready.clear()
        with self._status_lock:
            self._ready_info = {}
            self._recent_log.clear()
            self._stage = "starting"
        self._proc = subprocess.Popen(
            self.build_command(),
            cwd=str(self.config.paths.project_dir),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._reader = Thread(target=self._reader_loop, name="AH-LLM-stdout", daemon=True)
        self._reader.start()
        deadline = time.monotonic() + self.config.llm.startup_timeout_seconds
        while not self._ready.is_set() and time.monotonic() < deadline:
            if self._proc is None or self._proc.poll() is not None:
                status = self.status()
                tail = "\n".join(status.recent_log[-20:])
                self.stop()
                raise RuntimeError(
                    "Local LLM process exited during startup" + (f"\n{tail}" if tail else "")
                )
            self._ready.wait(0.10)
        if not self._ready.is_set():
            status = self.status()
            self.stop()
            tail = "\n".join(status.recent_log[-20:])
            raise TimeoutError("Local LLM process did not become ready" + (f"\n{tail}" if tail else ""))

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            with self._status_lock:
                self._stage = "stopped"
            return
        try:
            if proc.stdin and proc.poll() is None:
                try:
                    proc.stdin.write(json.dumps({"req": "shutdown"}) + "\n")
                    proc.stdin.flush()
                except Exception:
                    pass
            deadline = time.time() + 2.0
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.05)
            if proc.poll() is None:
                proc.terminate()
        finally:
            self._proc = None
            self._ready.clear()
            with self._status_lock:
                self._stage = "stopped"

    def restart(self) -> None:
        self.stop()
        self.start()

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict[str, Any] | None = None,
        role: str = "generic",
    ) -> LLMResponse:
        if not self.is_running:
            raise RuntimeError("LLM backend is not running")
        if self.config.llm.history_messages != 0:
            raise RuntimeError("LLM request history must stay disabled for mechanical role calls")
        if not system:
            fallback = self.config.paths.agent_prompt_path or self.config.paths.system_prompt_path
            if fallback is not None:
                try:
                    system = fallback.read_text(encoding="utf-8")
                except FileNotFoundError:
                    system = ""
        defaults = {
            "max_new_tokens": self.config.llm.max_new_tokens,
            "temperature": self.config.llm.temperature,
            "top_p": self.config.llm.top_p,
            "top_k": self.config.llm.top_k,
            "repetition_penalty": self.config.llm.repetition_penalty,
            "no_repeat_ngram_size": self.config.llm.no_repeat_ngram_size,
        }
        defaults.update(override or {})
        req_id = uuid.uuid4().hex
        payload = {
            "req_id": req_id,
            "req": "generate",
            "role": role,
            "prompt": prompt,
            "system": system,
            "override": defaults,
        }
        q: Queue[dict[str, Any]] = Queue(maxsize=1)
        with self._rpc_lock:
            if req_id in self._early:
                response = self._early.pop(req_id)
                return LLMResponse(str(response.get("text", "")), response)
            self._rpc[req_id] = q
        with self._status_lock:
            self._last_role = role
            self._request_count += 1
            self._stage = f"generating:{role}"
        try:
            self._send(payload)
            try:
                response = q.get(timeout=self.config.llm.request_timeout_seconds)
            except Empty as exc:
                error = f"LLM request timed out: {req_id}"
                self._record_request(
                    req_id=req_id, role=role, prompt=prompt, system=system,
                    response_text="", error=error,
                )
                raise TimeoutError(error) from exc
            response_text = str(response.get("text", ""))
            if not bool(response.get("ok", False)):
                error = str(response.get("error") or "LLM generation failed")
                self._record_request(
                    req_id=req_id, role=role, prompt=prompt, system=system,
                    response_text=response_text, error=error,
                )
                raise RuntimeError(error)
            self._record_request(
                req_id=req_id, role=role, prompt=prompt, system=system,
                response_text=response_text,
            )
            return LLMResponse(response_text, response)
        finally:
            with self._rpc_lock:
                self._rpc.pop(req_id, None)
            with self._status_lock:
                self._stage = "ready" if self._ready.is_set() else "running"

    def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise RuntimeError("LLM backend is not running")
        line = json.dumps(payload, ensure_ascii=False)
        with self._stdin_lock:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()

    def _append_log(self, text: str) -> None:
        with self._status_lock:
            self._recent_log.append(text)

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._append_log(line)
                continue

            event = str(msg.get("event") or "")
            if event == "status":
                stage = str(msg.get("stage") or "status")
                detail = str(msg.get("detail") or "")
                with self._status_lock:
                    self._stage = stage
                    for key in ("cuda", "placement", "effective_4bit", "checkpoint_quantized"):
                        if key in msg:
                            self._ready_info[key] = msg[key]
                    self._recent_log.append(f"[{stage}] {detail}".rstrip())
                continue

            if msg.get("ready") is True:
                with self._status_lock:
                    self._ready_info = dict(msg)
                    self._stage = "ready"
                    self._recent_log.append(
                        f"[ready] loader={msg.get('loader_type')} ctx={msg.get('ctx_total')} "
                        f"transformers={msg.get('transformers_version')} 4bit={msg.get('effective_4bit')}"
                    )
                    placement_text = self._format_placement(msg.get("placement"))
                    if placement_text:
                        self._recent_log.append(f"[placement] {placement_text}")
                self._ready.set()
                continue

            req_id = str(msg.get("req_id") or "")
            terminal = bool(
                msg.get("final") is True
                or msg.get("done") is True
                or ("ok" in msg and "text" in msg)
            )
            if not req_id or not terminal:
                self._append_log(line)
                continue
            with self._rpc_lock:
                q = self._rpc.get(req_id)
                if q is not None:
                    q.put(msg)
                else:
                    self._early[req_id] = msg
