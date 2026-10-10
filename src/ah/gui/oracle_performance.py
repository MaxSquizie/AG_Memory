"""Observational oracle timing reduction; no prompts or responses are retained.

Run clocks and HTTP durations are distinct. Sums of request durations may
exceed wall time when requests overlap, so they are never reported as shares.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import statistics

SCHEMA = "v7-oracle-performance-1"


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _clock(row):
    # elapsed_seconds belongs to the emitter; it is not HTTP latency.
    elapsed = _number(row.get("elapsed_seconds"))
    try:
        stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, TypeError, AttributeError):
        stamp = None
    return {"elapsed": elapsed, "timestamp": stamp}


def _difference(first, last):
    if first is None or last is None:
        return None
    for domain in ("elapsed", "timestamp"):
        if first[domain] is not None and last[domain] is not None:
            return last[domain] - first[domain]
    return None


def _distribution(values, missing=0, *, total=True):
    values = sorted(values)
    result = {"count": len(values), "missing_count": missing,
              "median": statistics.median(values) if values else None,
              "p95": values[max(0, math.ceil(len(values) * .95) - 1)] if values else None,
              "mean": statistics.mean(values) if values else None,
              "min": values[0] if values else None, "max": values[-1] if values else None}
    if total:
        result["total"] = math.fsum(values) if values else None
    return result


def _stats(row):
    explicit = row.get("provider_stats")
    if isinstance(explicit, dict) and not row.get("provider_stats_truncated"):
        return {key: value for key in ("input_tokens", "total_output_tokens",
                "reasoning_output_tokens", "tokens_per_second", "time_to_first_token_seconds")
                if (value := _number(explicit.get(key))) is not None}
    # A truncated preview is not a partial source of trusted numeric metadata.
    if row.get("raw_response_truncated"):
        return {}
    raw = row.get("raw_response")
    try:
        reply = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return {}
    if not isinstance(reply, dict) or not isinstance(reply.get("stats"), dict):
        return {}
    return {key: value for key in ("input_tokens", "total_output_tokens",
            "reasoning_output_tokens", "tokens_per_second", "time_to_first_token_seconds")
            if (value := _number(reply["stats"].get(key))) is not None}


def _union_seconds(intervals):
    total = 0.0
    overlap = False
    end = None
    for first, last in sorted(intervals):
        if end is None or first >= end:
            total += last - first
            end = last
        else:
            overlap = True
            if last > end:
                total += last - end
                end = last
    return total if intervals else None, overlap


def summarize_progress(path: Path) -> dict:
    """Stream even an interrupted progress file, keeping only numeric metadata.

    The first finish for each request ID wins. Duplicate/out-of-order seq rows
    are ignored, matching the GUI progress reader. Invalid tail rows are counted
    as observation warnings, not runtime/comparison failures.
    """
    path = Path(path)
    starts, finishes = {}, {}
    invalid = duplicate_seq = duplicate_request = unidentified = 0
    run_first = run_last = last_clock = None
    last_seq = -1
    complete = False
    warnings = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, TypeError):
                    invalid += 1
                    continue
                if not isinstance(row, dict) or row.get("schema_version") != "v7-oracle-progress-1":
                    continue
                seq = row.get("seq")
                if isinstance(seq, bool) or not isinstance(seq, int):
                    invalid += 1
                    continue
                if seq <= last_seq:
                    duplicate_seq += 1
                    continue
                last_seq = seq
                clock = _clock(row)
                if any(value is not None for value in clock.values()):
                    last_clock = clock
                kind = row.get("event")
                if kind == "run_started":
                    run_first = clock
                elif kind == "run_finished":
                    run_last = clock
                    complete = True
                if kind not in {"request_started", "request_finished"}:
                    continue
                request_id = row.get("request_id")
                if not isinstance(request_id, str) or not request_id:
                    request_id = f"unidentified-event:{seq}"
                    unidentified += 1
                if kind == "request_started":
                    if request_id in starts:
                        duplicate_request += 1
                    else:
                        starts[request_id] = clock
                else:
                    if request_id in finishes:
                        duplicate_request += 1
                        continue
                    finishes[request_id] = {"clock": clock,
                        "http": _number(row.get("request_elapsed_seconds")),
                        "status": row.get("status"), "stats": _stats(row)}
    except (OSError, UnicodeError) as exc:
        warnings.append(f"Cannot read performance source: {type(exc).__name__}: {exc}")
    if invalid:
        warnings.append(f"Invalid or incomplete progress records: {invalid}")
    observed_end = run_last if run_last is not None else last_clock
    wall = _difference(run_first, observed_end)
    if wall is not None and wall < 0:
        warnings.append("Progress clocks are inconsistent; wall time is unknown")
        wall = None
    n = len(finishes)
    http = [r["http"] for r in finishes.values() if r["http"] is not None]
    fields = {}
    for field in ("input_tokens", "total_output_tokens", "reasoning_output_tokens",
                  "time_to_first_token_seconds", "tokens_per_second"):
        values = [r["stats"][field] for r in finishes.values() if field in r["stats"]]
        fields[field] = _distribution(values, n - len(values), total=field != "tokens_per_second")
    residuals = []
    residual_tokens = []
    intervals = []
    # A union must use one clock domain throughout, rather than mixing epoch
    # timestamps and elapsed monotonic counters for partially recorded rows.
    interval_domain = max(("elapsed", "timestamp"), key=lambda domain: sum(
        starts.get(request_id) is not None and starts[request_id][domain] is not None
        and record["clock"][domain] is not None for request_id, record in finishes.items()))
    for request_id, record in finishes.items():
        first_clock = starts.get(request_id)
        first = first_clock[interval_domain] if first_clock is not None else None
        last = record["clock"][interval_domain]
        if first is not None and last is not None and last >= first:
            intervals.append((first, last))
        ttft = record["stats"].get("time_to_first_token_seconds")
        if record["http"] is not None and ttft is not None and record["http"] >= ttft:
            residual = record["http"] - ttft
            residuals.append(residual)
            output = record["stats"].get("total_output_tokens")
            if residual > 0 and output is not None:
                residual_tokens.append((output, residual))
    active, overlap = _union_seconds(intervals)
    return {"schema_version": SCHEMA, "source": path.name,
        "run_finished_recorded": complete, "wall_seconds": wall,
        "wall_scope": "COMPLETE_RUN" if complete else "OBSERVED_PARTIAL_RUN",
        "requests": {"started": len(starts), "finished": n,
            "unfinished_started": len(set(starts) - set(finishes)),
            "failed": sum(r["status"] in {"FAILED", "ERROR"} for r in finishes.values()),
            "unidentified_events": unidentified},
        "http_seconds": _distribution(http, n - len(http)),
        "request_intervals": {"count": len(intervals), "missing_count": n - len(intervals),
            "observed_active_wall_seconds": active, "overlap_observed": overlap,
            "clock_domain": interval_domain,
            "duration_sum_is_wall_share": False},
        "lmstudio_stats": fields,
        "http_minus_ttft_seconds": {**_distribution(residuals, n - len(residuals)),
            "meaning": "ESTIMATE: HTTP time minus server TTFT; includes decoding and transport/serialization, not pure generation time"},
        "estimated_residual_output_tokens_per_second":
            math.fsum(v[0] for v in residual_tokens) / math.fsum(v[1] for v in residual_tokens) if residual_tokens else None,
        "estimated_residual_rate_request_count": len(residual_tokens),
        "ignored_duplicate_seq_records": duplicate_seq,
        "ignored_duplicate_request_events": duplicate_request,
        "artifact_warnings": warnings,
        "gates_pass_claim": False}


def _fmt(value, suffix=""):
    return "unknown" if value is None else f"{value:.3f}{suffix}"


def format_performance(summary: dict) -> list[str]:
    """Concise CLI/GUI lines with explicit coverage and estimation labels."""
    http = summary.get("http_seconds") or {}
    stats = summary.get("lmstudio_stats") or {}
    input_tokens = stats.get("input_tokens") or {}
    output_tokens = stats.get("total_output_tokens") or {}
    ttft = stats.get("time_to_first_token_seconds") or {}
    reasoning = stats.get("reasoning_output_tokens") or {}
    rates = stats.get("tokens_per_second") or {}
    n = (summary.get("requests") or {}).get("finished", 0)
    return [f"Performance ({summary.get('wall_scope', 'UNKNOWN')}): wall={_fmt(summary.get('wall_seconds'), 's')}; "
            f"HTTP sum={_fmt(http.get('total'), 's')} (coverage {http.get('count', 0)}/{n}), "
            f"median={_fmt(http.get('median'), 's')}, p95={_fmt(http.get('p95'), 's')}; request sums are not wall-time shares.",
        f"LM Studio tokens: input={_fmt(input_tokens.get('total'))} ({input_tokens.get('count', 0)}/{n}), "
            f"output={_fmt(output_tokens.get('total'))} ({output_tokens.get('count', 0)}/{n}), "
            f"reasoning={_fmt(reasoning.get('total'))} ({reasoning.get('count', 0)}/{n}); "
            f"TTFT sum={_fmt(ttft.get('total'), 's')} ({ttft.get('count', 0)}/{n}), "
            f"reported tokens/s median={_fmt(rates.get('median'))} ({rates.get('count', 0)}/{n}).",
        f"Estimated HTTP-minus-TTFT residual={_fmt((summary.get('http_minus_ttft_seconds') or {}).get('total'), 's')} "
            "(decoding plus transport/serialization, not pure generation time)."]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", required=True, type=Path)
    parser.add_argument("--out", type=Path, help="optional performance JSON; never modifies the source")
    args = parser.parse_args(argv)
    if args.out and (args.out.resolve() == args.progress.resolve()
            or (args.out.exists() and args.progress.exists() and args.out.samefile(args.progress))):
        parser.error("--out must not overwrite --progress (including symlink/hardlink aliases)")
    summary = summarize_progress(args.progress)
    if args.out:
        args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(format_performance(summary)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
