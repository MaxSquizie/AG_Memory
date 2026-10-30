"""Source-proved shared wording in distinct logical alternatives."""
from copy import deepcopy
from .structural_tasks import choose,source_set,licensed_in_scope as licensed
from .probe_prerequisites import accepted
from .source_collections import valid


def propose(domain,groups):
    state,release,selector,region,cfg=domain.state,domain.release,domain.selector,domain.region,domain.cfg
    # This is sharing of a single occurrence, not a textual rewrite or an
    # assertion that the alternative propositions occurred together.
    selected=choose(state,release,selector,region,cfg,'structural_shared_material',[
        {'candidate_id':'SHARED','label':'Some wording is expressed once but belongs inside EACH alternative proposition, such as a shared predicate with alternative participants'}],
        'Outer relation: '+domain.kind+'. Proposed alternatives: '+
        '; '.join('«'+' '.join(t.span for t in g)+'»' for g in groups)+'. '
        'Does wording inside one alternative also supply content inside every other alternative? '
        'Do not duplicate a modifier or operator that scopes over the alternative as a whole. '
        '0 means no such shared wording; ? means uncertain.',
        empty={'candidate_id':'NONE','label':'each alternative already has its own source wording'})
    if not selected:return None
    if selected[0]['candidate_id']=='NONE':return groups,None
    refs={t.token_id for g in groups for t in g}
    tokens=[t for t in domain.tokens if t.token_id in refs]
    begin=len(state.syntax_trace)
    material=source_set(state,release,selector,region,tokens,cfg,'structural_shared_source',
        'Select only source wording belonging INSIDE EVERY alternative. Keep distinct participant heads '
        'and branch-specific descriptions outside this set; preserve operators over the whole alternative outside it.',
        prerequisites=(accepted('structural_shared_material',selected),))
    if not material:return None
    receipt=next((r for r in reversed(state.syntax_trace[begin:]) if r.get('kind')=='SOURCE_SET'),None)
    if receipt is None or not valid(state,receipt):return None
    shared={t.token_id for t in material[0]}
    if any(not {t.token_id for t in g}-shared for g in groups):
        state.diag('SHARED_PROPOSITION_CONTENT_UNRESOLVED',region.region_id);return None
    expanded=[[t for t in domain.tokens if t.token_id in shared|{x.token_id for x in g}] for g in groups]
    witness={'scope_proof':selected[1],'collection':deepcopy(receipt)}
    return expanded,witness


def validate(state,groups,witness):
    counts={}
    for group in groups:
        refs=[t.token_id for t in group]
        if len(set(refs))!=len(refs):return False
        for ref in refs:counts[ref]=counts.get(ref,0)+1
    repeated={r for r,n in counts.items() if n>1}
    if witness is None:return not repeated
    if not licensed(state,witness['scope_proof']) or witness['scope_proof'].get('candidate_id')!='SHARED':return False
    collection=witness['collection']
    if not valid(state,collection):return False
    shared=set(collection['selected_refs'])
    return (shared==repeated and all(counts[r]==len(groups) for r in shared)
            and all({t.token_id for t in g}-shared for g in groups))
