"""Headless Android/Chaquopy facade over RuntimeServices.

The GUI never imports this module. Kotlin talks only to the JSON functions here.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import shutil
import traceback

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.diagnostics.session_log import (
    begin_turn,
    emit,
    finish_turn,
    protocol_preview,
    start_session,
)
from ah.integration import IntegrationError
from ah.llm.android_npu_backend import AndroidNpuBackend, register_engine
from ah.perception import PerceptionParseError


_services: RuntimeServices | None = None
_root: Path | None = None
_session_id: str | None = None
_last_turn: dict[str, Any] | None = None
_chat_log: list[dict[str, Any]] = []
_phase: str = "idle"


def _sessions_dir(root: Path) -> Path:
    path = root / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_dir(root: Path, session_id: str) -> Path:
    path = _sessions_dir(root) / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path(root: Path, session_id: str) -> Path:
    return _session_dir(root, session_id) / "meta.json"


def _read_meta(root: Path, session_id: str) -> dict[str, Any]:
    path = _meta_path(root, session_id)
    if not path.is_file():
        return {"id": session_id, "title": "Новый чат", "preview": "", "updated_at": ""}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_meta(root: Path, session_id: str, **fields: Any) -> dict[str, Any]:
    meta = _read_meta(root, session_id)
    meta.update(fields)
    meta["id"] = session_id
    path = _meta_path(root, session_id)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _json_ready(value: Any) -> Any:
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            return None
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _failed_probe_rows(attempts: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in attempts or ():
        error = getattr(item, "error", None)
        if not error:
            continue
        rows.append(
            {
                "stage": getattr(item, "role", None) or getattr(item, "stage", ""),
                "error": str(error),
                "retry": getattr(item, "retry_index", 0),
                "raw_preview": protocol_preview(getattr(item, "raw_text", "")),
            }
        )
    return rows


def _perception_fail_snapshot(source_text: str | None = None) -> dict[str, Any]:
    perception = getattr(_services, "perception", None) if _services is not None else None
    if perception is None or not hasattr(perception, "diagnostics"):
        return {"probe_count": 0, "failed_probes": [], "parse_error": None}
    diags = perception.diagnostics()
    if not diags:
        return {"probe_count": 0, "failed_probes": [], "parse_error": None}
    last = diags[-1]
    last_source = getattr(last, "source_text", None)
    if source_text and last_source not in {None, source_text}:
        return {"probe_count": 0, "failed_probes": [], "parse_error": None, "source_text": last_source}
    failed = _failed_probe_rows(getattr(last, "attempts", ()))
    return {
        "probe_count": len(getattr(last, "attempts", ()) or ()),
        "failed_probes": failed[-8:],
        "parse_error": getattr(last, "final_error", None),
        "source_text": last_source,
    }


def _probe_line(probe: dict[str, Any]) -> str:
    preview = probe.get("raw_preview") if isinstance(probe.get("raw_preview"), dict) else {}
    raw = preview.get("repr") or preview.get("first_line") or probe.get("raw") or ""
    stage = probe.get("stage") or probe.get("role") or "probe"
    error = str(probe.get("error") or "").strip()
    retry = probe.get("retry")
    header = str(stage)
    if retry:
        header += f" · retry {retry}"
    parts = [header]
    if error:
        parts.append(f"  {error}")
    if raw:
        parts.append(f"  модель: {raw}")
    return "\n".join(parts)


def _trim_detail(text: str | None, *, limit: int = 1600) -> str:
    if not text:
        return ""
    stripped = str(text).strip()
    if "Traceback (most recent call last)" in stripped:
        stripped = "\n".join(stripped.splitlines()[-12:])
    if len(stripped) > limit:
        return stripped[:limit] + "…"
    return stripped


def _memory_summary() -> dict[str, Any]:
    if _services is None:
        return {"node_count": 0, "nodes": [], "snapshot_error": "ядро не запущено"}
    try:
        snap = _compact_snapshot(_services)
        nodes = [
            {
                "uid": node.get("uid"),
                "kind": node.get("kind"),
                "domain": node.get("domain"),
                "semantic": node.get("semantic") or "",
            }
            for node in snap.get("nodes") or []
        ]
        return {
            "node_count": snap.get("node_count", len(nodes)),
            "nodes": nodes[:24],
            "snapshot_error": snap.get("snapshot_error"),
        }
    except Exception as exc:
        return {"node_count": 0, "nodes": [], "snapshot_error": f"{type(exc).__name__}: {exc}"}


def _format_error_log(payload: dict[str, Any]) -> str:
    lines = ["не разобрал"]
    fail_kind = payload.get("fail_kind")
    error_type = payload.get("error_type")
    header = " · ".join(part for part in (fail_kind, error_type) if part)
    if header:
        lines.append(f"слой: {header}")
    parse_error = str(payload.get("parse_error") or "").strip()
    if parse_error:
        lines.append(parse_error[:800])
    probe = payload.get("last_failed_probe")
    if isinstance(probe, dict):
        lines.append("последний зонд:")
        lines.append(_probe_line(probe))
    failed = [item for item in (payload.get("failed_probes") or []) if isinstance(item, dict)]
    if len(failed) > 1:
        lines.append(f"упавшие зонды ({len(failed)} / {payload.get('probe_count') or len(failed)}):")
        for item in failed[-5:]:
            lines.append(_probe_line(item))
    unresolved = payload.get("unresolved_queries") or []
    if unresolved:
        lines.append(f"незакрытых целей: {len(unresolved)}")
        for item in unresolved[-3:]:
            if not isinstance(item, dict):
                continue
            diags = item.get("diagnostics") or []
            if diags:
                lines.append(f"  {diags[-1]}")
    detail = _trim_detail(payload.get("detail"))
    joined = "\n".join(lines)
    if detail and detail not in joined:
        if payload.get("fail_kind") == "exception" or not (parse_error or probe):
            lines.append(detail)
    memory = payload.get("memory_summary") or {}
    count = memory.get("node_count")
    if count is not None:
        names = [item.get("semantic") or item.get("uid") for item in memory.get("nodes") or []]
        shown = ", ".join(str(name) for name in names[:12] if name)
        extra = f" ({shown})" if shown else ""
        lines.append(f"память: {count} узлов{extra}")
        if memory.get("snapshot_error"):
            lines.append(f"снимок: {memory['snapshot_error']}")
        if int(count) <= 2:
            lines.append("семантика фразы в память не попала")
    return "\n".join(lines).strip()


def _finalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload["memory_summary"] = _memory_summary()
    if payload.get("status") == "error" or payload.get("fail_kind"):
        payload["error_log"] = _format_error_log(payload)
    else:
        payload["error_log"] = None
    return payload


def _query_snapshot(result: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in getattr(result, "queries", ()) or ():
        diagnostics = list(getattr(item, "diagnostics", ()) or ())
        outcome = getattr(item, "outcome", None)
        association_outcome = getattr(item, "association_outcome", None)
        rows.append(
            {
                "has_outcome": outcome is not None or association_outcome is not None,
                "diagnostics": diagnostics[-8:],
            }
        )
    unresolved = [item for item in rows if not item["has_outcome"] and item["diagnostics"]]
    return {"queries": rows[-8:], "unresolved_queries": unresolved[-8:]}


def _fail_payload(
    user_text: str,
    *,
    fail_kind: str,
    exc: BaseException | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    snapshot = _perception_fail_snapshot(user_text)
    last_failed = snapshot["failed_probes"][-1] if snapshot["failed_probes"] else None
    return {
        "user_text": user_text,
        "response_text": None,
        "response_error": "не разобрал",
        "status": "error",
        "assertion_uids": [],
        "query_ids": [],
        "clarification": None,
        "tick": None,
        "phase": "idle",
        "fail_kind": fail_kind,
        "error_type": type(exc).__name__ if exc is not None else None,
        "detail": detail or (str(exc) if exc is not None else None),
        "perception_diagnostics": [],
        "probe_count": snapshot["probe_count"],
        "failed_probes": snapshot["failed_probes"],
        "last_failed_probe": last_failed,
        "parse_error": snapshot.get("parse_error") or (str(exc) if exc is not None else None),
        "unresolved_queries": [],
    }


def _turn_payload(result: Any) -> dict[str, Any]:
    assertions: list[str] = []
    integration = getattr(result, "integration", None)
    if integration is not None:
        for item in getattr(integration, "assertions", ()) or ():
            ref = getattr(item, "ref", None)
            uid = getattr(ref, "uid", None)
            if uid:
                assertions.append(str(uid))
    clarification = None
    request = getattr(result, "clarification_request", None)
    if request is not None:
        clarification = {
            "mention": request.mention,
            "kind": request.kind,
            "options": [
                {"index": option.index, "label": option.label, "uid": option.ref.uid}
                for option in request.options
            ],
        }
    diagnostic = getattr(result, "agent_context_diagnostic", None)
    tick = None
    if diagnostic is not None:
        tick = getattr(diagnostic, "tick_index", None)
    error = getattr(result, "response_error", None)
    response = getattr(result, "response_text", None)
    status = "error" if error else "ok"
    fail_kind: str | None = None
    if error:
        fail_kind = "response_generation"
        display_error = "не разобрал"
    else:
        display_error = None
    if not str(response or "").strip() and not display_error:
        display_error = "не разобрал"
        status = "error"
        fail_kind = "empty_response"
        response = None
    perception = getattr(result, "perception", None)
    diagnostics = list(getattr(perception, "diagnostics", ()) or ())
    query_ids = [str(getattr(item, "local_id", "")) for item in getattr(perception, "queries", ()) or ()]
    snapshot = _perception_fail_snapshot(getattr(result, "user_text", None))
    queries = _query_snapshot(result)
    if fail_kind is None and queries["unresolved_queries"]:
        fail_kind = "unresolved_goal"
    last_failed = snapshot["failed_probes"][-1] if snapshot["failed_probes"] else None
    return {
        "user_text": result.user_text,
        "response_text": response if str(response or "").strip() else None,
        "response_error": display_error if display_error else None,
        "status": status,
        "assertion_uids": assertions,
        "query_ids": query_ids,
        "clarification": clarification,
        "tick": tick,
        "phase": "idle",
        "fail_kind": fail_kind,
        "error_type": None,
        "detail": str(error) if error else None,
        "perception_diagnostics": diagnostics[-12:],
        "probe_count": snapshot["probe_count"],
        "failed_probes": snapshot["failed_probes"],
        "last_failed_probe": last_failed,
        "parse_error": snapshot.get("parse_error"),
        "unresolved_queries": queries["unresolved_queries"],
    }


def _store_node_fallback(services: RuntimeServices) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    store = services.core.store
    workspace_uids = set()
    if services.ignition is not None:
        workspace_uids = {ref.uid for ref in services.ignition.workspace_refs()}
    for uid in sorted(store.all_uids()):
        kind = store.kind_of(uid)
        if getattr(kind, "value", kind) == "L":
            continue
        domain = store.domain_of(uid)
        runtime = store.runtime_state(uid)
        semantic = ""
        try:
            semantic = services.graph_inspector._semantic(uid)
        except Exception:
            semantic = uid
        nodes.append(
            {
                "uid": uid,
                "kind": getattr(kind, "value", kind),
                "domain": getattr(domain, "value", domain),
                "semantic": semantic or uid,
                "excitation": getattr(runtime, "excitation", None),
                "output": getattr(runtime, "output", None),
                "decay_age": getattr(runtime, "decay_age", None),
                "lifecycle_state": None,
                "in_workspace": uid in workspace_uids,
            }
        )
    return nodes


def _compact_snapshot(services: RuntimeServices) -> dict[str, Any]:
    snapshot_error = None
    try:
        raw = asdict(services.graph_inspector.snapshot())
        workspace_uids = set(raw.get("workspace_uids") or [])
        semantics = raw.get("workspace_semantics") or {}
        nodes = []
        for node in raw.get("nodes") or []:
            uid = node.get("uid")
            in_workspace = bool(node.get("in_workspace") or uid in workspace_uids)
            semantic = semantics.get(uid, node.get("semantic") or "")
            nodes.append(
                {
                    "uid": uid,
                    "kind": node.get("kind"),
                    "domain": node.get("domain"),
                    "semantic": semantic,
                    "excitation": node.get("excitation"),
                    "output": node.get("output"),
                    "decay_age": node.get("decay_age"),
                    "lifecycle_state": node.get("lifecycle_state"),
                    "in_workspace": in_workspace,
                }
            )
        links = []
        visible = {node["uid"] for node in nodes}
        for link in raw.get("links") or []:
            if link.get("source_uid") in visible and link.get("target_uid") in visible:
                links.append(link)
        for index, edge in enumerate(raw.get("structural_edges") or []):
            src = edge.get("source_uid")
            tgt = edge.get("target_uid")
            if src in visible and tgt in visible:
                links.append(
                    {
                        "uid": f"S{index}:{src}:{tgt}",
                        "relation_id": edge.get("relation_id") or edge.get("edge_kind") or "STRUCT",
                        "source_uid": src,
                        "target_uid": tgt,
                        "weight": 0.45 if src in workspace_uids and tgt in workspace_uids else 0.12,
                    }
                )
        tick = raw.get("tick", 0)
        threshold = services.config.workspace.threshold
    except Exception as exc:
        snapshot_error = f"{type(exc).__name__}: {exc}"
        emit("android_snapshot_failed", error=str(exc), error_type=type(exc).__name__)
        nodes = _store_node_fallback(services)
        links = []
        tick = getattr(services.ignition, "tick_index", 0) if services.ignition is not None else 0
        threshold = services.config.workspace.threshold
    nodes.sort(
        key=lambda item: (
            not item["in_workspace"],
            -(item["excitation"] if isinstance(item.get("excitation"), (int, float)) else float("-inf")),
            str(item.get("uid") or ""),
        )
    )
    result = {
        "tick": tick,
        "threshold": threshold,
        "workspace_count": sum(1 for node in nodes if node["in_workspace"]),
        "node_count": len(nodes),
        "nodes": nodes,
        "links": links,
        "last_turn": _last_turn,
        "phase": _phase,
        "session_id": _session_id,
        "snapshot_error": snapshot_error,
    }
    return _json_ready(result)


def _rewrite_config(root: Path, session_id: str) -> Path:
    source = root / "config" / "android.toml"
    if not source.is_file():
        raise FileNotFoundError(f"android config not found: {source}")
    session = _session_dir(root, session_id)
    data_dir = session / "data"
    logs_dir = session / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    replacements = {
        'project_dir = ".."': f'project_dir = "{root.as_posix()}"',
        'perception_prompt_dir = "../prompts/perception"': f'perception_prompt_dir = "{(root / "prompts" / "perception").as_posix()}"',
        'agent_prompt_path = "../prompts/agent.txt"': f'agent_prompt_path = "{(root / "prompts" / "agent.txt").as_posix()}"',
        'system_prompt_path = "../prompts/agent.txt"': f'system_prompt_path = "{(root / "prompts" / "agent.txt").as_posix()}"',
        'perception_prompt_path = "../prompts/perception.txt"': f'perception_prompt_path = "{(root / "prompts" / "perception.txt").as_posix()}"',
        'data_dir = "../data"': f'data_dir = "{data_dir.as_posix()}"',
        'persistence_file = "../data/ah_android_memory.json"': f'persistence_file = "{(data_dir / "ah_memory.json").as_posix()}"',
        'logs_dir = "../logs"': f'logs_dir = "{logs_dir.as_posix()}"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    out = session / "runtime.toml"
    out.write_text(text, encoding="utf-8")
    return out


def _stop_locked() -> None:
    global _services, _phase
    if _services is not None:
        try:
            _services.stop(save=True)
        except Exception:
            pass
        _services = None
    _phase = "idle"


def start(root_dir: str, session_id: str | None = None) -> str:
    """Boot RuntimeServices for a session. Returns the active session id."""

    global _services, _root, _session_id, _last_turn, _chat_log, _phase
    root = Path(root_dir).expanduser().resolve()
    _stop_locked()
    _root = root
    _last_turn = None
    _chat_log = []
    _phase = "starting"
    if session_id:
        sid = session_id
    else:
        existing = list_sessions(str(root))
        sid = existing[0]["id"] if existing else new_session(str(root))
    config_path = _rewrite_config(root, sid)
    logs_dir = _session_dir(root, sid) / "logs"
    start_session(logs_dir, extra={"platform": "android", "session_id": sid})
    services = RuntimeServices.build(load_config(config_path))
    if isinstance(services.llm, AndroidNpuBackend):
        # Engine may already be registered by Kotlin before start().
        pass
    services.start()
    _services = services
    _session_id = sid
    _phase = "idle"
    chat_path = _session_dir(root, sid) / "chat.json"
    if chat_path.is_file():
        _chat_log = json.loads(chat_path.read_text(encoding="utf-8"))
    _write_meta(root, sid, updated_at=datetime.now(timezone.utc).isoformat())
    return sid


def stop() -> None:
    _stop_locked()


def bind_engine(engine: Any) -> None:
    register_engine(engine)


def new_session(root_dir: str | None = None) -> str:
    root = Path(root_dir).expanduser().resolve() if root_dir else _root
    if root is None:
        raise RuntimeError("android bridge is not started")
    session_id = uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    _write_meta(root, session_id, title="Новый чат", preview="", updated_at=now)
    (_session_dir(root, session_id) / "chat.json").write_text("[]", encoding="utf-8")
    return session_id


def list_sessions(root_dir: str | None = None) -> list[dict[str, Any]]:
    root = Path(root_dir).expanduser().resolve() if root_dir else _root
    if root is None:
        return []
    items = []
    for path in _sessions_dir(root).iterdir():
        if path.is_dir():
            items.append(_read_meta(root, path.name))
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items


def delete_session(session_id: str) -> None:
    global _session_id
    if _root is None:
        raise RuntimeError("android bridge is not started")
    if _session_id == session_id:
        _stop_locked()
        _session_id = None
    target = _sessions_dir(_root) / session_id
    if target.is_dir():
        shutil.rmtree(target)


def open_session(session_id: str) -> str:
    if _root is None:
        raise RuntimeError("android bridge is not started")
    return start(str(_root), session_id)


def messages() -> list[dict[str, Any]]:
    return list(_chat_log)


def snapshot() -> dict[str, Any]:
    if _services is None:
        return {
            "tick": 0,
            "threshold": 0.35,
            "workspace_count": 0,
            "node_count": 0,
            "nodes": [],
            "links": [],
            "last_turn": _last_turn,
            "phase": _phase,
            "session_id": _session_id,
            "snapshot_error": None,
        }
    try:
        return _compact_snapshot(_services)
    except Exception as exc:
        return {
            "tick": 0,
            "threshold": 0.35,
            "workspace_count": 0,
            "node_count": 0,
            "nodes": [],
            "links": [],
            "last_turn": _last_turn,
            "phase": _phase,
            "session_id": _session_id,
            "snapshot_error": f"{type(exc).__name__}: {exc}",
        }


def snapshot_json() -> str:
    return json.dumps(_json_ready(snapshot()), ensure_ascii=False, default=str)


def list_sessions_json(root_dir: str | None = None) -> str:
    return json.dumps(list_sessions(root_dir), ensure_ascii=False)


def messages_json() -> str:
    return json.dumps(messages(), ensure_ascii=False)


def send(text: str) -> str:
    """Run one user turn and return the JSON payload for the Android UI."""

    global _last_turn, _phase, _chat_log
    if _services is None or _root is None or _session_id is None:
        raise RuntimeError("android bridge is not started")
    user_text = str(text or "").strip()
    if not user_text:
        raise ValueError("empty message")
    _phase = "формализация…"
    _chat_log.append({"role": "user", "text": user_text, "kind": "chat"})
    begin_turn(user_text)
    try:
        _phase = "вывод…"
        orchestrator = _services.create_orchestrator()
        _phase = "ответ…"
        result = orchestrator.handle_user_text(user_text)
        payload = _turn_payload(result)
    except PerceptionParseError as exc:
        payload = _fail_payload(
            user_text,
            fail_kind="perception",
            exc=exc,
            detail=traceback.format_exc(),
        )
        emit(
            "android_turn_failed",
            fail_kind="perception",
            error=str(exc),
            error_type=type(exc).__name__,
            user_text=user_text,
            last_failed_probe=payload.get("last_failed_probe"),
            failed_probes=payload.get("failed_probes"),
        )
    except IntegrationError as exc:
        payload = _fail_payload(
            user_text,
            fail_kind="integration",
            exc=exc,
            detail=traceback.format_exc(),
        )
        emit(
            "android_turn_failed",
            fail_kind="integration",
            error=str(exc),
            error_type=type(exc).__name__,
            user_text=user_text,
        )
    except Exception as exc:
        payload = _fail_payload(
            user_text,
            fail_kind="exception",
            exc=exc,
            detail=traceback.format_exc(),
        )
        emit(
            "android_turn_failed",
            fail_kind="exception",
            error=str(exc),
            error_type=type(exc).__name__,
            user_text=user_text,
        )
    payload = _finalize_payload(payload)
    emit(
        "android_turn",
        user_text=user_text,
        status=payload.get("status"),
        fail_kind=payload.get("fail_kind"),
        error_type=payload.get("error_type"),
        response_text=payload.get("response_text"),
        response_error=payload.get("response_error"),
        error_log=payload.get("error_log"),
        assertion_uids=payload.get("assertion_uids"),
        query_ids=payload.get("query_ids"),
        detail=payload.get("detail"),
        parse_error=payload.get("parse_error"),
        probe_count=payload.get("probe_count"),
        last_failed_probe=payload.get("last_failed_probe"),
        failed_probes=payload.get("failed_probes"),
        unresolved_queries=payload.get("unresolved_queries"),
        memory_summary=payload.get("memory_summary"),
    )
    finish_turn(
        user_text=user_text,
        status=payload.get("status"),
        fail_kind=payload.get("fail_kind"),
        error_type=payload.get("error_type"),
        error=payload.get("parse_error") or payload.get("detail") or payload.get("response_error"),
        probe_count=payload.get("probe_count"),
        last_failed_probe=payload.get("last_failed_probe"),
        assertion_count=len(payload.get("assertion_uids") or []),
        query_ids=payload.get("query_ids"),
        error_log=payload.get("error_log"),
    )
    _last_turn = payload
    _phase = "idle"
    if payload.get("response_text"):
        _chat_log.append({"role": "assistant", "text": payload["response_text"], "kind": "chat"})
    error_log = payload.get("error_log")
    if error_log:
        _chat_log.append({"role": "system", "text": error_log, "kind": "error"})
    elif payload.get("response_error"):
        _chat_log.append({"role": "system", "text": payload["response_error"], "kind": "error"})
    session = _session_dir(_root, _session_id)
    logs = session / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    ready = _json_ready(payload)
    (session / "chat.json").write_text(json.dumps(_chat_log, ensure_ascii=False, indent=2), encoding="utf-8")
    (logs / "last-turn.json").write_text(
        json.dumps(ready, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    title = user_text if _read_meta(_root, _session_id).get("title") in {"", "Новый чат"} else _read_meta(_root, _session_id)["title"]
    preview = payload.get("response_text") or payload.get("response_error") or ""
    _write_meta(
        _root,
        _session_id,
        title=title[:80],
        preview=str(preview)[:120],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return json.dumps(ready, ensure_ascii=False, default=str)


def _jsonl_tail(path: Path, *, kinds: tuple[str, ...], limit: int, chars: int) -> str:
    if not path.is_file():
        return ""
    kept: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("kind") in kinds:
            kept.append(line)
    return "\n".join(kept[-limit:])[-chars:]


def debug_log() -> str:
    """Return the latest Android runtime log so it can be copied off the device."""

    chunks: list[str] = []
    if _last_turn and _last_turn.get("error_log"):
        chunks.append("## chat-error")
        chunks.append(str(_last_turn["error_log"]))
    if _root is not None and _session_id is not None:
        logs = _session_dir(_root, _session_id) / "logs"
        turns = logs / "turns.jsonl"
        if turns.is_file():
            text = turns.read_text(encoding="utf-8")
            chunks.append("## turns.jsonl")
            chunks.append(text[-20000:] if text else "(empty)")
        latest_jsonl = logs / "latest.jsonl"
        summaries = _jsonl_tail(
            latest_jsonl,
            kinds=(
                "pipeline_parse_summary",
                "pipeline_perception_failed",
                "pipeline_integration_failed",
                "pipeline_unresolved_goal",
                "android_turn_failed",
                "turn_end",
            ),
            limit=40,
            chars=16000,
        )
        if summaries:
            chunks.append("## parse-summaries")
            chunks.append(summaries)
        probes = _jsonl_tail(
            latest_jsonl,
            kinds=("pipeline_probe",),
            limit=40,
            chars=16000,
        )
        if probes:
            chunks.append("## probes")
            chunks.append(probes)
    if _last_turn is not None:
        chunks.append("## last-turn")
        chunks.append(json.dumps(_last_turn, ensure_ascii=False, indent=2))
    if _root is not None and _session_id is not None:
        logs = _session_dir(_root, _session_id) / "logs"
        for name in ("last-turn.json", "latest.log"):
            path = logs / name
            if path.is_file():
                text = path.read_text(encoding="utf-8")[-12000:]
                chunks.append(f"## {name}")
                chunks.append(text)
    if not chunks:
        return "no android logs yet"
    return "\n\n".join(chunks)
