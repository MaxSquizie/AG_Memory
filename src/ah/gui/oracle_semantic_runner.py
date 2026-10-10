"""Pure V7 GUI runner helpers: commands, discovery and artifact reports."""
from __future__ import annotations

import gzip
import http.client
import json
from pathlib import Path
from urllib.parse import urlparse


def select_model_required_case_ids(corpus_dir: Path) -> list[str]:
    """Return case IDs (file order) whose steps contain a raw-text ``formalize``.

    Deterministic and provider-free; used to report the exact selected set in the
    run config even though the subprocess selects via ``--tier pipeline``.
    """
    cases_file = Path(corpus_dir) / "cases.jsonl"
    ids: list[str] = []
    if not cases_file.is_file():
        return ids
    for line in cases_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError:
            continue
        steps = case.get("steps") or []
        if any(isinstance(s, dict) and s.get("action") == "formalize" for s in steps):
            ids.append(case["case_id"])
    return ids


def detect_lmstudio_models(base_url: str, api_key: str | None = None, timeout: float = 10.0) -> list[str]:
    """GET ``/v1/models`` on an OpenAI-compatible server; return model IDs.

    Uses raw ``http.client`` (LM Studio's proxy rejects urllib with HTTP 502 for
    the identical body). Returns [] on any transport error so callers can fail
    closed instead of guessing a model name.
    """
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme not in {"http", "https"} or not host:
        return []
    connection = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection(host, port, timeout=timeout)
    try:
        conn.putrequest("GET", parsed.path.rstrip("/") + "/models")
        conn.putheader("Accept", "application/json")
        if api_key:
            conn.putheader("Authorization", f"Bearer {api_key}")
        conn.endheaders()
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            return []
        data = json.loads(raw)
    except Exception:
        return []
    finally:
        conn.close()
    models = (data.get("data") or []) if isinstance(data, dict) else []
    out: list[str] = []
    for item in models:
        if isinstance(item, dict):
            mid = item.get("id")
            if mid:
                out.append(str(mid))
    return out


