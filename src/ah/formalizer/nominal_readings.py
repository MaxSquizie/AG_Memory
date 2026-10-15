"""Typed boundary of a nominal phrase: external role and internal head reading."""
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


def description_heads(frame):
    readings=dict(frame.semantic['morph_bindings'])
    readings.update({d['head_ref']:d['morph'] for d in frame.semantic.get('nominal_dependencies',())})
    readings.update({t:r['selected_head_reading'] for t,r in frame.semantic.get('group_readings',{}).items()})
    return readings


def attach_groups(frame, quantities):
    sem=frame.semantic
    owned=set(sem['proposed_roles'])|set(sem.get('pp_readings',{}))
    owned.update(d['head_ref'] for d in sem.get('nominal_dependencies',()))
    inherited=sem.get('control_binding',{}).get('qualitative_groups',())
    groups={g['head_ref']:g for g in [*inherited,*quantities]}
    sem['qualitative_groups']=[{**g,**sem.get('group_readings',{}).get(g['head_ref'],{})}
                               for g in groups.values() if g['head_ref'] in owned]


def attested(state, token_ref, reading, _seen=frozenset()):
    """Reconstruct a contextual reading from source and its resolved short probe."""
    proof_key=digest([token_ref,reading])
    if proof_key in _seen:return False
    seen=_seen|{proof_key}
    token=next(e for e in state.evidence if e.token_id==token_ref)
    same=lambda v:digest(clean(v))==digest({k:v for k,v in reading.items() if k!='score'})
    if any(same(v) for v in token.variants):return True
    from .morphology_domain import proposed, attested as nominal_use_attested
    if proposed(reading):return nominal_use_attested(state,token,reading)
    refs=reading.get('evidence_refs',())
    if reading.get('origin')=='RECOVERED' and refs:
        decision=state.decisions.get(refs[-1])
        return bool(decision and decision.outcome=='RESOLVED' and any(
            row.get('kind')=='AGREEMENT_RECOVERY' and row['token_ref']==token_ref
            and row.get('selected') in decision.selected and row.get('recovered_reading')==clean(variant(reading))
            for row in state.syntax_trace))
    decision=state.decisions.get(refs[0]) if refs else None
    if not decision or decision.outcome!='RESOLVED':return False
    if list(decision.selected)==['NOMINAL'] and list(refs)==[refs[0],token_ref]:
        return any(same(replace(v,pos='NOUN',features=(v.features-{'ADJF'})|{'NOUN','SUBSTANTIVE'},
                   origin='CONTEXTUAL',evidence_refs=tuple(refs)))
                   for v in token.variants if v.pos=='ADJF' and not v.features & {'Anum','Apro'})
    for row in state.syntax_trace:
        if (row.get('kind')!='QUANTITY_COMPOSITION' or row['head_ref']!=token_ref or
                row['decision_ref']!=refs[0] or not decision.selected or 'OTHER' in decision.selected):continue
        for raw in row['internal_readings']:
            if not attested(state,token_ref,raw,seen):continue
            for case in row['external_cases']:
                if not compatible_head(row,{'cases':[case]},{k:v for k,v in raw.items() if k!='score'}):continue
                if same(MorphVariant(raw['lemma'],'NOUN',frozenset({case}),
                        features=frozenset({'NOUN','QUALITATIVE_GROUP'}),origin='CONTEXTUAL',
                        evidence_refs=(refs[0],row['marker_ref'],token_ref))):return True
    return False
