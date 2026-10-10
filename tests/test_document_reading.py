from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import json

import pytest

from ah.agent import InteractionContext
from ah.model import Domain
from ah.config import IgnitionSettings, WorkspaceSettings, IntegrationSettings
from ah.documents import DocumentProcessor
from ah.documents.reading import read_document
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.formalizer.telemetry import observe
from ah.formalizer.provider_adapter import ProviderAdapter
from ah.ignition import IgnitionEngine
from ah.integration.service import IntegrationConfig, IntegrationService
from ah.perception.llm_parser import LLMPerceptionService, LLMPerceptionSettings
from tools.formalizer_v7_test_support import native_fixture, FixtureMorph, NativeSelector


def services(tmp_path):
    store, binding, release = native_fixture(tmp_path / 'journal')
    ignition = IgnitionEngine(store._core, IgnitionSettings(), WorkspaceSettings(.02))
    class ClosedSelector(NativeSelector):
        def propose(self, request): pytest.fail('document must not ask model to build a graph')
    adapter = FormalizerAdapter(ClosedSelector(), morph=FixtureMorph(), store=store,
                               binding=binding, release=release, ignition=ignition)
    perception = LLMPerceptionService(None, LLMPerceptionSettings(), formalizer=adapter, native_commit=True)
    user_ref = store._core.ref(store._core.add_entity(Domain.C).uid)
    svc = SimpleNamespace(core=store._core, ignition=ignition, perception=perception,
                          integration=IntegrationService(store._core, IntegrationConfig.from_settings(IntegrationSettings())),
                          operation_lock=RLock(), context=InteractionContext(user_ref=user_ref))
    svc.document_processor = lambda: DocumentProcessor(svc, max_chunk_chars=256)
    return svc, adapter


def test_native_document_exact_source_integer_revision_and_replay(tmp_path):
    svc, adapter = services(tmp_path)
    text = 'У Ивана есть книга.\r\n\r\n# источник сохраняется\r\n'
    source = tmp_path / 'book.txt'
    source.write_bytes(text.encode('utf-8'))
    events = []
    first = read_document(svc, source, tmp_path / 'first', progress=events.append)
    assert first['status'] == 'EXECUTED', first
    assert first['interpretation']['committed_fragments']
    assert first['semantic_correctness'] == 'NOT_EVALUATED'
    assert (tmp_path / 'first/source.txt').read_bytes() == source.read_bytes()
    snapshot = json.loads((tmp_path / 'first/interpretation.json').read_text())
    assert snapshot['state']['text'] == text
    observation = snapshot['state']['observation']
    assert observation['source_revision'] == 1
    assert observation['range'] == [0, len(text)]
    assert observation['batch_kind'] == 'DOCUMENT'
    assert observation['syntax_budget_scope'] == 'SOURCE_WINDOW_V1'
    assert all(v is None for v in observation['context_snapshot'].values())
    assert 'time_anchor' not in observation  # never the file's mtime
    assert first['observations'] == 1
    tick = svc.ignition.tick_index
    count = len(adapter._store.ledger.data['supports'])
    second = read_document(svc, source, tmp_path / 'second')
    assert second['status'] == 'EXECUTED', second
    assert svc.ignition.tick_index == tick
    assert len(adapter._store.ledger.data['supports']) == count
    assert {e['stage'] for e in events if e['event'] == 'stage'} >= {'T2_REGIONS', 'CONTEXT', 'T6_ADMISSION'}
    assert second['interpretation']['observation_id'] == first['interpretation']['observation_id']
    with pytest.raises(FileExistsError):
        read_document(svc, source, tmp_path / 'first')


def test_document_does_not_inherit_uploaders_clock_or_identity(tmp_path, monkeypatch):
    svc, adapter = services(tmp_path)
    svc.context.now_ref = svc.context.user_ref
    svc.context.self_ref = svc.context.user_ref
    def clock_must_not_be_read(*args):
        pytest.fail('chat clock is not the document timeline')
    monkeypatch.setattr('ah.temporal.exact_datetime_from_ref', clock_must_not_be_read)
    class Captured(Exception): pass
    seen = []
    def capture(text, *, raw_input):
        seen.append(raw_input)
        raise Captured()
    monkeypatch.setattr(adapter, 'interpret', capture)
    with pytest.raises(Captured):
        svc.perception.perceive('Я работаю.', svc.context, raw_input={'batch_kind': 'DOCUMENT'})
    assert all(v is None for v in seen[0]['context_snapshot'].values())
    assert 'time_anchor' not in seen[0]
    with pytest.raises(Captured):
        svc.perception.perceive('Я работаю.', svc.context, raw_input={
            'batch_kind': 'DOCUMENT', 'context_snapshot': {'user_ref': 'declared:narrator'},
            'time_anchor': '1900-01-01T00:00:00+00:00'})
    assert seen[1]['context_snapshot'] == {'user_ref': 'declared:narrator'}
    assert seen[1]['time_anchor'] == '1900-01-01T00:00:00+00:00'


