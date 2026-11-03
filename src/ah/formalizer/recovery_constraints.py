"""Addressed recovery wording reads both presence and licensed provenance."""
from .canonical_ledger import digest
from .morphology_provenance import normalized


def matching_rows(state,token):
    recovery=token.lexical_recovery
    return [r for r in state.syntax_trace if r.get('kind')=='AGREEMENT_RECOVERY'
            and r.get('token_ref')==token.token_id
            and normalized(r.get('lexical_recovery'))==normalized(recovery)] if recovery else []


def inspect(state,token_refs,condition=None):
    from .morphology_provenance import _live,usable_condition
    tokens={t.token_id:t for t in state.evidence};result=[]
    for ref in token_refs:
        token=tokens.get(ref)
        if token is None:
            result.append({'token_ref':ref,'missing':True});continue
        recovery=token.lexical_recovery
        rows=matching_rows(state,token)
        result.append({'token_ref':ref,'surface':token.span,'recovery':recovery,
            'grounds':[[r,usable_condition(state,r,condition) and _live(state,r)] for r in rows]})
    return result


def signature(rows):return digest(normalized(rows))


def wording(state,token_refs,condition=None):
    rows=inspect(state,token_refs,condition)
    from .dispatch_evidence import observe
    observe(state,'RECOVERY_QUERY',{'token_refs':list(token_refs),'condition':condition,'signature':signature(rows)})
    return ['explicitly selected inflection reading «'+r['surface']+'» → «'+r['recovery']['surface']+'»; source text unchanged'
            for r in rows if r.get('recovery') and any(live for _,live in r['grounds'])]


def probe_refs(state,token_refs,condition=None):
    from .morphology_provenance import probe_refs as ancestry
    from .dispatch_evidence import evidence_probe_refs
    refs=evidence_probe_refs(state,'CONDITIONAL_PROOF',{'proof':None,'condition':condition})
    for token in state.evidence:
        if token.token_id not in token_refs:continue
        for row in matching_rows(state,token):refs.update(ancestry(state,row))
    return refs
