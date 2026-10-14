"""Lexical temporal components, before assignment to proposition slots.

Overlapping matches form one source component. The existing typed parser must
validate the entire component; interval containment alone grants no precedence.
"""
import re


def components(text, release, source_start=0):
    spans = sorted({(m.start(), m.end()) for rule in release.entries('TemporalRules')
                    for m in re.finditer(rule['pattern'], text, re.I)})
    groups = []
    for lo, hi in spans:
        if groups and lo < groups[-1][1]:
            groups[-1][1] = max(groups[-1][1], hi)
        else:
            groups.append([lo, hi])
    return [(source_start + lo, source_start + hi) for lo, hi in groups]


def symbolic_only(value, errors):
    """Unresolved civil precision is not an unresolved syntactic attachment."""
    return bool(value and value.get('expressions')) and set(errors) <= {
        'REFERENCE_UNKNOWN', 'REFERENCE_AMBIGUOUS'}
