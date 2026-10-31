"""Obligations at the relation/lexical boundary, with addressed failure evidence."""
from dataclasses import dataclass
from copy import deepcopy
from .canonical_ledger import digest


@dataclass(frozen=True)
class LexicalRoute:
    region_ref: str
    token_refs: tuple
    proof: dict
    interpretation_version: int

    def validate(self,state,region,tokens):
        from .structural_tasks import licensed
        from .composition_session import current
        runtime=current(state)
        if (state.interpretation_version!=self.interpretation_version or region.region_id!=self.region_ref or tuple(t.token_id for t in tokens)!=self.token_refs
                or not licensed(state,self.proof,relation='LEXICAL',region_ref=self.region_ref,
                                token_refs=list(self.token_refs),source_uid=state.source_uid,
                                input_scope=runtime.input_signature() if runtime else None)):
            raise ValueError('LEXICAL_ROUTE_UNGROUNDED')

    def accept(self,state,region,frames):
        """Check produced structures, never infer syntax from the number of verbs."""
        from .composition_tree import roots
        violations=lexical_violations(frames,self.token_refs)
        if violations:
            record_failure(state,region,'HYPOTHESIS_CONFLICT',self.proof,
                'A selected lexical-only route produced an internal relation.',violations,search_complete=False)
            state.diag('LEXICAL_ROUTE_CONFLICT',region.region_id)
            for f in frames:
                f.semantic['structural_unresolved']=True
                f.semantic['structural_rejection']='LEXICAL_ROUTE_CONFLICT'
                f.semantic.pop('partial_composition',None)
                f.semantic.pop('composition_domain',None)
            return False
        if roots(frames):
            state.syntax_trace.append({'kind':'LEXICAL_ROUTE_VALIDATED','region_ref':region.region_id,
                'token_refs':list(self.token_refs),'route_proof':deepcopy(self.proof),
                'frame_refs':[f.frame_id for f in frames]})
        return True


def record_failure(state,region,category,owner_proof,explanation,witness,*,search_complete):
    row={'kind':'COMPOSITION_OBLIGATION_FAILURE','region_ref':region.region_id,
         'source_range':list(region.source_range),'category':category,
         'owner_proof':deepcopy(owner_proof),'explanation':explanation,
         'witness':deepcopy(witness),'search_complete':search_complete}
    row['failure_ref']='composition-failure:'+digest(row)
    state.syntax_trace.append(row)
    return row


def conflicts(state,region,begin):
    from .partition_exclusions import failure_live
    from .structural_tasks import licensed
    return [row for row in state.syntax_trace[begin:]
            if row.get('kind')=='COMPOSITION_OBLIGATION_FAILURE'
            and row.get('region_ref')==region.region_id
            and row.get('category') in {'HYPOTHESIS_CONFLICT','PARTITION_REJECTED','PRODUCER_UNSUPPORTED'}
            and licensed(state,row.get('owner_proof'))
            and (row.get('category')!='PARTITION_REJECTED' or failure_live(state,row))
            and (row.get('category')!='PRODUCER_UNSUPPORTED'
                 or licensed(state,row.get('witness',{}).get('capability_proof')))]


def unsupported_route(state,region,cfg,producer,proof,explanation):
    """Expose a producer limitation to the existing addressed revision loop.

    A limitation does not falsify the reading or select a replacement relation.
    The caller must supply the actual selected capability question as evidence.
    """
    from .structural_tasks import licensed
    route=cfg.get('_lexical_route')
    if route is None or not licensed(state,proof):return None
    if route.region_ref!=region.region_id:return None
    if not licensed(state,route.proof):return None
    return record_failure(state,region,'PRODUCER_UNSUPPORTED',route.proof,explanation,
        {'producer':producer,'capability_proof':deepcopy(proof),
         'token_refs':list(route.token_refs),'interpretation_rejected':False},search_complete=False)


def lexical_violations(frames,token_refs,*,boundaries=None):
    """Pure lexical-route compatibility; no selection, exclusion or writes."""
    from .composition_tree import roots,expression,leaves
    by_id={f.frame_id:f for f in frames}
    violations=[]
    for root in (roots(frames) if boundaries is None else boundaries):
        tree=expression(root)
        pending=[tree]
        while pending:
            node=pending.pop()
            if 'choice_ref' in node:
                pending.extend(node.get('alternatives',()));continue
            if node.get('operator'):
                violations.append({'frame_ref':root.frame_id,'relation_tree':node});continue
            for fid in leaves(node):
                frame=by_id[fid]
                for role,slot in frame.semantic.get('proposition_args',{}).items():
                    from .composition_tree import content
                    for child in leaves(content(slot)):
                        f=by_id.get(child)
                        if f and f.predicate_token_ref in token_refs:
                            violations.append({'owner_ref':fid,'role':role,'child_ref':child})
                if frame.semantic.get('nominal_args'):
                    violations.append({'owner_ref':fid,'nominal_args':frame.semantic['nominal_args']})
    return violations


def slot_obligations(carrier,slot):
    """The same known/unknown case boundary used by CompositionSources.retain.

    This checks only output sort and the addressed head reading; other slot
    responsibilities remain explicit obligations at the caller.
    """
    conflicts=[];unknown=[]
    actual=carrier.semantic.get('output_sort','PROPOSITION')
    if actual!=slot.get('output_sort','PROPOSITION'):
        conflicts.append({'kind':'OUTPUT_SORT_CONFLICT','actual':actual,'required':slot.get('output_sort')})
    head=slot.get('head_ref');allowed=set(slot.get('allowed_cases') or ())
    if head:
        reading=carrier.semantic.get('morph_bindings',{}).get(head)
        cases=set(reading.get('cases') or ()) if reading else set()
        if reading is None or allowed and not cases:
            unknown.append({'kind':'HEAD_READING_UNKNOWN' if reading is None else 'HEAD_CASE_UNKNOWN','head_ref':head})
        elif allowed and not cases&allowed:
            conflicts.append({'kind':'HEAD_CASE_CONFLICT','head_ref':head,'actual':sorted(cases),'required':sorted(allowed)})
    return conflicts,unknown
