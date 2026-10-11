"""Released finite probe budgets keyed by source token windows, never wall time."""
from bisect import bisect_right


def configure(state, selector, release):
    policy=release.entries('ProposalPolicy')[0].get('probe_budget')
    if not policy or state.observation.get('structural_contract')!='region_probes': return
    starts=[e.start for e in state.evidence]
    width=policy['window_tokens']
    windows=[starts[i] for i in range(0,len(starts),width)] or [0]
    state.budget.probe_window_starts=windows
    state.budget.probe_scope_limits={str(i):policy['calls_per_window'] for i in range(len(windows))}
    state.budget.llm_limit=sum(state.budget.probe_scope_limits.values())
    if hasattr(selector,'configure_probe_windows'):
        selector.configure_probe_windows(tuple(state.budget.probe_scope_limits),policy['tokens_per_window'])


def enter(state, selector, source_range):
    """Return to a window without replenishing its counters, even across stages."""
    starts=state.budget.probe_window_starts
    if not starts: return
    key=str(max(0,bisect_right(starts,source_range[0])-1))
    state.budget.probe_scope_key=key
    if hasattr(selector,'enter_probe_window'): selector.enter_probe_window(key)
