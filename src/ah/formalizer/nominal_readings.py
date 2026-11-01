"""Typed boundary of a nominal phrase: external role and internal head reading."""
from .reading_decisions import selected as selected_reading_decision,UNSPECIFIED,condition_for
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph
from .state import MorphVariant


def clean(value):
    return {k:v for k,v in _morph(value).items() if k!='score'}


def variant(reading):
    return MorphVariant(**{**reading, 'cases':frozenset(reading['cases']),
        'features':frozenset(reading['features']), 'evidence_refs':tuple(reading.get('evidence_refs',()))})


def heads(token, quantities):
    group=quantities.get(token.token_id)
    if group:
        return [('HEAD',variant(m)) for m in group['internal_readings']]
    return [('EXTERNAL',v) for v in token.variants if v.pos in {'NOUN','NPRO'}]


def expand(options, token, quantities):
    group=quantities.get(token.token_id)
    if not group:return options
    return [{**o,'head_morph':clean(v),'quantity_ref':group['decision_ref']}
            for o in options for _,v in heads(token,quantities)
            if compatible_head(group,o['morph'],clean(v))]


def compatible_head(group,external,internal):
    pairs=group.get('internal_by_case')
    return pairs is None or any({k:v for k,v in raw.items() if k!='score'}==internal
        for case in external['cases'] for raw in pairs.get(case,()))


def description_heads(frame,*,state):
    readings=dict(frame.semantic['morph_bindings'])
    readings.update({d['head_ref']:d['morph'] for d in frame.semantic.get('nominal_dependencies',())})
    readings.update({t:r['selected_head_reading'] for t,r in frame.semantic.get('group_readings',{}).items()})
    if any(not available(state,tid,r) for tid,r in readings.items()):
        raise ValueError('MORPHOLOGY_DESCRIPTION_SOURCE_UNGROUNDED')
    return readings


def attach_groups(frame, quantities,*,state):
    sem=frame.semantic
    owned=set(sem['proposed_roles'])|set(sem.get('pp_readings',{}))
    owned.update(d['head_ref'] for d in sem.get('nominal_dependencies',()))
    inherited=sem.get('control_binding',{}).get('qualitative_groups',())
    from .morphology_provenance import group_live
    if any(not group_live(state,g,condition=condition_for(state,UNSPECIFIED)) for g in [*inherited,*quantities]):raise ValueError('MORPHOLOGY_GROUP_UNGROUNDED')
    groups={g['head_ref']:g for g in [*inherited,*quantities]}
    sem['qualitative_groups']=[{**g,**sem.get('group_readings',{}).get(g['head_ref'],{})}
                               for g in groups.values() if g['head_ref'] in owned]


def attested(state, token_ref, reading, _seen=frozenset(),*,condition=UNSPECIFIED):
    """Reconstruct a contextual reading from source and its resolved short probe."""
    condition=condition_for(state,condition)
    from .morphology_provenance import usable_condition
    proof_key=digest([token_ref,reading])
    if proof_key in _seen:return False
    seen=_seen|{proof_key}
    token=next((e for e in state.evidence if e.token_id==token_ref),None)
    if token is None:return False
    same=lambda v:digest(clean(v))==digest({k:v for k,v in reading.items() if k!='score'})
    from .morphology_provenance import original,live
    if reading.get('origin') not in {'CONTEXTUAL','RECOVERED'}:return original(state,token_ref,reading)
    from .morphology_domain import proposed, attested as nominal_use_attested
    if proposed(reading):return nominal_use_attested(state,token,reading,condition=condition)
    refs=reading.get('evidence_refs',())
    if reading.get('origin')=='RECOVERED' and refs:
        decision=state.decisions.get(refs[-1])
        return bool(selected_reading_decision(state,refs[-1],condition=condition) is not None and any(
            row.get('kind')=='AGREEMENT_RECOVERY' and usable_condition(state,row,condition) and live(state,row) and row['token_ref']==token_ref
            and row.get('selected') in decision.selected and digest(row.get('recovered_reading'))==digest({k:v for k,v in reading.items() if k!='score'})
            for row in state.syntax_trace))
    from .nominal_reference_groups import MARK
    if MARK in reading.get('features',()):
        for row in state.syntax_trace:
            if row.get('kind')!='NOMINAL_REFERENCE_GROUP' or not usable_condition(state,row,condition) or not live(state,row):continue
            for raw in row['internal_readings'].get(token_ref,()):
                expected=replace(variant(raw),features=frozenset(raw['features'])|{MARK},
                    origin='CONTEXTUAL',evidence_refs=(*raw.get('evidence_refs',()),row['decision_ref']))
                if same(expected):return True
        return False
    decision=state.decisions.get(refs[0]) if refs else None
    if not refs or selected_reading_decision(state,refs[0],condition=condition) is None:return False
    for row in state.syntax_trace:
        if (row.get('kind')!='QUANTITY_COMPOSITION' or not usable_condition(state,row,condition) or not live(state,row) or row['head_ref']!=token_ref or
                row['decision_ref']!=refs[0] or not decision.selected or 'OTHER' in decision.selected):continue
        for raw in row['internal_readings']:
            if not attested(state,token_ref,raw,seen,condition=condition):continue
            for case in row['external_cases']:
                if not compatible_head(row,{'cases':[case]},{k:v for k,v in raw.items() if k!='score'}):continue
                if same(MorphVariant(raw['lemma'],'NOUN',frozenset({case}),
                        features=frozenset({'NOUN','QUALITATIVE_GROUP'}),origin='CONTEXTUAL',
                        evidence_refs=(refs[0],row['marker_ref'],token_ref))):return True
    return False


def available(state,token_ref,reading,*,condition=UNSPECIFIED):
    """A candidate collection requires provenance, not a fabricated selection."""
    from .morphology_provenance import live,original
    from .morphology_domain import proposed,clean
    from .reading_producers import query_rows,use_scope,observe_query
    from .morphology_provenance import usable_condition
    condition=condition_for(state,condition)
    if proposed(reading):
        observe_query(state,token_ref,reading)
        return any(((row.get('kind')=='MORPHOLOGY_PROPOSAL' and clean(row.get('reading',{}))==clean(reading))
            or (row.get('kind')=='MORPHOLOGY_DOMAIN' and clean(reading) in [clean(v) for v in row.get('proposals',())])) and usable_condition(state,row,condition) and live(state,row)
            for row in query_rows(state,token_ref,use_scope(state)) if row.get('token_ref')==token_ref)
    return attested(state,token_ref,reading,condition=condition)
