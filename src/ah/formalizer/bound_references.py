"""TD candidates from lexical binders accessible in the selected scope tree.

These are variable references, never entities or memory identities. A quote
boundary must not capture an outer variable implicitly.
"""
from .canonical_ledger import digest
from .composition_tree import forests,leaves


def candidates(state,tid):
    owners={f.frame_id for f in state.frames if tid in f.argument_token_refs
            and not f.semantic.get('structural_unresolved')}
    evidence={t.token_id:t for t in state.evidence}
    found={}
    def walk(node):
        if node.get('operator') in {'FORALL','EXISTS'} and len(node.get('operands',()))==2:
            variable,body=node['operands']
            number=variable.get('bound_var')
            refs=leaves(body)
            if owners & refs:
                for frame in state.frames:
                    if frame.frame_id not in refs:continue
                    for head,bound in frame.semantic.get('bound_arguments',{}).items():
                        if bound!=number or head not in evidence:continue
                        from .discourse_scopes import for_mention
                        a,b=for_mention(state,head),for_mention(state,tid)
                        if bool(a and a.get('quoted'))!=bool(b and b.get('quoted')):continue
                        key='bound:'+digest([state.source_uid,node,head])
                        from .coreference import mention_features
                        found[key]={'entity_ref':key,'reference_kind':'BOUND_VARIABLE',
                            'variable':number,'head_ref':head,'scope_ref':digest(node),
                            'owner_refs':sorted(owners & refs),'binding_ref':key,
                            'source_tag':[state.source_uid,state.interpretation_version],
                            'premise_support_refs':[],'features':mention_features(evidence[head]),
                            'label':'The quantified variable introduced by «'+evidence[head].span+'»; not an individual'}
        for child in node.get('operands',()):walk(child)
    for tree in forests(state.frames,state.logical_roots):walk(tree)
    return list(found.values())


def resolved(state,frame,tid):
    row=state.observation.get('bound_reference_bindings',{}).get(tid)
    if not row:return None
    decision=state.decisions.get(tid+'|reference')
    if (not decision or decision.outcome!='RESOLVED' or tuple(decision.selected)!=(row['entity_ref'],)
            or frame.frame_id not in row['owner_refs']):raise ValueError('BOUND_REFERENCE_UNGROUNDED')
    return row['variable']
