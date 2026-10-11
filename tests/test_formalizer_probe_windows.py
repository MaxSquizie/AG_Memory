"""Probe-window budgets are bounded, fair across source regions and replayable."""
import pytest
from ah.formalizer.provider_adapter import ProviderAdapter,BudgetSnapshot,BudgetExceeded,IntegrityError
from ah.formalizer.pipeline import MorphProvider
from test_formalizer_components import frontend,Choices
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from ah.core import AHCore


def test_more_than_eight_real_questions_can_span_windows():
    text=('Купались. '+'123 '*64+'. ')*12
    selector=Choices()
    st=frontend(text,MorphProvider(),selector)
    assert len(selector.prompts)>8
    assert all(n<=st.budget.probe_scope_limits[k] for k,n in st.budget.probe_scope_calls.items())
    assert len(st.budget.probe_scope_calls)>1
    # The same release without a policy keeps the old observation-wide limit.
    old=with_components(test_release(AHCore()),regional_probes=False)
    legacy=Choices(); st=frontend(text,MorphProvider(),legacy,old)
    assert len(legacy.prompts)<=8


def test_provider_scope_return_does_not_refill_and_replay_keeps_bytes():
    calls=[]
    adapter=ProviderAdapter('fixture',frozenset({'select'}),lambda prompt:calls.append(prompt) or '1',
        budget=BudgetSnapshot(token_limit=16))
    adapter.start_run('run');adapter.configure_probe_windows(('0','1'),16)
    adapter.enter_probe_window('0');assert adapter.select('a'*48,'run')=='1'
    with pytest.raises(BudgetExceeded):adapter.select('b'*48,'run')
    adapter.enter_probe_window('1');assert adapter.select('c'*48,'run')=='1'
    adapter.enter_probe_window('0')
    with pytest.raises(BudgetExceeded):adapter.select('d'*48,'run')
    assert len(calls)==2
    adapter.start_run('run')
    adapter.enter_probe_window('0');assert adapter.select('a'*48,'run')=='1'
    with pytest.raises(BudgetExceeded):adapter.select('b'*48,'run')
    adapter.enter_probe_window('1');assert adapter.select('c'*48,'run')=='1'
    assert len(calls)==2
    adapter.start_run('run');adapter.enter_probe_window('1')
    with pytest.raises(IntegrityError):adapter.select('a'*48,'run')


def test_oversized_received_bytes_exhaust_only_their_window_and_replay():
    calls=[]
    adapter=ProviderAdapter('fixture',frozenset({'select'}),lambda prompt:calls.append(prompt) or '1'*80,
        budget=BudgetSnapshot(token_limit=16))
    adapter.start_run('run');adapter.configure_probe_windows(('0','1'),16)
    for replay in (False,True):
        if replay: adapter.start_run('run')
        adapter.enter_probe_window('0')
        with pytest.raises(BudgetExceeded):adapter.select('a','run')
        with pytest.raises(BudgetExceeded):adapter.select('b','run')
        adapter.enter_probe_window('1')
        with pytest.raises(BudgetExceeded):adapter.select('c','run')
        assert len(calls)==2
