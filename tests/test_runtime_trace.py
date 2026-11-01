"""Runtime observations must remain lossless, correlated and non-invasive."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import csv
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ah.diagnostics import runtime_trace as trace
from ah.diagnostics import session_log


def rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE))


@pytest.fixture(autouse=True)
def isolated_session(monkeypatch):
    monkeypatch.setattr(session_log, "_active", None)
    with trace.bind(), trace.use_trace(None):
        yield
    session = session_log.active_session()
    if session is not None:
        session.runtime_trace.close()


def test_one_physical_row_and_lossless_nested_payload(tmp_path):
    class State(Enum):
        SELECTED = "выбран"

    @dataclass
    class Payload:
        text: str
        status: State
        refs: frozenset
        path: Path

    original = Payload("строка\tс табом\nи переводом\r\\n" * 300, State.SELECTED,
                       frozenset({"b", "a"}), Path("папка/file"))
    path = tmp_path / "trace.tsv"
    with trace.RuntimeTrace(path, session_id="session:test") as writer:
        writer.emit("probe", reason='"a\tb\nc\r\\t', payload=original,
                    sequence=900, timestamp="provider timestamp")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    row = rows(path)[0]
    assert tuple(row) == trace.TSV_COLUMNS
    assert row["sequence"] == "1"
    assert row["schema_version"] == "runtime-tsv-1"
    assert trace.unescape_scalar(row["reason"]) == '"a\tb\nc\r\\t'
    data = json.loads(row["data_json"])
    assert data["payload"] == {"text": original.text, "status": "выбран",
                               "refs": ["a", "b"], "path": "папка/file"}
    assert data["sequence"] == 900
    assert data["timestamp"] == "provider timestamp"
    assert original.refs == frozenset({"a", "b"})


def test_unserializable_values_are_explicit_and_never_mutate_inputs(tmp_path):
    cycle = []
    cycle.append(cycle)
    path = tmp_path / "trace.tsv"
    with trace.RuntimeTrace(path) as writer:
        with pytest.warns(RuntimeWarning, match="serialization markers"):
            writer.emit("unusual", cycle=cycle, unsupported=object(),
                        mapping={1: "one", "1": "string"})
        writer.emit("next", useful="still recorded")
    data = json.loads(rows(path)[0]["data_json"])
    assert data["cycle"][0]["_trace_unserializable"] == "cycle"
    assert data["unsupported"]["_trace_unserializable"] == "unsupported_type"
    assert data["mapping"]["_trace_mapping"] == [[1, "one"], ["1", "string"]]
    assert cycle[0] is cycle
    assert rows(path)[1]["event"] == "next"


def test_non_utf8_input_and_unicode_line_separators_remain_readable(tmp_path):
    path = tmp_path / "trace.tsv"
    with trace.RuntimeTrace(path) as writer:
        writer.emit("input_rejected", source="a\ud800b\u2028c\u2029d")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert json.loads(rows(path)[0]["data_json"])["source"] == "a\ud800b\u2028c\u2029d"


def test_existing_trace_is_never_truncated(tmp_path):
    path = tmp_path / "trace.tsv"
    path.write_text("previous trace\n", encoding="utf-8")
    with pytest.warns(RuntimeWarning, match="FileExistsError"):
        writer = trace.RuntimeTrace(path)
    assert not writer.enabled
    writer.emit("discarded")
    writer.close()
    assert path.read_text(encoding="utf-8") == "previous trace\n"


def test_io_failure_warns_once_and_does_not_replace_business_exception(tmp_path):
    class BrokenFile:
        def write(self, text):
            raise OSError("disk full")

        def close(self):
            pass

    path = tmp_path / "trace.tsv"
    writer = trace.RuntimeTrace(path)
    expected = ValueError("real application failure")
    with trace.use_trace(writer):
        with pytest.warns(RuntimeWarning, match="disk full") as warnings:
            with pytest.raises(ValueError) as raised:
                with trace.span("COMMIT"):
                    writer._file.close()
                    writer._file = BrokenFile()
                    raise expected
        assert raised.value is expected
        assert len(warnings) == 1
        trace.emit("still_disabled")
    assert not writer.enabled


def test_warning_filters_cannot_turn_diagnostics_into_an_exception(tmp_path, capsys):
    import warnings
    path = tmp_path / "exists.tsv"
    path.write_text("prior content", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        writer = trace.RuntimeTrace(path)
    assert not writer.enabled
    assert "Runtime TSV logging disabled" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "prior content"


def test_disabled_context_update_cannot_leak_into_later_enabled_run(tmp_path):
    with trace.use_trace(None):
        with trace.span("DISABLED"):
            trace.update_context(run_id="disabled:run")
    path = tmp_path / "enabled.tsv"
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        trace.emit("enabled")
    assert rows(path)[0]["run_id"] == ""


def test_nested_spans_bind_dynamic_ids_and_restore_context(tmp_path):
    path = tmp_path / "trace.tsv"
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        with trace.span("INTERPRET", run_id=None, source_text="large input") as result:
            trace.update_context(run_id="run:1", observation_id="observation:1", interpretation_version=3)
            with trace.span("T0"):
                trace.emit("token", token="да")
            result["status"] = "APPLIED"
        trace.emit("outside")
    recorded = rows(path)
    outer_start, child_start, token, child_end, outer_end, outside = recorded
    assert outer_end["run_id"] == "run:1"
    assert outer_end["observation_id"] == "observation:1"
    assert outer_end["interpretation_version"] == "3"
    assert child_start["parent_span_id"] == outer_start["span_id"]
    assert child_end["span_id"] == child_start["span_id"]
    assert token["trace_id"] == outer_start["trace_id"]
    assert token["stage"] == "T0"
    assert "source_text" not in json.loads(token["data_json"])
    assert outer_end["status"] == "APPLIED"
    assert float(outer_end["duration_ms"]) >= 0
    assert outside["trace_id"] == outside["run_id"] == outside["stage"] == ""


def test_span_failure_preserves_outcome_and_exact_exception(tmp_path):
    path = tmp_path / "trace.tsv"
    expected = RuntimeError("backend unavailable")
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        with pytest.raises(RuntimeError) as raised:
            with trace.span("PROVIDER", run_id="run:failed") as outcome:
                outcome.update(status="BLOCKED", reason="PROVIDER_UNAVAILABLE")
                raise expected
    assert raised.value is expected
    start, failed = rows(path)
    assert failed["event"] == "span_failed"
    assert failed["status"] == "BLOCKED"
    assert failed["reason"] == "PROVIDER_UNAVAILABLE"
    assert failed["span_id"] == start["span_id"]
    assert json.loads(failed["data_json"])["error_type"] == "RuntimeError"


def test_thread_rows_have_single_serial_order_and_independent_context(tmp_path):
    path = tmp_path / "trace.tsv"
    with trace.RuntimeTrace(path) as writer:
        def worker(index):
            with trace.use_trace(writer), trace.span("THREAD", run_id=f"run:{index}"):
                for step in range(20):
                    trace.emit("step", index=index, step=step)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker, range(8)))
    recorded = rows(path)
    assert [int(row["sequence"]) for row in recorded] == list(range(1, 8 * 22 + 1))
    for index in range(8):
        group = [row for row in recorded if row["run_id"] == f"run:{index}"]
        assert len(group) == 22
        assert len({row["trace_id"] for row in group}) == 1
        for row in group[1:-1]:
            assert json.loads(row["data_json"])["index"] == index
    assert len({row["trace_id"] for row in recorded}) == 8


def test_async_context_isolation(tmp_path):
    path = tmp_path / "trace.tsv"
    async def work(index):
        with trace.span("TASK", run_id=f"task:{index}"):
            await asyncio.sleep(0)
            trace.emit("task_event", index=index)

    async def run():
        await asyncio.gather(work(1), work(2))

    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        asyncio.run(run())
    events = [row for row in rows(path) if row["event"] == "task_event"]
    assert {row["run_id"] for row in events} == {"task:1", "task:2"}
    assert all(row["run_id"] == f"task:{json.loads(row['data_json'])['index']}" for row in events)
    assert len({row["trace_id"] for row in events}) == 2


def test_session_owns_writer_and_replacement_closes_previous(tmp_path):
    # Remove the explicit disabled override from the fixture only in this scope.
    with trace.use_trace(trace._DEFAULT):
        first = session_log.start_session(tmp_path / "one")
        assert trace.active_trace() is first.runtime_trace
        first.begin_turn("текст")
        with trace.span("FORMALIZER", run_id="run:1"):
            trace.emit("decision", status="RESOLVED")
        first_records = rows(first.runtime_trace.path)
        assert all(row["session_id"] == first.session_id for row in first_records)
        assert all(row["turn_id"] == first.current_turn_id() for row in first_records)
        second = session_log.start_session(tmp_path / "two")
        assert not first.runtime_trace.enabled
        assert second.runtime_trace.enabled
        assert trace.active_trace() is second.runtime_trace
        assert rows(second.runtime_trace.path) == []
        with trace.use_trace(None):
            assert not trace.enabled()
            trace.emit("disabled")
        trace.emit("enabled_again")
        assert [row["event"] for row in rows(second.runtime_trace.path)] == ["enabled_again"]


def test_explicit_sink_does_not_inherit_foreign_session_turn(tmp_path):
    session = session_log.start_session(tmp_path / "gui")
    session.begin_turn("GUI text")
    path = tmp_path / "headless.tsv"
    with trace.RuntimeTrace(path) as writer, trace.use_trace(writer):
        trace.emit("headless")
    assert rows(path)[0]["turn_id"] == ""


def test_cli_starts_session_at_configured_path(tmp_path, monkeypatch, capsys):
    import ah.cli as cli
    import ah.diagnostics as diagnostics

    monkeypatch.setattr(cli, "load_config", lambda path: SimpleNamespace(paths=SimpleNamespace(logs_dir=tmp_path)))
    monkeypatch.setattr(diagnostics, "score_m1_acceptance_bundle",
                        lambda path: SimpleNamespace(weighted_mean=1.0))
    monkeypatch.setattr(cli, "_jsonable", lambda value: {"weighted_mean": value.weighted_mean})
    assert cli.main(["m1-score", str(tmp_path)]) == 0
    assert session_log.active_session().runtime_trace.path.parent == tmp_path
    assert session_log.active_session().runtime_trace.enabled
    assert len(list(tmp_path.glob("session-*.tsv"))) == 1