def build_oracle_command(
    repo_root: Path,
    base_url: str,
    model: str,
    out_dir: Path,
    *,
    timeout: float = 300.0,
    max_tokens: int = 4096,
    provider: str = "lmstudio",
    tiers: tuple[str, ...] = ("pipeline",),
) -> list[str]:
    """argv after the interpreter; the GUI consumes flushed progress events."""
    if provider not in {"disabled", "lmstudio", "ollama", "openai"}:
        raise ValueError("unsupported GUI oracle provider")
    if provider != "disabled" and not model.strip():
        raise ValueError("a loaded model must be selected")
    corpus = repo_root / "data" / "formalizer_v7_oracle"
    runner = repo_root / "tools" / "run_formalizer_v7_oracle.py"
    argv = [
        str(runner),
        "--corpus", str(corpus),
        "--provider", provider,
        "--base-url", base_url,
        "--model", model,
        "--timeout", str(timeout),
        "--max-tokens", str(max_tokens),
        "--progress-jsonl",
        "--out", str(out_dir),
    ]
    for tier in tiers:
        argv += ["--tier", tier]
    return argv


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_actual(out_dir: Path, warnings: list | None = None):
    gz = out_dir / "actual.jsonl.gz"
    plain = out_dir / "actual.jsonl"
    # The plain stream remains authoritative until compression has finished.
    # Stop/crash during archive.write_bytes can leave a partial .gz beside it.
    path = plain if plain.is_file() else gz
    if not path.is_file():
        return
    opener = path.open if path == plain else lambda **kw: gzip.open(path, **kw)
    try:
        with opener(mode="rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        yield row
                except json.JSONDecodeError:
                    if warnings is not None:
                        warnings.append(f"Incomplete or invalid actual record in {path.name}")
    except (OSError, EOFError, UnicodeError) as exc:
        if warnings is not None:
            warnings.append(f"Cannot read {path.name}: {exc}")


def _provider_health(out_dir: Path) -> dict:
    """Aggregate per-case provider WAL (journal.log prov_call records)."""
    received = failed = 0
    errors: dict[str, int] = {}
    times: list[float] = []
    cases_dir = out_dir / "cases"
    if not cases_dir.is_dir():
        return {"received": 0, "failed": 0, "errors": {}, "avg_ms": None, "max_ms": None}
    for journal in sorted(cases_dir.glob("*/journal.log")):
        try:
            lines = journal.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        calls = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = rec.get("payload") or {}
            if payload.get("kind") != "prov_call":
                continue
            calls[payload.get("id", (payload.get("run_id"), payload.get("ordinal"), payload.get("attempt")))] = payload
        for payload in calls.values():
            state = payload.get("state")
            if state == "RECEIVED":
                received += 1
            elif state in ("FAILED", "ERROR"):
                failed += 1
                key = str(payload.get("error") or f"provider {state}")[:160]
                errors[key] = errors.get(key, 0) + 1
            ms = payload.get("response_time_ms")
            if isinstance(ms, (int, float)):
                times.append(float(ms))
    return {
        "received": received,
        "failed": failed,
        "errors": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
        "avg_ms": (sum(times) / len(times)) if times else None,
        "max_ms": max(times) if times else None,
    }


def _progress_artifacts(out_dir: Path, warnings: list[str]) -> dict:
    """Reduce a partial progress stream without retaining prompts or responses.

    A flushed case_finished is the same serialized comparison used by the final
    comparator. Absence of the final files does not erase that recorded result.
    Duplicate events are ignored; the latest result for each case wins.
    """
    path = out_dir / "progress.jsonl"
    result = {"started": {}, "finished": {}, "cases": {}, "started_cases": set(),
              "requests": {}, "request_counts": {}, "elapsed_seconds": None,
              "received_provider_calls": None, "endpoint": None}
    if not path.is_file():
        return result
    last_seq = -1
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    warnings.append("Incomplete or invalid progress record in progress.jsonl")
                    continue
                if not isinstance(event, dict) or event.get("schema_version") != "v7-oracle-progress-1":
                    continue
                seq = event.get("seq")
                if not isinstance(seq, int) or seq <= last_seq:
                    continue
                last_seq = seq
                kind, cid = event.get("event"), event.get("case_id")
                if kind == "run_started":
                    result["started"] = event
                elif kind == "run_finished":
                    result["finished"] = event
                elif kind == "case_started" and isinstance(cid, str):
                    result["started_cases"].add(cid)
                elif kind == "case_finished" and isinstance(cid, str):
                    result["started_cases"].add(cid)
                    # Keep only diagnostic/comparison metadata, not raw replies.
                    result["cases"][cid] = {key: event.get(key) for key in (
                        "status", "errors", "blockers", "runtime_error",
                        "first_observed_text", "native_diagnostic_text")}
                    native = event.get("runtime_diagnostics") or {}
                    result["cases"][cid]["diag_codes"] = sorted({str(d["code"])
                        for d in native.get("native_diagnostics", [])
                        if isinstance(d, dict) and d.get("code")}) if isinstance(native, dict) else []
                elif kind in {"request_started", "request_finished"}:
                    request_id = event.get("request_id")
                    if isinstance(request_id, str):
                        result["requests"][request_id] = {
                            "event": kind, "status": event.get("status"), "error": event.get("error"),
                            "elapsed_seconds": event.get("request_elapsed_seconds"),
                        }
                    if event.get("endpoint"):
                        result["endpoint"] = event["endpoint"]
                for key in ("requests_started", "requests_finished", "requests_failed"):
                    if isinstance(event.get(key), int):
                        result["request_counts"][key] = event[key]
                if isinstance(event.get("received_provider_calls"), int):
                    result["received_provider_calls"] = event["received_provider_calls"]
                # The emitter preserves HTTP time in request_elapsed_seconds;
                # elapsed_seconds is its run clock, including the active call.
                if isinstance(event.get("elapsed_seconds"), (int, float)):
                    result["elapsed_seconds"] = event["elapsed_seconds"]
    except (OSError, UnicodeError) as exc:
        warnings.append(f"Cannot read progress.jsonl: {exc}")
    return result


def _progress_provider_health(progress: dict) -> dict:
    received = failed = 0
    errors: dict[str, int] = {}
    times: list[float] = []
    for request in progress["requests"].values():
        if request["event"] != "request_finished":
            continue
        if request["status"] == "SUCCESS":
            received += 1
        elif request["status"] in {"ERROR", "FAILED"}:
            failed += 1
            error = str(request.get("error") or f"provider {request['status']}")[:160]
            errors[error] = errors.get(error, 0) + 1
        duration = request.get("elapsed_seconds")
        if isinstance(duration, (int, float)):
            times.append(duration * 1000)
    return {"received": received, "failed": failed, "errors": errors,
            "avg_ms": sum(times) / len(times) if times else None,
            "max_ms": max(times) if times else None}


def parse_run_stats(out_dir: Path) -> dict:
    """Aggregate every run artifact into one detailed diagnostics structure."""
    out_dir = Path(out_dir)
    summary = _read_json(out_dir / "summary.json") or {}
    issues = _read_json(out_dir / "issues.json") or {}
    comparison = _read_json(out_dir / "comparison.json") or {}
    run_config = _read_json(out_dir / "run_config.json") or {}
    provenance = _read_json(out_dir / "provenance.json") or {}

    artifact_warnings: list[str] = []
    progress = _progress_artifacts(out_dir, artifact_warnings)
    started, finished = progress["started"], progress["finished"]
    # The final files have priority; incomplete runs retain flushed comparison
    # results from case_finished, never a guessed failure from a partial IR.
    per_case_status = {cid: {
        "status": res.get("status"),
        "blockers": [b.get("reason") for b in res.get("blockers") or [] if isinstance(b, dict)],
        "errors": res.get("errors") or [],
        "source": "progress.jsonl",
        "first_observed_text": res.get("first_observed_text"),
        "native_diagnostic_text": res.get("native_diagnostic_text"),
    } for cid, res in progress["cases"].items()}

    # Per-case diagnostics codes from actual records and recorded native events.
    per_case_diag: dict[str, list[str]] = {}
    observed_cases: set[str] = set()
    runtime_exceptions = {cid for cid, res in progress["cases"].items() if res.get("runtime_error")}
    for rec in _iter_actual(out_dir, artifact_warnings):
        cid = rec.get("case_id")
        if not cid:
            continue
        observed_cases.add(cid)
        if rec.get("runtime_error"):
            runtime_exceptions.add(cid)
        codes = sorted({str(code) for checkpoint in rec.get("checkpoints") or []
                        for code in ((checkpoint.get("actual") or {}).get("diagnostics") or {}).get("codes", [])})
        per_case_diag[cid] = list(codes)
    for cid, res in progress["cases"].items():
        per_case_diag[cid] = sorted(set(per_case_diag.get(cid, [])) | set(res["diag_codes"]))
    diag_counts: dict[str, int] = {}
    for codes in per_case_diag.values():
        for code in codes:
            diag_counts[code] = diag_counts.get(code, 0) + 1

    # Per-case status/blockers from the comparison results.
    for res in (comparison.get("results") or []):
        cid = res.get("case_id")
        if not cid:
            continue
        blockers = [b.get("reason") for b in (res.get("blockers") or []) if isinstance(b, dict)]
        per_case_status[cid] = {
            "status": res.get("status"),
            "blockers": blockers,
            "errors": res.get("errors") or [],
            "source": "comparison.json",
        }

    # Non-passing cases merged with diagnostics + provider state.
    non_passing: list[dict] = []
    seen_cases = observed_cases | set(per_case_status) | progress["started_cases"]
    for cid in sorted(seen_cases):
        info = per_case_status.get(cid, {})
        status = info.get("status") or "INCOMPLETE"
        if status == "PASS":
            continue
        non_passing.append({
            "case_id": cid,
            "status": status,
            "blockers": info.get("blockers", []),
            "diag_codes": per_case_diag.get(cid, []),
            "source": info.get("source", "no completed comparison recorded"),
        })

    completed = {cid: res for cid, res in per_case_status.items() if res.get("status") in {"PASS", "FAIL", "BLOCKED"}}
    expected = comparison.get("expected_cases", started.get("total"))
    if expected is None and isinstance(run_config.get("selected_case_ids"), list):
        expected = len(run_config["selected_case_ids"])
    unfinished_cases = sorted(seen_cases - set(completed))
    failed_detail = issues.get("cases") or [{"case_id": cid, "errors": res["errors"],
        "attribution": "NOT_RECORDED", "source": res["source"],
        "first_observed_text": res.get("first_observed_text"),
        "native_diagnostic_text": res.get("native_diagnostic_text")}
        for cid, res in completed.items() if res["status"] == "FAIL"]
    provider_config = run_config.get("provider_config") or started.get("provider_config") or {
        key: started[key] for key in ("provider", "model") if key in started}
    selected = run_config.get("selected_case_ids", started.get("selected_case_ids", []))
    selected_ids = [cid for cid in selected if isinstance(cid, str)]
    has_wal = any((out_dir / "cases").glob("*/journal.log"))
    health = _provider_health(out_dir) if has_wal else _progress_provider_health(progress)
    effective_summary = summary or finished.get("summary") or {}
    blocker_counts = effective_summary.get("blocker_counts", {})
    if not blocker_counts:
        for res in completed.values():
            for reason in res["blockers"]:
                if isinstance(reason, str):
                    blocker_counts[reason] = blocker_counts.get(reason, 0) + 1

    return {
        "out_dir": str(out_dir),
        "provider_config": provider_config or None,
        "provider_endpoint": progress["endpoint"],
        "selected_case_ids": selected_ids,
        "selected_case_ids_complete": isinstance(expected, int) and len(selected_ids) == expected,
        "status": effective_summary.get("status") or finished.get("status") or "INCOMPLETE",
        "comparison_source": "comparison.json" if comparison else "progress.jsonl" if completed else "NOT_RECORDED",
        "run_finished_recorded": bool(finished),
        "unfinished_cases": unfinished_cases,
        "case_results": [{"case_id": cid, "status": res["status"], "source": res["source"]}
                         for cid, res in sorted(completed.items())],
        "totals": {
            "passed": effective_summary.get("passed_cases", sum(res["status"] == "PASS" for res in completed.values())),
            "failed": effective_summary.get("failed_cases", sum(res["status"] == "FAIL" for res in completed.values())),
            "blocked": effective_summary.get("blocked_cases", sum(res["status"] == "BLOCKED" for res in completed.values())),
            "expected": expected,
            "observed": comparison.get("observed_cases", len(observed_cases | set(completed))),
            "completed": len(completed),
            "incomplete_observed": len(unfinished_cases),
            "not_started": max(0, expected - len(seen_cases)) if isinstance(expected, int) else None,
            "runtime_exceptions": effective_summary.get("runtime_exceptions", len(runtime_exceptions)),
        },
        "request_counts": progress["request_counts"],
        "blocker_counts": blocker_counts,
        "failure_attribution_counts": effective_summary.get("failure_attribution_counts", {}),
        "provenance": {
            "model_live_execution": provenance.get("model_live_execution", provider_config.get("provider") in {"lmstudio", "ollama", "openai"} and health["received"] > 0),
            "received_provider_calls": provenance.get("received_provider_calls", progress["received_provider_calls"] if progress["received_provider_calls"] is not None else health["received"]),
            "elapsed_seconds": provenance.get("elapsed_seconds", progress["elapsed_seconds"]),
            "source_unchanged": provenance.get("source_unchanged"),
        },
        "provider_health": health,
        "provider_health_source": "provider WAL" if has_wal else "progress.jsonl",
        "diagnostic_code_counts": dict(sorted(diag_counts.items(), key=lambda kv: -kv[1])),
        "non_passing_cases": non_passing,
        "failed_case_detail": failed_detail,
        "artifact_warnings": artifact_warnings,
    }


def render_report(stats: dict) -> str:
    """Human-readable multi-section diagnostics report from ``parse_run_stats``."""
    lines: list[str] = []
    cfg = stats.get("provider_config") or {}
    prov = stats.get("provenance") or {}
    tot = stats.get("totals") or {}

    lines.append("# V7 oracle — run report")
    lines.append("")
    if stats.get("artifact_warnings"):
        lines.append("## Artifact warnings")
        lines.extend("- " + str(w) for w in stats["artifact_warnings"][:20])
        lines.append("")
    lines.append(f"- out_dir: {stats.get('out_dir')}")
    lines.append(f"- provider: {cfg.get('provider')}  model: {cfg.get('model') or '(not recorded)'}  base_url: {cfg.get('base_url') or '(not recorded)'}")
    if stats.get("provider_endpoint"):
        lines.append(f"- recorded request endpoint: {stats['provider_endpoint']}")
    lines.append(f"- live execution: {prov.get('model_live_execution')}   received calls: {prov.get('received_provider_calls')}   elapsed: {prov.get('elapsed_seconds')}s")
    if stats.get("gui_status"):
        lines.append(f"- GUI process status: {stats['gui_status']}  exit_code: {stats.get('process_exit_code')}")
    lines.append("")

    lines.append("## Totals")
    lines.append(
        f"status={stats.get('status')}  passed={tot.get('passed')}  failed={tot.get('failed')}  "
        f"blocked={tot.get('blocked')}  expected={tot.get('expected')}  observed={tot.get('observed')}  "
        f"runtime_exceptions={tot.get('runtime_exceptions')}"
    )
    lines.append(f"completed comparisons={tot.get('completed')}  incomplete observed cases={tot.get('incomplete_observed')}  not started={tot.get('not_started')}")
    lines.append(f"case result source: {stats.get('comparison_source', 'NOT_RECORDED')}")
    if stats.get("comparison_source") == "progress.jsonl":
        lines.append("Partial run: completed PASS/FAIL/BLOCKED results are preserved from the last case_finished events. An incomplete run is not an all-case failure.")
    if stats.get("request_counts"):
        counts = stats["request_counts"]
        lines.append(f"requests started={counts.get('requests_started')}  finished={counts.get('requests_finished')}  failed={counts.get('requests_failed')}")
    lines.append("")

    health = stats.get("provider_health") or {}
    lines.append("## Provider transport health")
    lines.append(f"source: {stats.get('provider_health_source', 'NOT_RECORDED')}")
    lines.append(f"received={health.get('received')}  failed={health.get('failed')}  avg_ms={health.get('avg_ms')}  max_ms={health.get('max_ms')}")
    if health.get("errors"):
        lines.append("transport errors:")
        for msg, n in list(health["errors"].items())[:15]:
            lines.append(f"  - {n}x  {msg}")
    else:
        lines.append("no transport errors recorded")
    lines.append("")

    if stats.get("failure_attribution_counts"):
        lines.append("## Failure attribution")
        for k, v in stats["failure_attribution_counts"].items():
            lines.append(f"  - {v}x  {k}")
        lines.append("")

    if stats.get("blocker_counts"):
        lines.append("## Blockers")
        for k, v in stats["blocker_counts"].items():
            lines.append(f"  - {v}x  {k}")
        lines.append("")

    if stats.get("diagnostic_code_counts"):
        lines.append("## Diagnostic codes (across cases)")
        for k, v in stats["diagnostic_code_counts"].items():
            lines.append(f"  - {v}x  {k}")
        lines.append("")

    non_passing = stats.get("non_passing_cases") or []
    lines.append(f"## Non-passing cases ({len(non_passing)})")
    for c in non_passing[:200]:
        extra = []
        if c.get("blockers"):
            extra.append("blocked=" + ",".join(c["blockers"]))
        if c.get("diag_codes"):
            extra.append("diag=" + ",".join(c["diag_codes"]))
        suffix = ("  [" + " ".join(extra) + "]") if extra else ""
        lines.append(f"  - {c['case_id']}: {c['status']}{suffix}")
    if len(non_passing) > 200:
        lines.append(f"  ... and {len(non_passing) - 200} more (see gui_stats.json)")
    lines.append("")

    detail = stats.get("failed_case_detail") or []
    if detail:
        lines.append(f"## Failed case error detail ({len(detail)})")
        for c in detail[:60]:
            lines.append(f"- {c.get('case_id')}  [{c.get('attribution')}]")
            if c.get("first_observed_text"):
                lines.append(f"    - runtime: {str(c['first_observed_text'])[:2000]}")
            if c.get("native_diagnostic_text"):
                lines.append(f"    - native IR: {str(c['native_diagnostic_text'])[:4000]}")
            for e in (c.get("errors") or [])[:6]:
                if not isinstance(e, dict):
                    lines.append(f"    - {str(e)[:2000]}")
                    continue
                bits = [e.get(k) for k in ("detail", "error", "path", "step") if e.get(k) is not None]
                lines.append(f"    - {' | '.join(str(b) for b in bits)}")
        if len(detail) > 60:
            lines.append(f"... and {len(detail) - 60} more (see gui_stats.json)")
        lines.append("")

    return "\n".join(lines)


def process_run_status(status: str, exit_code: int, *, normal_exit: bool, completed: bool, cancelled: bool = False) -> str:
    """A partial/abnormal process can never be displayed as a successful run."""
    if cancelled:
        return "CANCELLED"
    if not normal_exit:
        return "ERROR"
    if not completed:
        return "INCOMPLETE" if exit_code == 0 else "ERROR"
    expected_exit = {"PASS": 0, "PARTIAL": 0, "ORACLE_MATCH": 0, "FAIL": 1, "BLOCKED": 3}
    if status not in expected_exit:
        return "INCOMPLETE"
    return status if exit_code == expected_exit[status] else "ERROR"


def save_report(out_dir: Path, stats: dict) -> tuple[Path, Path]:
    """Persist the report + raw stats into the run dir for later diagnostics."""
    out_dir = Path(out_dir)
    md_path = out_dir / "gui_report.md"
    json_path = out_dir / "gui_stats.json"
    md_path.write_text(render_report(stats), encoding="utf-8")
    json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return md_path, json_path
