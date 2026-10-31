"""Run-local producer authority, independent of diagnostic observation packets.

An issuance proves which bytes the producer returned, not semantic correctness
or source closure. It is deliberately unavailable after serialized reload.
"""
from copy import deepcopy
from uuid import uuid4
from hashlib import sha256
from pickle import dumps
from .canonical_ledger import digest
from .composition_contracts import slot_obligations


def fingerprint(value):
    return sha256(dumps(value,protocol=5)).hexdigest()


class Issuer:
    def __init__(self):
        self.__prefix=uuid4().hex;self.__records={};self.__context_verifiers={}

    def __deepcopy__(self,memo):
        # Private validation views share authority, never mutable record values.
        return self

    def issue(self,source,condition,basis,invocation,reads,evidence,context_verifier=None):
        ref='lexical-issuance:'+self.__prefix+':'+str(len(self.__records))
        self.__records[ref]=deepcopy({'source_hash':fingerprint(source),
            'condition':condition,'basis':basis,'invocation':invocation,
            'reads':reads,'evidence':evidence})
        if context_verifier is not None:self.__context_verifiers[ref]=context_verifier
        return ref

    def check_context(self,ref):
        record=self.__records[ref];verify=self.__context_verifiers.get(ref)
        if verify is None or record["reads"].get("unmapped_contexts"):
            return {"status":"UNAVAILABLE","reason":"CONTEXT_RECEIPT_CAPABILITY_MISSING"}
        return verify(deepcopy(record["evidence"].get("context_receipts",[])))

    def get(self,ref):
        return deepcopy(self.__records.get(ref))


def authority(state):
    issuer=getattr(state,'_lexical_issuer',None)
    if issuer is None:issuer=Issuer();state._lexical_issuer=issuer
    return issuer


def inspect(state,result,source):
    """Historical origin and dependency freshness, outside execution scope.

    These checks are independent graph evaluations: external read validators
    may themselves enter the iterative proof graph. No recursive graph entry.
    Semantic compatibility and completeness remain separate obligations.
    """
    from .structural_conditions import historical,resolve
    from .structural_shells import evidence_state
    from .dispatch_evidence import probe_stamp,valid
    issuer=getattr(state,'_lexical_issuer',None)
    issued=issuer.get(source.get('issuance_ref')) if issuer else None
    def failure(reason):return {'status':'STALE_EVIDENCE','reason':reason,'write_eligible':False}
    if issued is None:return failure('PRODUCER_ISSUANCE_UNAVAILABLE')
    payload={k:v for k,v in source.items() if k!='issuance_ref'}
    if fingerprint(payload)!=issued['source_hash']:return failure('PRODUCER_OUTPUT_CHANGED')
    if result.get('condition')!=issued['condition']:return failure('PRODUCER_CONDITION_CHANGED')
    if not historical(state,issued['condition']):return failure('CONDITION_RETIRED')
    node=resolve(state,issued['condition']);invocation=issued['invocation']
    if node.basis!=issued['basis']:return failure('PRODUCER_BASIS_CHANGED')
    if (node.candidate['relation']!='LEXICAL' or node.hypothesis_ref!=result.get('hypothesis_ref')
            or node.forest['forest_ref']!=result.get('forest_ref')
            or result.get('token_refs')!=invocation['token_refs']
            or result.get('input_slot')!=invocation['input_slot']
            or result.get('source_range')!=invocation['source_range']):return failure('PRODUCER_ADDRESS_CHANGED')
    # Use trusted issued packet, not a caller-supplied replacement. Current
    # authority overrides captured values, including overlay-only retirements.
    local=evidence_state(state,{'evidence':issued['evidence']},read_only=True)
    if not issued['reads'].get('consistent',True):return failure('DEPENDENCY_REVISIONS_MIXED')
    for ref,stamp in issued['reads']['probes'].items():
        if stamp is None or probe_stamp(local,ref)!=stamp:return failure('PROBE_RETIRED_OR_CHANGED')
    for read in issued['reads']['external']:
        if valid(local,read['kind'],read['value'])!=read.get('expected',True):
            return failure('DEPENDENCY_CHANGED:'+read['kind'])
    if issued['evidence'].get('context_reads') or issued['reads'].get('contexts'):
        context=issuer.check_context(source['issuance_ref'])
        if context['status']=='STALE':return failure(context['reason'])
        if context['status']!='CURRENT':
            return {'status':'CONTEXT_REVALIDATION_PENDING','reason':context['reason'],'write_eligible':False}
    return {'status':'PRODUCED_EVIDENCE_CURRENT','reason':None,'write_eligible':False}


