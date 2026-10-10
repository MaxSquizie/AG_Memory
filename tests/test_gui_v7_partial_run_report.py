"""Interrupted oracle reports retain recorded comparisons, not guessed failures."""
from __future__ import annotations

import json

from ah.gui.oracle_semantic_runner import parse_run_stats, render_report, save_report


def event(seq, kind, **fields):
    return {"schema_version": "v7-oracle-progress-1", "seq": seq, "event": kind, **fields}


def progress(tmp_path, rows, tail=""):
    (tmp_path / "progress.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n" + tail,
        encoding="utf-8")


def test_cancelled_51_of_640_run_preserves_nine_passes_and_42_failures(tmp_path):
    # The uploaded stopped run has this shape: final reports never written,
    # 51 completed comparisons and an active request for the 52nd case.
    rows = [event(1, "run_started", total=640, provider="lmstudio", model="local-model",
        selected_case_ids=["C0", {"_omitted_items": 639}])]
    for i in range(51):
        rows.append(event(len(rows) + 1, "case_started", case_id=f"C{i}"))
        rows.append(event(len(rows) + 1, "request_started", case_id=f"C{i}", request_id=f"R{i}",
            endpoint="http://localhost:1234/api/v1/chat"))
        rows.append(event(len(rows) + 1, "request_finished", request_id=f"R{i}", status="SUCCESS",
            request_elapsed_seconds=1.5))
        rows.append(event(len(rows) + 1, "case_finished", case_id=f"C{i}",
            status="PASS" if i < 9 else "FAIL", errors=[] if i < 9 else [{"path": "/assertions/ah", "observed": []}],
            received_provider_calls=i + 1, runtime_diagnostics={"native_diagnostics":
                [] if i < 9 else [{"code": "PROPOSAL_INVALID", "detail": "missing alignment"}]}))
    rows += [event(len(rows) + 1, "case_started", case_id="C51"),
        event(len(rows) + 2, "request_started", case_id="C51", request_id="R51",
            requests_started=52, requests_finished=51, requests_failed=0, elapsed_seconds=295.2)]
    progress(tmp_path, rows)
    original = (tmp_path / "progress.jsonl").read_bytes()

    stats = parse_run_stats(tmp_path)
    assert stats["status"] == "INCOMPLETE"
    assert stats["totals"] == {"passed": 9, "failed": 42, "blocked": 0, "expected": 640,
        "observed": 51, "completed": 51, "incomplete_observed": 1, "not_started": 588, "runtime_exceptions": 0}
    assert len(stats["case_results"]) == 51
    assert len(stats["non_passing_cases"]) == 43
    assert [c for c in stats["non_passing_cases"] if c["status"] == "INCOMPLETE"] == [{
        "case_id": "C51", "status": "INCOMPLETE", "blockers": [], "diag_codes": [],
        "source": "no completed comparison recorded"}]
    assert not any(c["case_id"] == "C0" for c in stats["non_passing_cases"])
    assert stats["diagnostic_code_counts"] == {"PROPOSAL_INVALID": 42}
    assert stats["provider_config"] == {"provider": "lmstudio", "model": "local-model"}
    assert "base_url" not in stats["provider_config"]  # not inferred from the endpoint
    assert stats["provider_endpoint"] == "http://localhost:1234/api/v1/chat"
    assert stats["provider_health"]["received"] == 51
    assert stats["provenance"]["elapsed_seconds"] == 295.2
    assert stats["selected_case_ids"] == ["C0"]
    assert stats["selected_case_ids_complete"] is False
    assert stats["request_counts"]["requests_started"] == 52
    assert stats["comparison_source"] == "progress.jsonl"
    assert (tmp_path / "progress.jsonl").read_bytes() == original


def test_last_case_result_wins_and_running_counters_do_not_replace_comparisons(tmp_path):
    progress(tmp_path, [event(1, "run_started", total=1),
        event(2, "case_finished", case_id="C", status="FAIL", failed=999),
        event(3, "case_finished", case_id="C", status="PASS", passed=999),
        event(3, "case_finished", case_id="C", status="FAIL"),
        event(2, "case_finished", case_id="C", status="BLOCKED")])
    stats = parse_run_stats(tmp_path)
    assert stats["status"] == "INCOMPLETE"  # no run_finished/final report even if all compared
    assert stats["totals"]["passed"] == 1
    assert stats["totals"]["failed"] == stats["totals"]["blocked"] == 0
    assert stats["non_passing_cases"] == []


