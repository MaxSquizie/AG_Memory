"""Strict P01 reading evidence, independent of legacy morphology-use adapters.

Historical callers supply the address and source snapshot explicitly. No ambient
session, mutable token.variants, or selected-decision-only fallback is consulted.
This evaluator is deliberately uncached until P04 installs dependency observation.
"""
from dataclasses import dataclass
import json
from .canonical_ledger import digest
from .composition_dispatcher import canonical
from .morphology_domain import clean


def freeze(value):
    return json.dumps(canonical(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


@dataclass(frozen=True)
class Address:
    source_uid: str
    source_revision: int
    interpretation_version: int
    text_digest: str
    region_ref: str
    occurrence_refs: tuple
    input_scope: str
    resource_version: str
    condition_json: str = 'null'
    stage: str = 'T2_TP'
    profile: str = 'READING_USE_V1'

    def __post_init__(self):
        if not isinstance(self.occurrence_refs,tuple):raise TypeError('IMMUTABLE_OCCURRENCES_REQUIRED')
        if not isinstance(self.condition_json,str):raise TypeError('FROZEN_CONDITION_REQUIRED')

    @property
    def condition(self):return json.loads(self.condition_json)


def address(state, *, source_revision, region_ref, occurrence_refs, input_scope,
            resource_version, condition=None):
    """Explicit adapter: no inference of historical scope from a current session."""
    if not region_ref or not input_scope or not resource_version or source_revision<1:
        raise ValueError('READING_ADDRESS_INCOMPLETE')
    refs=tuple(occurrence_refs)
    if not refs or len(refs)!=len(set(refs)):raise ValueError('READING_OCCURRENCES_INVALID')
    return Address(state.source_uid,source_revision,state.interpretation_version,
                   digest(state.text),region_ref,refs,input_scope,resource_version,freeze(condition))


@dataclass(frozen=True)
class SourceSnapshot:
    source_uid: str
    source_revision: int
    interpretation_version: int
    text_digest: str
    resource_version: str
    evidence_json: str


def source_snapshot(state, *, source_revision, resource_version, original_evidence):
    """Source producer supplies its immutable pre-overlay evidence, never consumers.

    Snapshot provenance belongs to the source adapter (P02/P03). Capturing the
    current consumer's variants is not a supported way to establish originals.
    """
    rows=[{'token_ref':t.token_id,'range':[t.start,t.end],
           'readings':[clean(v) for v in t.variants if v.origin=='DICTIONARY']}
          for t in original_evidence]
    if len(rows)!=len({r['token_ref'] for r in rows}):raise ValueError('DUPLICATE_ORIGINAL_OCCURRENCE')
    return SourceSnapshot(state.source_uid,source_revision,state.interpretation_version,
                          digest(state.text),resource_version,freeze(rows))


@dataclass(frozen=True)
class Witness:
    address: Address
    kind: str
    token_ref: str
    source_range: tuple
    reading_json: str
    use_json: str
    rule: str
    payload_json: str = 'null'
    proof_json: str = 'null'
    domain_json: str = 'null'
    parent_refs: tuple = ()
    basis_json: str = 'null'
    schema: str = 'READING_WITNESS_V1'

    def __post_init__(self):
        if not isinstance(self.address,Address):raise TypeError('TYPED_ADDRESS_REQUIRED')
        if not isinstance(self.source_range,tuple) or not isinstance(self.parent_refs,tuple):
            raise TypeError('IMMUTABLE_WITNESS_REFERENCES_REQUIRED')
        if not all(isinstance(v,str) for v in (self.reading_json,self.use_json,self.payload_json,self.proof_json,self.domain_json,self.basis_json)):
            raise TypeError('FROZEN_WITNESS_PAYLOAD_REQUIRED')

    @property
    def ref(self):return 'reading-witness:'+digest(canonical(self))


def witness(where,kind,token_ref,source_range,reading,use,*,rule,payload=None,
            proof=None,domain=None,parent_refs=(),basis=None):
    return Witness(where,kind,token_ref,tuple(source_range),freeze(clean(reading)),
                   freeze(use),rule,freeze(payload),freeze(proof),freeze(domain),tuple(parent_refs),freeze(basis))


@dataclass(frozen=True)
class Assessment:
    status: str
    reason: str
    dependencies: tuple = ()
    permission: str = 'NONE'

    @property
    def selected_use(self):return self.supported and self.permission=='SELECTED_USE'

    @property
    def supported(self):return self.status=='SUPPORTED'


def _basis(state,w,expected):
    a=w.address
    if w.schema!='READING_WITNESS_V1' or a.profile!='READING_USE_V1' or a.stage!='T2_TP':
        return Assessment('UNKNOWN','SCHEMA_OR_PROFILE_UNSUPPORTED')
    if (a.source_uid,a.source_revision,a.interpretation_version,a.text_digest,a.resource_version)!=(
            expected.source_uid,expected.source_revision,expected.interpretation_version,
            expected.text_digest,expected.resource_version):return Assessment('STALE','SOURCE_OR_RESOURCE_CHANGED')
    if (state.source_uid,state.interpretation_version,digest(state.text))!=(a.source_uid,a.interpretation_version,a.text_digest):
        return Assessment('STALE','HISTORICAL_STATE_MISMATCH')
    if a!=expected:return Assessment('CONFLICT','USE_ADDRESS_MISMATCH')
    if w.token_ref not in a.occurrence_refs:return Assessment('CONFLICT','OCCURRENCE_OUTSIDE_SCOPE')
    token=next((t for t in state.evidence if t.token_id==w.token_ref),None)
    if token is None:return Assessment('UNKNOWN','OCCURRENCE_UNAVAILABLE')
    if (token.start,token.end)!=w.source_range:return Assessment('CONFLICT','OCCURRENCE_RANGE_MISMATCH')
    if a.condition is not None:
        from .structural_conditions import historical
        if not historical(state,a.condition):return Assessment('STALE','CONDITION_NOT_LIVE')
    return None


def selection_basis(state,record):
    """Freeze actual task/domain area, not the caller's payload declaration."""
    key=record.get('domain_ref')
    domain=next((r for r in reversed(state.syntax_trace)
                 if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==key),None)
    pages=[] if domain is None else [r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK'
                                     and r.get('decision_ref') in domain.get('page_refs',())]
    probes={} if domain is None else {key:{field:state.component_probe_records.get(key,{}).get(field)
            for field in ('signature','dependency_signature','branch_condition')}
            for key in domain.get('page_refs',())}
    return json.loads(freeze({'domain':domain,'pages':pages,'probes':probes}))


def _domain_basis(state,w,record):
    if not isinstance(record,dict):return Assessment('UNKNOWN','DOMAIN_PROOF_MISSING')
    saved=json.loads(w.basis_json)
    if not isinstance(saved,dict) or not saved.get('domain'):return Assessment('UNKNOWN','TASK_BASIS_MISSING')
    current=selection_basis(state,record)
    if saved!=current:return Assessment('STALE','TASK_BASIS_CHANGED')
    domain=saved['domain'];basis=domain.get('execution_basis')
    if not isinstance(basis,dict):return Assessment('UNKNOWN','EXECUTION_BASIS_MISSING')
    from .structural_probe_inputs import source_signature
    if basis.get('source_basis')!=source_signature(state):return Assessment('STALE','TASK_SOURCE_CHANGED')
    if basis.get('context_version')!=state.context_version:return Assessment('STALE','TASK_CONTEXT_CHANGED')
    if basis.get('input_scope')!=w.address.input_scope:return Assessment('CONFLICT','TASK_INPUT_SCOPE_MISMATCH')
    if tuple(domain.get('token_refs',()))!=w.address.occurrence_refs:
        return Assessment('CONFLICT','TASK_OCCURRENCES_MISMATCH')
    lo,hi=domain.get('source_range',(None,None))
    if lo is None or not lo<=w.source_range[0]<=w.source_range[1]<=hi:
        return Assessment('CONFLICT','TASK_RANGE_MISMATCH')
    if not saved['pages'] or any(p.get('region_ref')!=w.address.region_ref
            or p.get('source_range')!=domain['source_range']
            or tuple(p.get('target_token_refs',()))!=w.address.occurrence_refs for p in saved['pages']):
        return Assessment('CONFLICT','TASK_REGION_MISMATCH')
    condition=domain.get('branch_condition')
    if {p.get('decision_ref') for p in saved['pages']}!=set(domain.get('page_refs',())):
        return Assessment('UNKNOWN','DOMAIN_PAGE_RECORD_MISSING')
    if any(p.get('branch_condition')!=condition or p.get('execution_basis')!=basis
           for p in saved['pages']):return Assessment('CONFLICT','PAGE_CONTEXT_MISMATCH')
    for key in domain.get('page_refs',()):
        probe=saved.get('probes',{}).get(key,{})
        if not probe.get('signature') or not probe.get('dependency_signature'):
            return Assessment('UNKNOWN','PAGE_PROBE_BASIS_MISSING')
        if probe.get('branch_condition')!=condition:return Assessment('CONFLICT','REPLAY_CONDITION_MISMATCH')
    if condition is not None:
        from .structural_conditions import allows
        if w.address.condition is None or not allows(state,condition,w.address.condition):
            return Assessment('CONFLICT','DOMAIN_CONDITION_MISMATCH')
    return None


def _selected(state,w,payload,proof):
    from .partial_readings import retired_refs
    if not isinstance(proof,dict):return Assessment('UNKNOWN','SELECTION_PROOF_MISSING')
    key=proof.get('decision_ref');decision=state.decisions.get(key)
    if key in retired_refs(state.syntax_trace):return Assessment('STALE','SELECTION_RETIRED')
    if decision is None:return Assessment('UNKNOWN','SELECTION_UNAVAILABLE')
    if not isinstance(payload,dict) or digest(payload)!=proof.get('payload_hash'):
        return Assessment('CONFLICT','SELECTED_PAYLOAD_MISMATCH')
    if payload.get('candidate_id')!=proof.get('candidate_id'):
        return Assessment('CONFLICT','SELECTED_CANDIDATE_MISMATCH')
    failed=_domain_basis(state,w,proof)
    if failed:return failed
    from .structural_tasks import _licensed
    if not _licensed(state,proof,_branch=w.address.condition):
        # A selected Decision without a task/domain proof is missing evidence,
        # not a proof that the source-language interpretation is impossible.
        rows=[r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'
              and r.get('task_ref')==proof.get('domain_ref')]
        return Assessment('STALE' if rows else 'UNKNOWN','SELECTION_NOT_LICENSED')
    return None


def _local(state,w,original,parents):
    reading=json.loads(w.reading_json);use=json.loads(w.use_json)
    payload=json.loads(w.payload_json);proof=json.loads(w.proof_json)
    if w.kind=='ORIGINAL':
        if w.rule!='SOURCE_DICTIONARY_V1' or use!={'kind':'AVAILABLE_READING'}:
            return Assessment('CONFLICT','ORIGINAL_IS_AVAILABILITY_NOT_SELECTION')
        if original is None:return Assessment('UNKNOWN','ORIGINAL_SNAPSHOT_MISSING')
        a=w.address
        if (original.source_uid,original.source_revision,original.interpretation_version,
            original.text_digest,original.resource_version)!=(a.source_uid,a.source_revision,
            a.interpretation_version,a.text_digest,a.resource_version):return Assessment('STALE','ORIGINAL_SNAPSHOT_CHANGED')
        rows=json.loads(original.evidence_json)
        supported=any(r['token_ref']==w.token_ref and tuple(r['range'])==w.source_range
                      and reading in r['readings'] for r in rows)
        return Assessment('SUPPORTED' if supported else 'CONFLICT','ORIGINAL_READING' if supported else 'NOT_AN_ORIGINAL_READING',permission='AVAILABLE_READING' if supported else 'NONE')
    if w.kind=='DERIVED' and w.rule=='IDENTITY_FROM_PARENT_V1':
        if len(w.parent_refs)!=1:return Assessment('UNKNOWN','ONE_PARENT_REQUIRED')
        parent=parents[w.parent_refs[0]]
        if (parent.address,parent.token_ref,parent.source_range,parent.reading_json,parent.use_json)!=(
            w.address,w.token_ref,w.source_range,w.reading_json,w.use_json):return Assessment('CONFLICT','IDENTITY_TRANSFORMATION_MISMATCH')
        return Assessment('SUPPORTED','PARENT_IDENTITY')
    if w.kind not in {'DERIVED','SELECTED_DOMAIN'}:return Assessment('UNKNOWN','WITNESS_KIND_UNSUPPORTED')
    if w.rule!='SELECTED_READING_USE_V1':return Assessment('UNKNOWN','TRANSFORMATION_ADAPTER_MISSING')
    if w.kind=='DERIVED':
        failed=_selected(state,w,payload,proof)
        if failed:return failed
    else:
        domain=json.loads(w.domain_json)
        if not isinstance(domain,dict):return Assessment('UNKNOWN','DOMAIN_PROOF_MISSING')
        failed=_domain_basis(state,w,domain)
        if failed:return failed
        from .validation_graph import validate
        from .partial_readings import retired_refs
        if domain.get('decision_ref') in retired_refs(state.syntax_trace):return Assessment('STALE','DOMAIN_RETIRED')
        if domain.get('decision_ref') not in state.decisions:return Assessment('UNKNOWN','DOMAIN_UNAVAILABLE')
        rows=[r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'
              and r.get('task_ref')==domain.get('domain_ref')]
        if not rows:return Assessment('UNKNOWN','DOMAIN_RECORD_MISSING')
        required=rows[-1].get('branch_condition')
        if required is not None:
            from .structural_conditions import allows
            if w.address.condition is None or not allows(state,required,w.address.condition):
                return Assessment('CONFLICT','DOMAIN_CONDITION_MISMATCH')
        if not validate('DOMAIN',state,domain):return Assessment('STALE','DOMAIN_NOT_LICENSED')
        if payload not in domain.get('alternatives',()):return Assessment('CONFLICT','PAYLOAD_OUTSIDE_DOMAIN')
        # Membership is not a final choice; callers must retain this type.
    binding={'token_ref':w.token_ref,'source_range':list(w.source_range),
             'reading':reading,'use':use,'address':canonical(w.address)}
    if not isinstance(payload,dict) or binding not in payload.get('reading_uses',()):
        return Assessment('CONFLICT','PAYLOAD_DOES_NOT_LICENSE_USE')
    return Assessment('SUPPORTED','DOMAIN_MEMBER_ONLY' if w.kind=='SELECTED_DOMAIN' else 'EXACT_SELECTED_USE',
                      permission='DOMAIN_MEMBERSHIP' if w.kind=='SELECTED_DOMAIN' else 'SELECTED_USE')


def historical(state,root,*,expected_address,original=None,parents=()):
    """Uncached bounded-stack evaluation, including every parent dependency.

    Returned dependency refs are an audit manifest, not installed cache watches.
    P04 must subscribe before using this API in a cached production consumer.
    """
    available={p.ref:p for p in parents};available[root.ref]=root
    results={};active=set();stack=[(root,False)];deps=set()
    try:
        while stack:
            w,leaving=stack.pop();key=w.ref
            if key in results:continue
            if not leaving:
                if key in active:return Assessment('UNKNOWN','PARENT_CYCLE',tuple(sorted(deps)))
                issue=_basis(state,w,expected_address)
                if issue:results[key]=issue;continue
                missing=set(w.parent_refs)-available.keys()
                if missing:results[key]=Assessment('UNKNOWN','PARENT_WITNESS_MISSING');continue
                active.add(key);deps.add(key)
                for record in (json.loads(w.proof_json),json.loads(w.domain_json)):
                    if isinstance(record,dict) and record.get('decision_ref'):deps.add(record['decision_ref'])
                stack.append((w,True));stack.extend((available[p],False) for p in reversed(w.parent_refs))
            else:
                active.remove(key)
                failed=next((results[p] for p in w.parent_refs if not results[p].supported),None)
                results[key]=failed or _local(state,w,original,available)
                if results[key].supported and w.rule=='IDENTITY_FROM_PARENT_V1':
                    from dataclasses import replace
                    results[key]=replace(results[key],permission=results[w.parent_refs[0]].permission)
        result=results[root.ref]
        return Assessment(result.status,result.reason,tuple(sorted(deps)),result.permission)
    except (KeyError,TypeError,ValueError,AttributeError):
        return Assessment('UNKNOWN','MALFORMED_WITNESS',tuple(sorted(deps)))


def validate(state,w,*,expected_address,original=None,parents=()):
    """Public unconditional boundary. No ambient branch can upgrade a witness."""
    try:
        if w.address.condition is not None or expected_address.condition is not None:
            return Assessment('CONFLICT','CONDITIONAL_WITNESS_AT_PUBLIC_BOUNDARY')
    except (ValueError,TypeError,AttributeError):
        return Assessment('UNKNOWN','MALFORMED_WITNESS')
    return historical(state,w,expected_address=expected_address,original=original,parents=parents)
