"""Complete, occurrence-addressed reading domains; no implicit first choice."""
from copy import deepcopy
from dataclasses import dataclass
from .canonical_ledger import digest


@dataclass(frozen=True)
class SupportedDomain:
    values: tuple
    decision_ref: str
    domain_ref: str

    def record(self):
        return {'decision_ref':self.decision_ref,'domain_ref':self.domain_ref,
                'alternatives':deepcopy(list(self.values))}


def retired_refs(trace):
    return {ref for row in trace for ref in [
        row.get('decision_ref') if row.get('kind')=='DEPENDENCY_REJECTED' else
        row.get('previous_decision_ref') if row.get('kind')=='COMPOSITION_PROBE_SUPERSEDED' else None]
        if ref}


def valid_domain(state,record):
    retired=retired_refs(state.syntax_trace)
    if record.get('decision_ref') in retired:return False
    decision=state.decisions.get(record.get('decision_ref'))
    if decision is None or decision.search_complete is not True:return False
    values=record.get('alternatives',())
    if not values or len({v['candidate_id'] for v in values})!=len(values):return False
    ids={v['candidate_id'] for v in values}
    if set(decision.selected)!=ids:return False
    for row in reversed(state.syntax_trace):
        if row.get('kind')=='TASK_DOMAIN' and row.get('task_ref')==record.get('domain_ref'):
            return (row.get('search_complete') is True and row.get('source_complete') is True
                and not retired.intersection(row.get('page_refs',()))
                and ids<=set(row['supported_ids'])
                and all(row.get('supported_payloads',{}).get(v['candidate_id'])==digest(v) for v in values))
    return False


def retain(state,region,predicate,token,role,domain):
    record=domain.record()
    if not valid_domain(state,record):raise ValueError('READING_DOMAIN_UNGROUNDED')
    from .composition_session import current
    runtime=current(state)
    row={'kind':'PARTIAL_READING_DOMAIN','region_ref':region.region_id,
         'task_scope':runtime.input_signature() if runtime else None,
         'predicate_ref':predicate.token_id,'token_ref':token.token_id,'role':role,**record}
    if row not in state.syntax_trace:state.syntax_trace.append(row)
    return deepcopy(row)


def domains(state,region):
    from .composition_session import current
    runtime=current(state);scope=runtime.input_signature() if runtime else None
    found={}
    for row in state.syntax_trace:
        if row.get('kind')=='PARTIAL_READING_DOMAIN' and row['region_ref']==region.region_id and row['task_scope']==scope:
            found[(row['predicate_ref'],row['token_ref'])]=row
    return list(found.values())


@dataclass
class BindingDomain:
    alternatives: list
    reading_domains: list


def bundles(state,region,candidates):
    """Prove a common structural projection, preserving every whole reading.

    Only declared morphology locations may differ. Other fields, scopes and
    roles still participate in the existing exact component comparison.
    """
    records=domains(state,region)
    if len(candidates)<2 or not records or not all(valid_domain(state,r) for r in records):return None
    from .composition_equivalence import component_signature
    signatures=[];used=set()
    for bundle in candidates:
        copied=deepcopy(bundle)
        for frame in copied:
            if frame.semantic.get('structural_rejection'):return None
            frame.semantic.pop('reading_domains',None)
            frame.semantic['component_questions']=[q for q in frame.semantic.get('component_questions',())
                if not (q.get('kind')=='DEPENDENCY_READING_DOMAIN' and any(
                    r['predicate_ref']==frame.predicate_token_ref and r['token_ref']==q.get('token_ref') for r in records))]
            for row in records:
                if frame.predicate_token_ref!=row['predicate_ref']:continue
                tid=row['token_ref'];reading=frame.semantic.get('morph_bindings',{}).get(tid)
                if reading is None:continue
                from .morphology_domain import clean
                if clean(reading) not in [v['reading'] for v in row['alternatives']]:return None
                if frame.semantic.get('proposed_roles',{}).get(tid)!=row['role']:return None
                used.add((row['predicate_ref'],tid))
                frame.semantic['morph_bindings'][tid]={'reading_domain':row['domain_ref']}
        signatures.append(component_signature(copied))
    if None in signatures or len(set(signatures))!=1:return None
    if used!={(r['predicate_ref'],r['token_ref']) for r in records}:return None
    # Every supported reading needs a represented alternative; enumeration
    # cannot silently retain only a viable prefix after a producer fails.
    from .morphology_domain import clean
    for row in records:
        represented={digest(clean(f.semantic['morph_bindings'][row['token_ref']]))
            for bundle in candidates for f in bundle if f.predicate_token_ref==row['predicate_ref'] and row['token_ref'] in f.semantic.get('morph_bindings',{})}
        if represented!={digest(v['reading']) for v in row['alternatives']}:return None
    return deepcopy(records)
