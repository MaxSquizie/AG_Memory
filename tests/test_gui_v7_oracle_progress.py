from __future__ import annotations

import json
from pathlib import Path

from ah.gui.oracle_progress_state import OracleOutputParser, OracleProgressState
from ah.gui.oracle_semantic_runner import build_oracle_command, parse_run_stats, _provider_health


def event(seq, kind, **fields):
    return {"schema_version": "v7-oracle-progress-1", "seq": seq, "event": kind, **fields}


def test_progress_parser_handles_partial_utf8_and_json_without_losing_events():
    data = ("startup\nV7_PROGRESS " + json.dumps(event(0, "request_started", prompt="Книга"), ensure_ascii=False) + "\n").encode()
    parser = OracleOutputParser()
    events, logs = [], []
    for byte in data:
        a, b = parser.feed(bytes([byte]))
        events.extend(a)
        logs.extend(b)
    assert events == [event(0, "request_started", prompt="Книга")]
    assert logs == ["startup"]
    assert parser.feed(b'V7_PROGRESS {bad}\n')[1][0].startswith("Invalid oracle")


def test_waiting_clock_counts_sent_calls_before_result_and_ignores_duplicates():
    state = OracleProgressState(started_at=10)
    assert state.apply(event(0, "run_started", total=3), now=10)
    assert state.apply(event(1, "request_started", case_id="A38", action="formalize", requests_started=1, requests_finished=0), now=11)
    assert "Запросы 0/1" in state.text(now=20)
    assert "ожидание модели 9 с" in state.text(now=20)
    assert not state.apply(event(1, "request_started", requests_started=99), now=20)
    state.apply(event(2, "request_finished", requests_started=1, requests_finished=1), now=21)
    state.apply(event(3, "case_finished", total=3, completed=1, blocked=1), now=22)
    assert "BLOCKED 1" in state.text(now=22)
    assert "ожидание" not in state.text(now=22)


def test_three_gui_selections_use_actual_v7_runner_and_progress(tmp_path):
    root = Path(__file__).resolve().parents[1]
    language = build_oracle_command(root, "http://localhost:1234", "model", tmp_path)
    assert language[language.index("--tier") + 1] == "pipeline"
    assert "--progress-jsonl" in language
    complete = build_oracle_command(root, "http://localhost:1234", "model", tmp_path, tiers=())
    assert "--tier" not in complete
    components = build_oracle_command(root, "", "", tmp_path, provider="disabled", tiers=("component", "durability"))
    assert components[components.index("--provider") + 1] == "disabled"
    assert components.count("--tier") == 2


def test_provider_health_counts_calls_not_cases_and_incomplete_is_not_fail(tmp_path):
    case = tmp_path / "cases" / "same-case"
    case.mkdir(parents=True)
    calls = [{"kind": "prov_call", "id": f"call{i}", "state": state, "response_time_ms": ms}
             for i, state, ms in [(1, "PENDING", 0), (1, "RECEIVED", 10), (2, "RECEIVED", 20), (3, "FAILED", 30)]]
    (case / "journal.log").write_text("\n".join(json.dumps({"payload": c}) for c in calls))
    health = _provider_health(tmp_path)
    assert health["received"] == 2
    assert health["failed"] == 1
    assert health["avg_ms"] == 20
    (tmp_path / "actual.jsonl").write_text(json.dumps({"case_id": "C", "checkpoints": [{"actual": {"diagnostics": {"codes": ["EXPECTED"]}}}]}))
    stats = parse_run_stats(tmp_path)
    assert stats["status"] == "INCOMPLETE"
    assert stats["non_passing_cases"][0]["status"] == "INCOMPLETE"


def test_corrupt_archive_does_not_break_cancelled_gui_report(tmp_path):
    (tmp_path / "actual.jsonl.gz").write_bytes(b'partial-gzip')
    stats = parse_run_stats(tmp_path)
    assert stats["status"] == "INCOMPLETE"
    assert stats["artifact_warnings"]
    # A crash during compression leaves the complete plain stream available.
    (tmp_path / "actual.jsonl").write_text(json.dumps({"case_id": "C", "checkpoints": []}))
    assert not parse_run_stats(tmp_path)["artifact_warnings"]


def test_process_status_never_labels_abnormal_or_missing_completion_as_success():
    from ah.gui.oracle_semantic_runner import process_run_status
    assert process_run_status("PARTIAL", 0, normal_exit=True, completed=True) == "PARTIAL"
    assert process_run_status("ORACLE_MATCH", 1, normal_exit=True, completed=True) == "ERROR"
    assert process_run_status("PARTIAL", 1, normal_exit=True, completed=True) == "ERROR"
    assert process_run_status("BLOCKED", 3, normal_exit=True, completed=True) == "BLOCKED"
    assert process_run_status("FAIL", 1, normal_exit=True, completed=True) == "FAIL"
    assert process_run_status("ORACLE_MATCH", 0, normal_exit=True, completed=False) == "INCOMPLETE"
    assert process_run_status("ORACLE_MATCH", -1, normal_exit=False, completed=True, cancelled=True) == "CANCELLED"


def test_gui_ollama_uses_explicit_native_provider(tmp_path):
    root = Path(__file__).resolve().parents[1]
    argv = build_oracle_command(root, "http://localhost:11434", "model", tmp_path, provider="ollama")
    assert argv[argv.index("--provider") + 1] == "ollama"
