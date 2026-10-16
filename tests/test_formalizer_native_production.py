"""Production routing against a signed isolated release; preview is a separate API."""
import pytest
from ah.formalizer.runtime_adapter import FormalizerAdapter
from ah.perception.contracts import PerceptionResult
from ah.core.journal import JournalChannel
from tools.formalizer_v7_test_support import native_fixture,NativeSelector,FixtureMorph

TEXT='У Ивана есть книга.'


def adapter(tmp_path,*,release=True):
    store,binding,resources=native_fixture(tmp_path/'journal.log')
    return FormalizerAdapter(NativeSelector(),morph=FixtureMorph(),store=store,binding=binding,
                             release=resources if release else None)


def test_signed_native_route_commits_and_survives_reopen(tmp_path):
    a=adapter(tmp_path)
    result=a.interpret(TEXT,raw_input={'source_id':'production-contract','revision':1})
    assert result.applied and result.terminal=='APPLIED' and result.committed_fragments
    assert isinstance(result.perception,PerceptionResult) and len(result.perception.assertions)==1
    records=JournalChannel(a._store._journal.path).scan_unprocessed()
    assert any(r['payload'].get('kind')=='BATCH' for r in records)
    assert a._store.ledger.f_visible()


def test_missing_release_and_unwired_paths_cannot_commit(tmp_path):
    a=adapter(tmp_path,release=False)
    result=a.interpret(TEXT,raw_input={'source_id':'missing-release','revision':1})
    assert not result.applied and 'RESOURCE_MISSING' in result.diagnostics
    assert not a._store.ledger.f_visible()
    with pytest.raises(RuntimeError):FormalizerAdapter(NativeSelector()).interpret(TEXT)


def test_perception_service_routes_to_signed_native_path(tmp_path):
    from ah.perception.llm_parser import LLMPerceptionService,LLMPerceptionSettings
    a=adapter(tmp_path)
    service=LLMPerceptionService(object(),LLMPerceptionSettings(),formalizer=a,native_commit=True)
    from ah.agent.interaction_context import InteractionContext
    result=service.perceive(TEXT,InteractionContext())
    assert isinstance(result,PerceptionResult) and result.assertions
    assert a._store.ledger.f_visible()
