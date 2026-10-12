"""Explain attachment to an assembled area using only established syntax."""


def question(state, frame, units, views, target, unit):
    evidence = {e.token_id: e for e in state.evidence}
    phrases = {u['entities'][0][0].token_id: u for u in units if u['entities']}
    edges = []
    for view in views:
        for edge in view['established_edges']:
            if edge not in edges:
                edges.append(edge)
    rows = []
    for edge in edges:
        parent = frame.predicate_token_ref if edge['parent_ref'] == 'EVENT' else edge['parent_ref']
        child = edge['child_ref']
        label = edge['kind']
        if label == 'ARGUMENT':
            label = frame.semantic.get('proposed_roles', {}).get(child, label)
            prep = frame.semantic.get('preposition_bindings', {}).get(child)
            if prep:
                label += ' via «' + evidence[prep['token_ref']].span + '»'
        elif label == 'SELECTED_PP':
            label = 'via «' + phrases[child]['token'].span + '»'
        rows.append('«' + evidence[parent].span + '» -- ' + label + ' --> «' + evidence[child].span + '»')
    return ('What does the prepositional phrase «' + unit['token'].span + ' ' + target['surface'] +
        '» describe? Choose its attachment scope in the assembled structure. '
        'EVENT means the complete predicate area with its established dependents; a nominal option means that inner entity only. '
        + ('Established links: ' + '; '.join(rows) + '. ' if rows else '') +
        'A place complement remains an entity: selecting its host does not identify it with the event or its landmark. '
        'Preserve the target subtree and all established links; do not infer a new relation sense or factuality from attachment alone. '
        'Keep distinct scopes when the wording does not discriminate.')
