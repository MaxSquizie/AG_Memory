"""Scope guards inspect only the tokens owned by the current area."""
import re
from .component_source import view


def connectives(state, release, region, tokens):
    raw = view(state, region, tokens)
    lo = region.source_range[0]
    return sorted({(lo+m.start(), lo+m.end()) for r in release.entries('ScopeLexicon')
        if r.get('operator') == 'AND' for m in re.finditer(r['pattern'], raw, re.I)})


def allowed(state, release, region, tokens, *, conjunction=False):
    from .regions import protected_intervals
    from .component_temporal import relative_adjuncts
    from .clock_ranges import consumed_scope_spans, scope_consumed
    raw = view(state, region, tokens)
    protected = protected_intervals(state.text)
    if any(a <= t.start < b for t in tokens for a, b in protected): return False
    if any(t.span in {'«', '»', '"', '(', ')', '?', ':'} for t in tokens): return False
    relative = {(r['resource_pattern'], r['operator'])
        for r in relative_adjuncts(state, release, region, tokens)}
    clocks = consumed_scope_spans(raw, state.observation, release)
    return not any((r['pattern'], r.get('operator')) not in relative
        and not (conjunction and r.get('operator') == 'AND')
        and not scope_consumed(r, m, clocks)
        for r in release.entries('ScopeLexicon') for m in re.finditer(r['pattern'], raw, re.I))
