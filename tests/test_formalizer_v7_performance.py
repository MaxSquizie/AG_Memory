"""Timing observation cannot substitute guessed zeroes or comparator outcomes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.formalizer_v7_performance import SCHEMA, format_performance, main, summarize_progress
from ah.gui.oracle_semantic_runner import parse_run_stats, render_report


def event(seq, kind, clock=None, **values):
    row = {"schema_version": "v7-oracle-progress-1", "seq": seq, "event": kind, **values}
    if clock is not None:
        row["elapsed_seconds"] = clock
    return row


def write(tmp_path, rows, tail=""):
    path = tmp_path / "progress.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n" + tail)
    return path


def raw(input=100, output=30, reasoning=0, rate=50, ttft=.5):
    return json.dumps({"output": [{"content": "secret reply"}], "stats": {
        "input_tokens": input, "total_output_tokens": output,
        "reasoning_output_tokens": reasoning, "tokens_per_second": rate,
        "time_to_first_token_seconds": ttft}})


def test_complete_uses_http_field_not_elapsed_run_clock_and_records_token_coverage(tmp_path):
    path = write(tmp_path, [event(1, "run_started", 0),
        event(2, "request_started", 1, request_id="R1", prompt="secret prompt"),
        event(3, "request_finished", 3, request_id="R1", status="SUCCESS",
              request_elapsed_seconds=2, raw_response=raw()),
        event(4, "request_started", 4, request_id="R2"),
        event(5, "request_finished", 8, request_id="R2", status="SUCCESS",
              request_elapsed_seconds=4, raw_response=raw(output=50, rate=25, ttft=1.5)),
        event(6, "run_finished", 10)])
    original = path.read_bytes()
    result = summarize_progress(path)
    assert result["schema_version"] == SCHEMA
    assert result["wall_seconds"] == 10
    assert result["run_finished_recorded"] and result["wall_scope"] == "COMPLETE_RUN"
    assert result["http_seconds"]["total"] == 6
    assert result["http_seconds"]["median"] == 3
    assert result["http_seconds"]["p95"] == 4
    assert result["lmstudio_stats"]["input_tokens"]["total"] == 200
    assert result["lmstudio_stats"]["total_output_tokens"]["total"] == 80
    assert result["lmstudio_stats"]["reasoning_output_tokens"]["total"] == 0
    assert result["lmstudio_stats"]["tokens_per_second"]["mean"] == 37.5
    assert "total" not in result["lmstudio_stats"]["tokens_per_second"]
    assert result["http_minus_ttft_seconds"]["total"] == 4
    assert result["estimated_residual_output_tokens_per_second"] == 20
    assert result["request_intervals"]["observed_active_wall_seconds"] == 6
    assert not result["request_intervals"]["overlap_observed"]
    assert result["request_intervals"]["duration_sum_is_wall_share"] is False
    assert "secret" not in json.dumps(result)
    assert "not pure generation" in "\n".join(format_performance(result))
    assert path.read_bytes() == original


def test_missing_and_truncated_stats_are_unknown_not_zero(tmp_path):
    path = write(tmp_path, [event(1, "run_started", 0),
        event(2, "request_finished", 2, request_id="R1", status="SUCCESS", raw_response=raw(),
              raw_response_truncated=True),
        event(3, "request_finished", 4, request_id="R2", status="ERROR", error="secret error"),
        event(4, "request_finished", 6, request_id="R3", status="SUCCESS", raw_response="{truncated")])
    result = summarize_progress(path)
    assert result["http_seconds"]["total"] is None
    assert result["http_seconds"]["missing_count"] == 3
    assert result["requests"]["failed"] == 1
    for field in result["lmstudio_stats"].values():
        assert field["count"] == 0 and field["missing_count"] == 3
        assert field["mean"] is None
    assert result["http_minus_ttft_seconds"]["total"] is None
    assert result["wall_scope"] == "OBSERVED_PARTIAL_RUN"
    assert result["wall_seconds"] == 6
    assert "unknown" in "\n".join(format_performance(result))


def test_explicit_provider_stats_survive_raw_preview_truncation(tmp_path):
    path = write(tmp_path, [event(1, "run_started", 0),
        event(2, "request_finished", 2, request_id="R", request_elapsed_seconds=2,
              raw_response="{truncated", raw_response_truncated=True, provider_stats={
                  "input_tokens": 100, "total_output_tokens": 20,
                  "reasoning_output_tokens": 0, "tokens_per_second": 50,
                  "time_to_first_token_seconds": .5})])
    result = summarize_progress(path)
    assert result["lmstudio_stats"]["total_output_tokens"]["total"] == 20
    assert result["lmstudio_stats"]["reasoning_output_tokens"]["total"] == 0
    assert result["http_minus_ttft_seconds"]["total"] == 1.5


def test_overlap_and_incomplete_request_never_turn_duration_sum_into_wall_share(tmp_path):
    path = write(tmp_path, [event(1, "run_started", 0),
        event(2, "request_started", 1, request_id="R1"),
        event(3, "request_started", 2, request_id="R2"),
        event(4, "request_finished", 5, request_id="R1", request_elapsed_seconds=4),
        event(5, "request_finished", 6, request_id="R2", request_elapsed_seconds=4),
        event(6, "request_started", 7, request_id="R3")], tail='{"event":')
    result = summarize_progress(path)
    assert result["http_seconds"]["total"] == 8
    assert result["wall_seconds"] == 7
    assert result["request_intervals"]["observed_active_wall_seconds"] == 5
    assert result["request_intervals"]["overlap_observed"]
    assert result["requests"]["unfinished_started"] == 1
    assert result["artifact_warnings"] == ["Invalid or incomplete progress records: 1"]


def test_duplicate_seq_and_request_ids_do_not_inflate_totals(tmp_path):
    path = write(tmp_path, [event(1, "run_started", 0),
        event(2, "request_started", 1, request_id="R"),
        event(2, "request_started", 1, request_id="R"),
        event(3, "request_started", 1, request_id="R"),
        event(4, "request_finished", 2, request_id="R", request_elapsed_seconds=1, raw_response=raw()),
        event(5, "request_finished", 3, request_id="R", request_elapsed_seconds=99, raw_response=raw()),
        event(4, "request_finished", 3, request_id="R", request_elapsed_seconds=99, raw_response=raw()),
        event(6, "run_finished", 4)])
    result = summarize_progress(path)
    assert result["requests"]["started"] == result["requests"]["finished"] == 1
    assert result["http_seconds"]["total"] == 1
    assert result["lmstudio_stats"]["total_output_tokens"]["total"] == 30
    assert result["ignored_duplicate_seq_records"] == 2
    assert result["ignored_duplicate_request_events"] == 2


def test_clock_domains_are_not_mixed_and_invalid_numbers_are_unknown(tmp_path):
    path = write(tmp_path, [event(1, "run_started", 0, timestamp="2026-10-10T10:00:00+00:00"),
        event(2, "request_started", request_id="R", timestamp="2026-10-10T10:00:01+00:00"),
        event(3, "request_finished", 3, request_id="R", timestamp="2026-10-10T10:00:03+00:00",
              request_elapsed_seconds=True, raw_response=json.dumps({"stats": {
                  "input_tokens": -1, "total_output_tokens": True, "reasoning_output_tokens": "0"}})),
        event(4, "run_finished", 5, timestamp="2026-10-10T10:00:05+00:00")])
    result = summarize_progress(path)
    assert result["wall_seconds"] == 5
    assert result["request_intervals"]["clock_domain"] == "timestamp"
    assert result["request_intervals"]["observed_active_wall_seconds"] == 2
    assert result["http_seconds"]["total"] is None
    assert result["lmstudio_stats"]["reasoning_output_tokens"]["total"] is None


def test_gui_fallback_keeps_comparisons_and_summary_has_no_raw_payload(tmp_path):
    write(tmp_path, [event(1, "run_started", 0, total=1),
        event(2, "request_started", 1, request_id="R", prompt="secret prompt"),
        event(3, "request_finished", 3, request_id="R", status="SUCCESS", request_elapsed_seconds=2,
              raw_response=raw()),
        event(4, "case_finished", 4, case_id="C", status="FAIL", errors=[]),
        event(5, "run_finished", 5, status="FAIL")])
    stats = parse_run_stats(tmp_path)
    assert stats["status"] == "FAIL" and stats["totals"]["failed"] == 1
    assert stats["performance"]["http_seconds"]["total"] == 2
    report = render_report(stats)
    assert "## Performance" in report and "HTTP sum=2.000s" in report
    assert "secret" not in json.dumps(stats["performance"])
    # The persisted artifact is authoritative for a completed report.
    artifact = stats["performance"]
    artifact["wall_seconds"] = 10
    (tmp_path / "performance.json").write_text(json.dumps(artifact))
    assert parse_run_stats(tmp_path)["performance"]["wall_seconds"] == 10


def test_cli_writes_only_requested_artifact_and_preserves_source(tmp_path, capsys):
    path = write(tmp_path, [event(1, "run_started", 0), event(2, "run_finished", 1)])
    source = path.read_bytes()
    out = tmp_path / "timing.json"
    assert main(["--progress", str(path), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["http_seconds"]["total"] is None
    assert "coverage 0/0" in capsys.readouterr().out
    assert path.read_bytes() == source


def test_missing_file_is_an_observation_warning(tmp_path):
    result = summarize_progress(tmp_path / "missing.jsonl")
    assert result["wall_seconds"] is None
    assert result["http_seconds"]["total"] is None
    assert result["artifact_warnings"]
    assert result["gates_pass_claim"] is False


@pytest.mark.parametrize("alias", ["same_path", "hardlink", "symlink"])
def test_cli_cannot_overwrite_progress_even_through_alias(tmp_path, alias):
    path = write(tmp_path, [event(1, "run_started", 0)])
    source = path.read_bytes()
    dest = path if alias == "same_path" else tmp_path / "alias.jsonl"
    if alias == "hardlink":
        os.link(path, dest)
    elif alias == "symlink":
        dest.symlink_to(path)
    with pytest.raises(SystemExit) as exc:
        main(["--progress", str(path), "--out", str(dest)])
    assert exc.value.code == 2
    assert path.read_bytes() == source


def test_gui_helpers_import_without_checkout_cwd_or_tools_package(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c",
        "from ah.gui.oracle_semantic_runner import parse_run_stats; "
        "from ah.gui.oracle_performance import summarize_progress; print('imported')"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(repo / "src")},
        text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "imported"