def test_final_comparison_has_priority_over_live_results(tmp_path):
    progress(tmp_path, [event(1, "run_started", total=1),
        event(2, "case_finished", case_id="C", status="FAIL")])
    (tmp_path / "comparison.json").write_text(json.dumps({"expected_cases": 1, "observed_cases": 1,
        "results": [{"case_id": "C", "status": "PASS"}]}))
    (tmp_path / "summary.json").write_text(json.dumps({"status": "ORACLE_MATCH", "passed_cases": 1,
        "failed_cases": 0, "blocked_cases": 0}))
    stats = parse_run_stats(tmp_path)
    assert stats["status"] == "ORACLE_MATCH"
    assert stats["totals"]["passed"] == 1 and stats["totals"]["failed"] == 0
    assert stats["case_results"] == [{"case_id": "C", "status": "PASS", "source": "comparison.json"}]
    assert stats["non_passing_cases"] == []


def test_partial_report_retains_config_errors_and_distinct_cancelled_process_status(tmp_path):
    cfg = {"provider": "ollama", "model": "local", "base_url": "http://localhost:11434",
        "timeout": 30, "max_tokens": 512}
    progress(tmp_path, [event(1, "run_started", total=2, provider_config=cfg, selected_case_ids=["A", "B"]),
        event(2, "case_finished", case_id="A", status="FAIL", errors=[{"path": "/assertions/ah", "error": "mismatch"}],
            first_observed_text="PROPOSAL_INVALID: missing alignment", native_diagnostic_text="PROPOSAL_INVALID: missing alignment"),
        event(3, "case_started", case_id="B")], tail='{"event":')
    stats = parse_run_stats(tmp_path)
    stats.update(gui_status="CANCELLED", process_exit_code=-15)
    assert stats["provider_config"] == cfg
    assert stats["artifact_warnings"]
    assert stats["failed_case_detail"][0]["errors"][0]["path"] == "/assertions/ah"
    assert stats["selected_case_ids_complete"] is True
    md, raw = save_report(tmp_path, stats)
    text = md.read_text()
    assert "status=INCOMPLETE  passed=0  failed=1" in text
    assert "GUI process status: CANCELLED" in text
    assert "A: FAIL" in text and "B: INCOMPLETE" in text
    assert "http://localhost:11434" in text and "missing alignment" in text
    assert "completed comparisons=1" in text and "case result source: progress.jsonl" in text
    assert json.loads(raw.read_text())["totals"]["completed"] == 1


def test_wal_remains_transport_source_when_progress_preview_is_partial(tmp_path):
    journal = tmp_path / "cases" / "C" / "journal.log"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"payload": {"kind": "prov_call", "id": "R", "state": "RECEIVED",
        "response_time_ms": 20}}))
    progress(tmp_path, [event(1, "run_started", total=1),
        event(2, "request_finished", request_id="other", status="ERROR", error="HTTP 403")])
    stats = parse_run_stats(tmp_path)
    assert stats["provider_health_source"] == "provider WAL"
    assert stats["provider_health"]["received"] == 1
    assert stats["provider_health"]["failed"] == 0


def test_observed_checkpoint_without_completed_comparison_stays_incomplete(tmp_path):
    (tmp_path / "actual.jsonl").write_text(json.dumps({"case_id": "C", "runtime_error": {"type": "RuntimeError"},
        "checkpoints": [{"actual": {"diagnostics": {"codes": ["PROPOSAL_INVALID"]}}}]}))
    stats = parse_run_stats(tmp_path)
    assert stats["totals"]["passed"] == stats["totals"]["failed"] == stats["totals"]["blocked"] == 0
    assert stats["totals"]["runtime_exceptions"] == 1
    assert stats["case_results"] == []
    assert stats["non_passing_cases"][0]["status"] == "INCOMPLETE"
    assert "failed=0" in render_report(stats)


def test_finished_run_with_progress_results_is_not_labelled_partial(tmp_path):
    progress(tmp_path, [event(1, "run_started", total=2),
        event(2, "case_finished", case_id="A", status="PASS"),
        event(3, "case_finished", case_id="B", status="FAIL"),
        event(4, "run_finished", status="FAIL", summary={"status": "FAIL", "passed_cases": 1,
            "failed_cases": 1, "blocked_cases": 0})])
    stats = parse_run_stats(tmp_path)
    assert stats["run_finished_recorded"]
    assert stats["comparison_source"] == "progress.jsonl"
    assert stats["status"] == "FAIL" and stats["totals"]["completed"] == 2
    text = render_report(stats)
    assert "Completed run:" in text and "Partial run:" not in text
    assert "passed=1  failed=1" in text
    # Seeing the final event cannot fill a missing per-case comparison.
    stats["totals"]["completed"] = 1
    assert "Partial run:" in render_report(stats)