def assess(state,result,source):
    """Expose checked obligations without upgrading the producer's completeness."""
    origin=inspect(state,result,source)
    if origin['status']!='PRODUCED_EVIDENCE_CURRENT':return {**origin,'bundles':[]}
    from .state import FrameCandidate
    from .composition_contracts import lexical_violations
    from .composition_tree import expression,leaves,slots
    from .structural_shells import evidence_state
    issued=state._lexical_issuer.get(source['issuance_ref'])
    local=evidence_state(state,{'evidence':issued['evidence']},read_only=True)
    frames=[FrameCandidate(**deepcopy(row)) for row in source['frames']]
    by_id={f.frame_id:f for f in frames};outputs=[]
    for bundle in source['bundles']:
        refs=bundle['frame_refs'];root=bundle['root_ref'];unknown=[];conflicts=[]
        # Malformed producer output is an implementation obligation, never
        # evidence against the source-language hypothesis.
        if (len(by_id)!=len(frames) or len(set(refs))!=len(refs)
                or root not in refs or any(ref not in by_id for ref in refs)):
            outputs.append({'root_ref':root,'status':'INVALID_PRODUCER_OUTPUT',
                            'obligations':['BUNDLE_MEMBERSHIP_INVALID']});continue
        owned=[by_id[ref] for ref in refs]
        try:
            referenced=set().union(*(leaves(expression(f)) for f in owned),
                *(leaves(slot.tree) for f in owned for slot in slots(f)))
            if referenced-set(refs):
                unknown.append({'kind':'UNBOUND_FRAME_REFERENCES','refs':sorted(referenced-set(refs))})
            else:conflicts.extend(lexical_violations(owned,result['token_refs'],boundaries=[by_id[root]]))
        except (KeyError,TypeError,ValueError):
            unknown.append({'kind':'FRAME_STRUCTURE_UNESTABLISHED'})
        slot_conflicts,slot_unknown=slot_obligations(by_id[root],result.get('input_slot') or {})
        conflicts.extend(slot_conflicts);unknown.extend(slot_unknown)
        from .bundle_constraints import inspect as check_bundle
        from .structural_conditions import resolve
        node=resolve(local,result['condition'])
        semantic=check_bundle(local,node.forest['region_ref'],issued['basis']['input_scope'],
            result['token_refs'],owned,result['condition'])
        conflicts.extend(semantic['conflicts']);unknown.extend(semantic['unknowns'])
        # Explicit unfinished work cannot be discharged by a successful origin
        # check. Other typed-slot consumers have not yet all been connected.
        unknown.extend(deepcopy(source['obligations']))
        unknown.extend({'kind':kind} for kind in ('NOMINAL_RELATION_CONTRACT_PENDING',
            'OWNER_RELATIVE_CONTRACT_PENDING','CONTROL_CONTRACT_PENDING','TEMPORAL_CONTRACT_PENDING'))
        outputs.append({'root_ref':root,'status':'STALE_EVIDENCE' if semantic['stale'] else 'CONTRACT_CONFLICT' if conflicts else 'OPEN_REQUIREMENTS',
                        'conflicts':conflicts,'obligations':unknown,'semantic_requirements':semantic})
    return {**origin,'bundles':outputs}
