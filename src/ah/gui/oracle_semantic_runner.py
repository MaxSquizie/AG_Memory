"""Semantic (model-required) V7 oracle runner helpers for the GUI.

Pure logic only (no Qt imports): model detection, deterministic selection of the
model-dependent corpus subset, subprocess command construction, and detailed
post-run statistics aggregation + report rendering. The GUI layer in
``semantic_test_window.py`` drives a QProcess with these helpers so the UI stays
responsive during long live-model runs.

"Model-required" cases are exactly those whose steps contain a raw-text
``formalize`` action: they cannot execute without a live provider (the runner
marks them ``BLOCKED_LOCAL_PROVIDER_DISABLED`` when disabled). In the current
corpus this is precisely the 640 ``pipeline``-tier cases, so selection uses
``--tier pipeline``.
"""
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
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.putrequest("GET", "/v1/models")
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
    models = data.get("data") or []
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
) -> list[str]:
    """argv (after the interpreter) for a live LM Studio run of the model set."""
    corpus = repo_root / "data" / "formalizer_v7_oracle"
    runner = repo_root / "tools" / "run_formalizer_v7_oracle.py"
    return [
        str(runner),
        "--corpus", str(corpus),
        "--provider", "lmstudio",
        "--base-url", base_url,
        "--model", model,
        "--timeout", str(timeout),
        "--max-tokens", str(max_tokens),
        "--tier", "pipeline",
        "--out", str(out_dir),
    ]


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_actual(out_dir: Path):
    gz = out_dir / "actual.jsonl.gz"
    plain = out_dir / "actual.jsonl"
    if gz.is_file():
        with gzip.open(gz, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    elif plain.is_file():
        for line in plain.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


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
        saw_received = False
        case_failed_error = None
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
            state = payload.get("state")
            if state == "RECEIVED":
                saw_received = True
            elif state in ("FAILED", "ERROR"):
                case_failed_error = payload.get("error") or f"provider {state}"
            ms = payload.get("response_time_ms")
            if isinstance(ms, (int, float)):
                times.append(float(ms))
        if saw_received:
            received += 1
        elif case_failed_error is not None:
            failed += 1
            key = str(case_failed_error)[:160]
            errors[key] = errors.get(key, 0) + 1
    return {
        "received": received,
        "failed": failed,
        "errors": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
        "avg_ms": (sum(times) / len(times)) if times else None,
        "max_ms": max(times) if times else None,
    }


def parse_run_stats(out_dir: Path) -> dict:
    """Aggregate every run artifact into one detailed diagnostics structure."""
    out_dir = Path(out_dir)
    summary = _read_json(out_dir / "summary.json") or {}
    issues = _read_json(out_dir / "issues.json") or {}
    comparison = _read_json(out_dir / "comparison.json") or {}
    run_config = _read_json(out_dir / "run_config.json") or {}
    provenance = _read_json(out_dir / "provenance.json") or {}

    # Per-case diagnostics codes from the actual stream.
    diag_counts: dict[str, int] = {}
    per_case_diag: dict[str, list[str]] = {}
    for rec in _iter_actual(out_dir):
        cid = rec.get("case_id")
        if not cid:
            continue
        act = (rec.get("checkpoints") or [{}])[0].get("actual") or {}
        codes = ((act.get("diagnostics") or {}).get("codes")) or []
        for code in codes:
            diag_counts[code] = diag_counts.get(code, 0) + 1
        per_case_diag[cid] = list(codes)

    # Per-case status/blockers from the comparison results.
    per_case_status: dict[str, dict] = {}
    for res in (comparison.get("results") or []):
        cid = res.get("case_id")
        if not cid:
            continue
        blockers = [b.get("reason") for b in (res.get("blockers") or []) if isinstance(b, dict)]
        per_case_status[cid] = {
            "status": res.get("status"),
            "blockers": blockers,
            "errors": res.get("errors") or [],
        }

    # Non-passing cases merged with diagnostics + provider state.
    non_passing: list[dict] = []
    for cid in sorted(set(per_case_status) | set(per_case_diag)):
        info = per_case_status.get(cid, {})
        status = info.get("status") or ("FAIL" if per_case_diag.get(cid) else "UNKNOWN")
        if status == "PASS":
            continue
        non_passing.append({
            "case_id": cid,
            "status": status,
            "blockers": info.get("blockers", []),
            "diag_codes": per_case_diag.get(cid, []),
        })

    failed_detail = issues.get("cases") or []

    return {
        "out_dir": str(out_dir),
        "provider_config": run_config.get("provider_config"),
        "selected_case_ids": run_config.get("selected_case_ids", []),
        "status": summary.get("status"),
        "totals": {
            "passed": summary.get("passed_cases"),
            "failed": summary.get("failed_cases"),
            "blocked": summary.get("blocked_cases"),
            "expected": comparison.get("expected_cases"),
            "observed": comparison.get("observed_cases"),
            "runtime_exceptions": summary.get("runtime_exceptions"),
        },
        "blocker_counts": summary.get("blocker_counts", {}),
        "failure_attribution_counts": summary.get("failure_attribution_counts", {}),
        "provenance": {
            "model_live_execution": provenance.get("model_live_execution"),
            "received_provider_calls": provenance.get("received_provider_calls"),
            "elapsed_seconds": provenance.get("elapsed_seconds"),
            "source_unchanged": provenance.get("source_unchanged"),
        },
        "provider_health": _provider_health(out_dir),
        "diagnostic_code_counts": dict(sorted(diag_counts.items(), key=lambda kv: -kv[1])),
        "non_passing_cases": non_passing,
        "failed_case_detail": failed_detail,
    }


def render_report(stats: dict) -> str:
    """Human-readable multi-section diagnostics report from ``parse_run_stats``."""
    lines: list[str] = []
    cfg = stats.get("provider_config") or {}
    prov = stats.get("provenance") or {}
    tot = stats.get("totals") or {}

    lines.append("# V7 semantic oracle — model run report")
    lines.append("")
    lines.append(f"- out_dir: {stats.get('out_dir')}")
    lines.append(f"- provider: {cfg.get('provider')}  model: {cfg.get('model') or '(auto)'}  base_url: {cfg.get('base_url')}")
    lines.append(f"- live execution: {prov.get('model_live_execution')}   received calls: {prov.get('received_provider_calls')}   elapsed: {prov.get('elapsed_seconds')}s")
    lines.append("")

    lines.append("## Totals")
    lines.append(
        f"status={stats.get('status')}  passed={tot.get('passed')}  failed={tot.get('failed')}  "
        f"blocked={tot.get('blocked')}  expected={tot.get('expected')}  observed={tot.get('observed')}  "
        f"runtime_exceptions={tot.get('runtime_exceptions')}"
    )
    lines.append("")

    health = stats.get("provider_health") or {}
    lines.append("## Provider transport health")
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
            for e in (c.get("errors") or [])[:6]:
                bits = [e.get(k) for k in ("detail", "error", "path", "step") if e.get(k) is not None]
                lines.append(f"    - {' | '.join(str(b) for b in bits)}")
        if len(detail) > 60:
            lines.append(f"... and {len(detail) - 60} more (see gui_stats.json)")
        lines.append("")

    return "\n".join(lines)


def save_report(out_dir: Path, stats: dict) -> tuple[Path, Path]:
    """Persist the report + raw stats into the run dir for later diagnostics."""
    out_dir = Path(out_dir)
    md_path = out_dir / "gui_report.md"
    json_path = out_dir / "gui_stats.json"
    try:
        md_path.write_text(render_report(stats), encoding="utf-8")
    except Exception:
        pass
    try:
        json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass
    return md_path, json_path
