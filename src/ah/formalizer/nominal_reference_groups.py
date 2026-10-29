"""Source-local determiner groups. R1 readings and identity remain separate."""
from dataclasses import replace
from copy import deepcopy
from .canonical_ledger import digest
from .component_policy import _features, compatible, _morph
from .component_probe import _probe


MARK = 'NOMINAL_REFERENCE_FUNCTION'


def functional(token):
    return bool(token.variants) and all(MARK in v.features for v in token.variants)


def owned_function_refs(state,tokens):
    """Ownership is occurrence-local; a shared head remains a nominal bearer."""
    from .nominal_functions import rows
    refs={t.token_id for t in tokens if functional(t)}
    for row in rows(state,tokens,'REFERENCE'):
        refs.update(r for r in row['function_refs'] if r!=row['head_ref'])
    return refs


def validate(cfg):
    policy = cfg.get('nominal_references')
    if not policy:
        return
    if cfg.get('nominal_composition') != 'QUESTION_TREE_V1':
        raise ValueError('nominal references require question tree')
    for field in ('demonstratives', 'identity_modifiers'):
        rows = policy[field]
        if (len({(r['lemma'], r['POS']) for r in rows}) != len(rows) or
                len({r['rule_id'] for r in rows}) != len(rows) or
                any(r['lemma'] != r['lemma'].casefold() or not r['lemma'].strip() for r in rows)):
            raise ValueError('invalid nominal reference policy')


def project(state, release, selector, region, tokens, cfg):
    from .nominal_functions import prepared,rows
    from .function_inventory import current
    if current(state,'NOMINAL',tokens,cfg.get('_task_constraints'),require=True) is not None:
        groups=[];selected={};evidence={t.token_id:t for t in tokens}
        for source in rows(state,tokens,'REFERENCE'):
            lo,hi=source['source_range'];key=source['decision_ref']
            row={'head_ref':source['head_ref'],'anchor_refs':source['anchor_refs'],
                'function_refs':source['function_refs'],'source_range':[lo,hi],
                'raw':state.text[lo:hi],'identity_constraint':source['identity_constraint'],
                'decision_ref':key,'resource_sha256':release.sha256,'rule_ids':['SOURCE_FUNCTION_V1'],
                'internal_readings':{ref:[_morph(v) for v in evidence[ref].variants] for ref in source['function_refs']}}
            if source.get('shared_function'):
                from .nominal_functions import shared_nominal_readings
                selected[source['head_ref']]=shared_nominal_readings(state,evidence[source['head_ref']],source)
            groups.append(row)
            for ref in source['function_refs']:
                if ref==source['head_ref']:continue  # shared bearer remains a nominal, not a detachable determiner
                selected[ref]=tuple(replace(v,features=v.features|{MARK},origin='CONTEXTUAL',
                    evidence_refs=(*v.evidence_refs,key)) for v in evidence[ref].variants)
            state.syntax_trace.append({'kind':'NOMINAL_REFERENCE_GROUP',**row})
        return [replace(t,variants=selected[t.token_id]) if t.token_id in selected else t for t in tokens],groups
    policy = cfg.get('nominal_references')
    if not policy:
        return tokens, []
    state.require_structures_open('NOMINAL_REFERENCE_GROUP')
    groups, selected = [], {}
    def matches(token, rows):
        return [(r, v) for r in rows for v in token.variants
                if v.lemma == r['lemma'] and v.pos == r['POS']]
    for i, marker in enumerate(tokens):
        det = matches(marker, policy['demonstratives'])
        if not det:
            continue
        j = i+1
        identity = matches(tokens[j], policy['identity_modifiers']) if j < len(tokens) else []
        identity_token = tokens[j] if identity else None
        if identity:
            j += 1
        while j < len(tokens) and any(v.pos in {'ADJF','PRTF'} for v in tokens[j].variants):
            j += 1
        if j >= len(tokens):
            continue
        head = tokens[j]
        nouns = [v for v in head.variants if v.pos == 'NOUN']
        det = [(r,v) for r,v in det if any(v.cases & n.cases and
                compatible(_features(v), _features(n)) for n in nouns)]
        if not det:
            continue
        key = 'nominal-reference:'+digest([state.source_uid, marker.token_id, head.token_id])
        choice = None
        raw = state.text[marker.start:head.end]
        if region.source_range[1]-region.source_range[0] <= cfg['context_chars']:
            choice = _probe(state, selector, release, key, 'nominal_attachment', [
                {'candidate_id':'REFERENCE', 'label':raw+': determiner identifies an antecedent of the noun'+
                 ('; modifier requires the SAME antecedent' if identity else '')},
                {'candidate_id':'OTHER', 'label':'These words do not form this referential noun group; keep original analyses'}],
                state.text[slice(*region.source_range)], region.source_range,
                question='Choose the grammatical function of the whole noun group, not its antecedent. Do not infer identity from proximity.', target_refs=tuple(t.token_id for t in tokens if marker.start<=t.start<t.end<=head.end))
        if choice is None:
            state.diag('NOMINAL_REFERENCE_GROUP_UNRESOLVED',key)
            return None, []
        if choice != 'REFERENCE':
            continue  # Keep all original tokens; no ignored particle or forced group.
        refs = [t.token_id for t in tokens[i:j+1]]
        functions = [marker.token_id]+([identity_token.token_id] if identity_token else [])
        row = {'head_ref':head.token_id, 'anchor_refs':refs, 'function_refs':functions,
               'source_range':[marker.start,head.end], 'raw':raw,
               'identity_constraint':'SAME' if identity else 'CONTEXTUAL',
               'decision_ref':key, 'resource_sha256':release.sha256,
               'rule_ids':sorted({r['rule_id'] for r,v in det+identity}),
               'internal_readings':{marker.token_id:[_morph(v) for r,v in det],
                   **({identity_token.token_id:[_morph(v) for r,v in identity]} if identity else {})}}
        groups.append(row)
        for token, readings in [(marker, det)]+([(identity_token, identity)] if identity else []):
            selected[token.token_id] = tuple(replace(v, features=v.features|{MARK},
                origin='CONTEXTUAL', evidence_refs=(*v.evidence_refs,key)) for r,v in readings)
        state.syntax_trace.append({'kind':'NOMINAL_REFERENCE_GROUP', **row})
    return [replace(t, variants=selected[t.token_id]) if t.token_id in selected else t for t in tokens], groups


def attach(frames, groups):
    for frame in frames:
        for row in groups:
            head = row['head_ref']
            if head not in frame.argument_token_refs:
                continue
            unit = frame.semantic['lexical_units'].get(head)
            if unit is None:
                continue
            unit.update(anchor_refs=row['anchor_refs'], surface=row['raw'],
                        mention_ref='mention:'+digest(row['anchor_refs']),
                        reference_constraint=deepcopy(row))
