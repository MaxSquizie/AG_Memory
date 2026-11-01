"""The oracle subprocess owns its TSV sink; expected answers never feed it."""
import csv
import json

import pytest

from ah.diagnostics import runtime_trace
from tools import run_formalizer_v7_oracle as runner


def rows(path):
    with path.open(encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream,delimiter='\t',quoting=csv.QUOTE_NONE))


def test_list_does_not_create_a_trace_or_output_directory(tmp_path,monkeypatch,capsys):
    def forbidden(*args,**kwargs):
        raise AssertionError('--list must not open a writer or run cases')
    monkeypatch.setattr(runtime_trace,'RuntimeTrace',forbidden)
    monkeypatch.setattr(runner.adapter,'run_case',forbidden)
    output=tmp_path/'list-only'
    assert runner.main(['--case','A04','--out',str(output),'--list'])==0
    assert capsys.readouterr().out.strip()=='A04'
    assert not output.exists()


def test_nonempty_output_is_rejected_before_writer_creation(tmp_path,monkeypatch):
    output=tmp_path/'existing';output.mkdir()
    prior=output/'runtime.tsv';prior.write_text('prior\n',encoding='utf-8')
    def forbidden(*args,**kwargs):
        raise AssertionError('output validation must precede trace creation')
    monkeypatch.setattr(runtime_trace,'RuntimeTrace',forbidden)
    with pytest.raises(SystemExit) as failure:
        runner.main(['--case','A04','--out',str(output)])
    assert failure.value.code==2
    assert prior.read_text(encoding='utf-8')=='prior\n'


def test_case_correlation_has_actual_execution_only_and_preserves_progress(tmp_path,monkeypatch):
    execute=runner.adapter.run_case
    created=[]
    writer_class=runtime_trace.RuntimeTrace
    class TrackedWriter(writer_class):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            created.append(self)
    def observed_case(stimulus,fixtures):
        assert all('checks' not in step for step in stimulus['steps'])
        runtime_trace.emit('actual_case_call',source='independent_observer')
        return execute(stimulus,fixtures)
    monkeypatch.setattr(runtime_trace,'RuntimeTrace',TrackedWriter)
    monkeypatch.setattr(runner.adapter,'run_case',observed_case)
    output=tmp_path/'executed'
    assert runner.main(['--case','A04','--out',str(output)])==0
    assert len(created)==1 and not created[0].enabled
    recorded=rows(output/'runtime.tsv')
    assert recorded
    assert all(json.loads(row['data_json'])['case_id']=='A04' for row in recorded)
    assert all(json.loads(row['data_json'])['case_index']==1 for row in recorded)
    assert [row['event'] for row in recorded if row['stage']=='ORACLE_CASE']==[
        'span_started','actual_case_call','span_finished']
    assert recorded[-1]['status']=='EXECUTED'
    assert all('checks' not in json.loads(row['data_json']) for row in recorded)
    assert all(row['status']!='PASS' for row in recorded)
    progress=[json.loads(line) for line in (output/'progress.jsonl').read_text(encoding='utf-8').splitlines()]
    assert progress[0]['event']=='run_started'
    comparison=json.loads((output/'comparison.json').read_text(encoding='utf-8'))
    assert progress[-1]['event']=='run_finished' and progress[-1]['status']==comparison['status']
    assert progress[-1]['passed']==1 and progress[-1]['failed']==0


def test_runner_exception_closes_sink_and_restores_outer_context(tmp_path,monkeypatch):
    captured=[]
    expected=RuntimeError('execution setup failed')
    def broken(*args,**kwargs):
        captured.append(runtime_trace.active_trace())
        runner.progress.configure(tmp_path/'interrupted-progress.jsonl')
        raise expected
    monkeypatch.setattr(runner,'_run',broken)
    with runtime_trace.RuntimeTrace(tmp_path/'outer.tsv') as outer,runtime_trace.use_trace(outer):
        with pytest.raises(RuntimeError) as failed:
            runner.main(['--case','A04','--out',str(tmp_path/'failed')])
        assert failed.value is expected
        assert runtime_trace.active_trace() is outer and outer.enabled
    assert len(captured)==1 and not captured[0].enabled
    assert runner.progress._active is None
