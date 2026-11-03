"""Released source-window accounting; V2 zero means unlimited short probes."""
from bisect import bisect_right
from . import budget_tracing


def configure(state, selector, release):
    policy=release.entries('ProposalPolicy')[0].get('probe_budget')
    if not policy or state.observation.get('structural_contract')!='region_probes':
        budget_tracing.state_configured(state.budget, reason='window_policy_not_applied')
        return
    starts=[e.start for e in state.evidence]
    width=policy['window_tokens']
    windows=[starts[i] for i in range(0,len(starts),width)] or [0]
    state.budget.probe_window_starts=windows
    state.budget.probe_scope_limits={str(i):policy['calls_per_window'] for i in range(len(windows))}
    state.budget.llm_limit=sum(state.budget.probe_scope_limits.values())
    budget_tracing.state_windows_configured(state, policy, release)
    if hasattr(selector,'configure_probe_windows'):
        selector.configure_probe_windows(tuple(state.budget.probe_scope_limits),policy['tokens_per_window'])


def enter(state, selector, source_range):
    """Return to a window without replenishing its counters, even across stages."""
    starts=state.budget.probe_window_starts
    if not starts: return
    key=str(max(0,bisect_right(starts,source_range[0])-1))
    previous = state.budget.probe_scope_key
    state.budget.probe_scope_key=key
    budget_tracing.state_window_entered(state, previous, source_range)
    if hasattr(selector,'enter_probe_window'): selector.enter_probe_window(key)
