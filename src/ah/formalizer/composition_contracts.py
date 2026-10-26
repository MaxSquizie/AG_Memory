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
        from .composition_tree import roots,expression,leaves
        by_id={f.frame_id:f for f in frames}
        violations=[]
        for root in roots(frames):
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
                            if f and f.predicate_token_ref in self.token_refs:
                                violations.append({'owner_ref':fid,'role':role,'child_ref':child})
                    if frame.semantic.get('nominal_args'):
                        violations.append({'owner_ref':fid,'nominal_args':frame.semantic['nominal_args']})
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
    from .structural_tasks import licensed
    return [row for row in state.syntax_trace[begin:]
            if row.get('kind')=='COMPOSITION_OBLIGATION_FAILURE'
            and row.get('region_ref')==region.region_id
            and row.get('category') in {'HYPOTHESIS_CONFLICT','PARTITION_REJECTED'}
            and licensed(state,row.get('owner_proof'))]
