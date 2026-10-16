"""Nonnumeric binders selected from source tasks, sharing the binder compiler."""
from .structural_tasks import choose
from .composition_tree import expression,InputSlot
from dataclasses import replace
from .composition_children import select_child
from .relation_composition import block,attach_tree
from .partition_domain import PartitionDomain,PartitionProposal


def compose(state,release,selector,region,tokens,cfg,request,compose_child,operator,proof):
    def propose(domain):
        marker=domain.span(tokens,'structural_quantifier',
            operator+': select the nonnumeric quantifier expression only, excluding its nominal restriction.',marker=True)
        if not marker:return None
        anchors=marker[0];ids={t.token_id for t in anchors};owned=[t for t in tokens if t.token_id not in ids]
        if any(v.pos=='NUMR' or 'Anum' in v.features for t in anchors for v in t.variants):
            state.diag('ARITHMETIC_QUANTIFIER_DEFERRED',region.region_id)
            return None
        binding=choose(state,release,selector,region,cfg,'quantifier_source_functions',[
            {'candidate_id':'SEPARATE','shared':False,'label':'The quantified mention is separate from these quantifier words'},
            *[{'candidate_id':t.token_id,'head_ref':t.token_id,'shared':True,
               'label':'«'+t.span+'» simultaneously expresses quantification and the bound participant'} for t in anchors]],
            'Does this quantifier contain its own participant mention? The same occurrence can have both functions.')
        if not binding:return None
        shared=()
        if binding[0]['shared']:
            head=next(t for t in anchors if t.token_id==binding[0]['head_ref'])
            owned=sorted([*owned,head],key=lambda t:t.start)
            shared=({'token_ref':head.token_id,'functions':['QUANTIFIER','BOUND_MENTION'],'proof':binding[1]},)
        return PartitionProposal([owned],{'anchors':anchors,'binding':binding},shared)
    selected=PartitionDomain(state,release,selector,region,tokens,cfg,operator,proof).resolve(propose)
    if not selected:return block(state,region)
    proposal,partition=selected;owned=proposal.groups[0];anchors=proposal.data['anchors']
    heads=[t for t in owned if any(v.pos in {'NOUN','NPRO'} for v in t.variants)]
    selected=proposal.data['binding'] if proposal.shared_functions else choose(state,release,selector,region,cfg,'structural_binder_head',
        [{'candidate_id':t.token_id,'head_ref':t.token_id,'label':'Bind the nominal «'+t.span+'» @'+str(t.start)} for t in heads],
        operator+': select the restricted variable mention. Its complete body remains indivisible; do not create a witness.')
    if not selected:return block(state,region)
    slot=request or InputSlot()
    slot=replace(slot,surrounding_relations=(*slot.surrounding_relations,operator))
    frames=compose_child(owned,slot)
    root=select_child(state,release,selector,region,frames,operator+' body','Preserve every use of the variable in this whole child.')
    if root is None:return block(state,region,frames)
    rule={'operator':operator,'attachment_kinds':['QUANTIFIED_NOMINAL'],'variable_sort':'ENTITY',
        'restriction_pattern':{'head_pos':['NOUN','NPRO'],'agreement':['cases','number','gender'],
            'role':cfg['subject_role'],'body_operator':'IMPLIES' if operator=='FORALL' else 'AND'},
        'structural_license':proof,'head_license':selected[1],'head_ref':selected[0]['head_ref'],
        'partition_license':partition[1]}
    from .quantifier_composition import bind
    bounds=(anchors[0].start,anchors[-1].end,operator)
    result=bind(state,release,selector,region,frames,{bounds:(anchors,rule)},cfg)
    if not result:return block(state,region,frames)
    item=next(iter(result.values()));restriction=item['restriction']
    # A description of the quantified nominal restricts the variable; it does
    # not strengthen the consequent. Its host remains that same bound variable.
    descriptions=[]
    for frame in frames:
        kept=[]
        for description in frame.semantic.get('nominal_args',()):
            if description.get('host_token_ref')==item['head_ref']:descriptions.append(description)
            else:kept.append(description)
        if 'nominal_args' in frame.semantic:frame.semantic['nominal_args']=kept
    restriction_tree={'frame_ref':restriction.frame_id}
    if descriptions:
        restriction_tree={'operator':'AND','operands':[restriction_tree,*[
            d.get('tree') or {'frame_ref':d['frame_ref']} for d in descriptions]]}
        restriction.semantic['quantifier_description_refs']=[d['frame_ref'] for d in descriptions]
    tree={'operator':operator,'anchor_refs':item['anchors'],'operands':[
        {'bound_var':item['variable'],'sort':'ENTITY'},
        {'operator':item['body_operator'],'operands':[restriction_tree,expression(root)]}]}
    frames.append(restriction);attach_tree(frames,tree,region)
    state.syntax_trace.append({'kind':'STRUCTURAL_RELATION_COMPOSED','relation':operator,'region_ref':region.region_id,
        'source_range':list(region.source_range),'decision_ref':proof['decision_ref'],'tree':tree})
    return frames