def test_long_quote_is_not_split_into_independent_observations(tmp_path, monkeypatch):
    svc, adapter = services(tmp_path)
    text = 'Иван сказал: «' + ('Она ушла.\n\n' * 100) + '».'
    source = tmp_path / 'quote.txt'
    source.write_text(text)
    seen = []
    def stop(text, *args, **kw):
        seen.append((text, kw['raw_input']))
        raise ValueError('COMPUTATION_LIMIT')
    monkeypatch.setattr(svc.perception, 'perceive', stop)
    report = read_document(svc, source, tmp_path / 'out')
    assert seen == [(text, {'source_id': DocumentProcessor.source_id(text, 'quote'),
                           'source_revision': 1, 'batch_kind': 'DOCUMENT', 'range': [0, len(text)]})]
    assert report['status'] == 'STOPPED'
    assert report['error']['message'] == 'COMPUTATION_LIMIT'
    assert not adapter._store.ledger.data['supports']
    assert json.loads((tmp_path / 'out/report.json').read_text())['status'] == 'STOPPED'


def test_failed_runtime_start_still_leaves_source_and_diagnostic_report(tmp_path):
    source=tmp_path/'book.txt'; source.write_text('Текст.\r\n',newline='')
    def start(): raise ValueError('RESOURCE_MISSING: release')
    report=read_document(start,source,tmp_path/'out')
    assert report['status']=='STOPPED'
    assert report['error']['message']=='RESOURCE_MISSING: release'
    assert report['events']=={}
    assert (tmp_path/'out/source.txt').read_bytes()==source.read_bytes()
    assert json.loads((tmp_path/'out/report.json').read_text())==report


def test_streamed_structural_hash_matches_previous_canonical_bytes():
    from ah.formalizer.pipeline import t0
    from ah.formalizer.seal import structural_hash, _canonical_records, _jsonable
    import hashlib
    st=t0('Разные записи.')
    st.syntax_trace=[{'event':'check','step':i,'result':result} for i,result in enumerate([True,None,False])]
    records=[_jsonable(r) for r in _canonical_records(st)]
    records.sort(key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    expected=hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    assert structural_hash(st)==expected


def test_probe_progress_distinguishes_transport_and_replay_and_observer_failure():
    events = []
    calls = []
    provider = ProviderAdapter('local', frozenset({'select'}), lambda p: calls.append(p) or 'A')
    with observe(events.append):
        assert provider.select('short?', 'run', ordinal=1) == 'A'
        assert provider.select('short?', 'run', ordinal=1) == 'A'
    assert [e['event'] for e in events] == ['probe_started', 'probe_finished', 'probe_replayed']
    assert calls == ['short?']
    with observe(lambda e: (_ for _ in ()).throw(ValueError('bad GUI'))):
        assert provider.select('short?', 'run', ordinal=1) == 'A'


def test_read_windows_cannot_cut_delimiters_or_drop_their_dependencies():
    from ah.formalizer.pipeline import t0
    from ah.formalizer.regions import build_regions
    from ah.formalizer.syntax_rules import _windows
    from ah.formalizer.state import ClauseCandidate, ResourceProvenance
    text = 'Он сказал: «Она пришла.\n\nЯ (всё ещё) ждал». Потом ушёл.'
    state = t0(text)
    windows = _windows(state, 'SENTENCE')
    assert len(windows) == 2
    assert ''.join(e.span for e in state.evidence[windows[0][0]:windows[0][1]]).endswith('».')
    forest = build_regions(text, state.evidence, 'file')
    scopes = list(forest.dependencies)
    forest.attach_frames([])
    assert forest.dependencies == scopes
    assert len(scopes) == 2
    split = next(i for i, e in enumerate(state.evidence) if e.span == '.')
    state.clause_candidates = [ClauseCandidate('cut', ((0, split), (split+1, len(state.evidence)-1)), ResourceProvenance())]
    assert _windows(state, 'CLAUSE') == []


def test_document_panel_reports_actual_progress_and_no_gold_pass():
    from PySide6.QtWidgets import QApplication
    from ah.gui.document_panel import DocumentPanelWidget
    app = QApplication.instance() or QApplication([])
    panel = DocumentPanelWidget()
    panel.set_busy(True)
    panel.set_reading_progress({'event': 'reading', 'stage': 'CONTEXT', 'tokens_read': 128,
                               'tokens_total': 1000, 'probes_started': 3, 'probes_finished': 2})
    assert panel.progress.value() == 128 and panel.progress.maximum() == 1000
    assert '2/3' in panel.status.text()
    panel.set_reading_report({'source_path': 'book.txt', 'status': 'STOPPED',
        'elapsed_seconds': 2.0, 'output_dir': 'run', 'error': {'message': 'COMPUTATION_LIMIT'}})
    panel.set_busy(False)
    assert not panel.summary_button.isEnabled()
    assert 'NOT_EVALUATED' in panel.continuation_view.toPlainText()
    panel.close()
