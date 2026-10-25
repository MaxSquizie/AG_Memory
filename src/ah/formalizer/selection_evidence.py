"""A supported choice is evidence, not semantic validation or search closure."""


def selected_candidate(decision):
    if decision is None or decision.outcome not in (None, 'RESOLVED'):
        return None
    if len(decision.selected) != 1:
        return None
    candidate = decision.selected[0]
    if candidate not in decision.candidates:
        return None
    return candidate if any(g.value == candidate for g in decision.grounds) else None
