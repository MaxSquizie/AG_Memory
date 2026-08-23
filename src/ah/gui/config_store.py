from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import tempfile
import tomllib
from typing import Any, Iterable

from ah.config import AppConfig, load_config


class ApplyMode(str, Enum):
    LIVE = "LIVE"
    NEXT_TURN = "NEXT_TURN"
    RESTART_LLM = "RESTART_LLM"
    RESTART_RUNTIME = "RESTART_RUNTIME"


@dataclass(frozen=True, slots=True)
class ConfigEntry:
    path: str
    value: Any
    value_type: type
    apply_mode: ApplyMode


def _classify(path: str) -> ApplyMode:
    # Model loading/runtime shape is fixed inside the subprocess and therefore
    # requires an LLM restart. Pure generation parameters are read by the parent
    # for every request and are hot-safe.
    if path in {
        "paths.llm_model_dir",
        "paths.tokenizer_dir",
        "paths.adapter_dir",
        "llm.backend",
        "llm.ollama_base_url",
        "llm.ollama_model",
        "llm.lmstudio_base_url",
        "llm.lmstudio_model",
        "llm.lmstudio_api_key",
        "llm.loader_type",
        "llm.device_map",
        "llm.dtype",
        "llm.local_files_only",
        "llm.trust_remote_code",
        "llm.use_4bit",
        "llm.ctx_total",
        "llm.enable_thinking",
        "llm.strip_thinking",
        "llm.engine_script",
        "llm.enabled",
        "llm.history_messages",
    }:
        return ApplyMode.RESTART_LLM
    if path.startswith("paths.") and path not in {
        "paths.system_prompt_path",
        "paths.agent_prompt_path",
        "paths.perception_prompt_path",
        "paths.perception_prompt_dir",
    }:
        return ApplyMode.RESTART_RUNTIME
    if path.startswith("persistence.") or path.startswith("identity."):
        return ApplyMode.RESTART_RUNTIME
    if path.startswith("orchestrator."):
        return ApplyMode.NEXT_TURN
    return ApplyMode.LIVE


def _flatten(data: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten(value, path)
        else:
            yield path, value


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        # repr keeps enough precision and emits TOML-compatible decimal/exponent.
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def _dump_table(lines: list[str], table: dict[str, Any], prefix: str) -> None:
    scalar_items = [(k, v) for k, v in table.items() if not isinstance(v, dict)]
    child_items = [(k, v) for k, v in table.items() if isinstance(v, dict)]
    if prefix:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{prefix}]")
    for key, value in scalar_items:
        lines.append(f"{key} = {_toml_value(value)}")
    for key, child in child_items:
        child_prefix = f"{prefix}.{key}" if prefix else key
        _dump_table(lines, child, child_prefix)


def dumps_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    top_scalars = [(k, v) for k, v in data.items() if not isinstance(v, dict)]
    top_tables = [(k, v) for k, v in data.items() if isinstance(v, dict)]
    for key, value in top_scalars:
        lines.append(f"{key} = {_toml_value(value)}")
    for key, table in top_tables:
        _dump_table(lines, table, key)
    return "\n".join(lines).rstrip() + "\n"


def parse_typed(text: str, current: Any) -> Any:
    raw = text.strip()
    if isinstance(current, bool):
        lowered = raw.casefold()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError("Expected boolean")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    if isinstance(current, list):
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("Expected JSON array")
        return parsed
    return text


class ConfigDocument:
    """Editable TOML document with validation through the canonical config loader.

    GUI changes are staged in memory, validated by `load_config`, then atomically
    written. Comments are not preserved; the GUI itself provides the operational
    metadata (type + apply mode) and the generated TOML stays deterministic.
    """

    def __init__(self, source_path: str | Path) -> None:
        self.source_path = Path(source_path).expanduser().resolve()
        self._data = self._read()
        self._saved_data = deepcopy(self._data)

    def _read(self) -> dict[str, Any]:
        with self.source_path.open("rb") as fh:
            raw = tomllib.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("Config root must be a TOML table")
        return raw

    @property
    def dirty(self) -> bool:
        return self._data != self._saved_data

    def reload(self) -> None:
        self._data = self._read()
        self._saved_data = deepcopy(self._data)

    def entries(self) -> tuple[ConfigEntry, ...]:
        return tuple(
            ConfigEntry(path, value, type(value), _classify(path))
            for path, value in _flatten(self._data)
        )

    def get(self, path: str) -> Any:
        current: Any = self._data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise KeyError(path)
            current = current[part]
        return current

    def set(self, path: str, value: Any) -> None:
        _set_path(self._data, path, value)

    def set_from_text(self, path: str, text: str) -> Any:
        value = parse_typed(text, self.get(path))
        self.set(path, value)
        return value

    def validate(self) -> AppConfig:
        text = dumps_toml(self._data)
        # Put the temporary file beside the real config so relative paths resolve
        # exactly as they will after save.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.source_path.stem}.",
            suffix=self.source_path.suffix,
            dir=self.source_path.parent,
        )
        tmp = Path(tmp_name)
        try:
            import os
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            return load_config(tmp)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def save(self) -> AppConfig:
        validated = self.validate()
        text = dumps_toml(self._data)
        tmp = self.source_path.with_suffix(self.source_path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(self.source_path)
        self._saved_data = deepcopy(self._data)
        # Reload from the actual path so AppConfig.source_path is canonical.
        return load_config(self.source_path)

    def changed_paths(self) -> tuple[str, ...]:
        before = dict(_flatten(self._saved_data))
        after = dict(_flatten(self._data))
        keys = set(before) | set(after)
        return tuple(sorted(k for k in keys if before.get(k) != after.get(k)))

    @staticmethod
    def apply_mode(path: str) -> ApplyMode:
        return _classify(path)
