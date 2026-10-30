"""General source relation tasks; spelling is not an admission requirement.

The model selects registered types and source boundaries through closed tasks.
Children use the same composer. Coverage and ordinary T3/T5 still validate every
selected structure; no child is returned as assertible after a parent failure.
"""
from dataclasses import replace
from .task_contracts import SelectionPurpose
from .canonical_ledger import digest
from .composition_tree import InputSlot,expression,internalize,leaves
from .composition_children import select_child
from .structural_tasks import choose,choose_open
from .partition_domain import ContentRequired,PartitionDomain
import unicodedata


RELATIONS={
    'LEXICAL':'One lexical predication or nominal description; no logical operator or dependent clause inside the target. A separately supplied content slot may remain open',
    'NOMINAL_DESCRIPTION':'A parent clause contains a nominal described by another clause or predicative phrase inside this target',
    'NOT':'Negation of a proposition (not lexical opposition)',
    'POSSIBLE':'Possibility or ability; does not assert occurrence',
    'NECESSARY':'Necessity or obligation; preserve its scope',
    'AND':'Conjunction: the text connects both propositions together within the current scope',
    'OR':'Inclusive alternative between propositions; the text permits both',
    'XOR':'Exclusive alternative: the text presents exactly one of the propositions',
    'IMPLIES':'One conditional rule: a condition implies a consequence; no alternative outcome for when that condition fails',
    'IF_ELSE':'Conditional with two branches: one outcome when a condition holds, another when that SAME condition does not hold',
    'COUNTERFACTUAL':'Counterfactual condition and its consequence; not material implication',
    'BEFORE':'First event/proposition occurs before the second',
    'AFTER':'First event/proposition occurs after the second',
    'DURING':'First event/proposition occurs during the second',
    'CONTENT':'The target contains BOTH a parent predicate AND its dependent content: speech, thought, quotation or a controlled infinitive',
    'FORALL':'Universal nonnumeric quantification over a restricted variable',
    'EXISTS':'Existential nonnumeric quantification; no particular witness identity',
    'QUERY':'A question about content; no assertion of the content',
    'GROUP':'Parentheses group an entire proposition without changing its logical meaning',
    'CONTENT_REFERENCE':'A predicate takes content referred to elsewhere: an explicit pointer to a proposition/action, or omitted but understood propositional content. The content itself is not expressed inside this target',
}
BINARY={'AND','OR','XOR','IMPLIES','COUNTERFACTUAL','BEFORE','AFTER','DURING'}


def block(state,region,frames=(),reason='STRUCTURAL_TASK_UNRESOLVED'):
    for frame in frames:frame.semantic['structural_unresolved']=True
    state.diag(reason,region.region_id)
    return list(frames)


def attach_tree(frames,tree,region):
    internalize(frames)
    reachable=leaves(tree)
    carrier=next(f for f in frames if f.frame_id==min(reachable))
    for frame in frames:
        frame.semantic['composition_group_root']=carrier.frame_id
        frame.semantic['coordination_owner']=region.region_id
    carrier.semantic.pop('component_child',None)
    carrier.semantic['component_scope_tree']=tree
    carrier.semantic['operator_forest']=[tree]
    return frames


def confirm_partition(state,release,selector,region,tokens,cfg,kind,groups,proof,*,shared_functions=(),owner_choice=None,marker_roles=None,shared_material=None):
    refs=[t.token_id for group in groups for t in group]
    from .shared_proposition_material import validate as shared_valid
    if shared_material is not None and kind not in {'OR','XOR'}:return None
    if not shared_valid(state,groups,shared_material):return None
    used=set(refs);markers=[t for t in tokens if t.token_id not in used]
    from .structural_tasks import licensed
    owner=None
    if kind=='CONTENT':
        if (not owner_choice or len(groups)!=2
                or not licensed(state,owner_choice[1],owner_ref=owner_choice[0]['owner_ref'])):return None
        owner=next((t for t in groups[0] if t.token_id==owner_choice[0]['owner_ref']),None)
        if owner is None:return None
    for shared in shared_functions:
        if (kind not in {'FORALL','EXISTS'} or shared.get('functions')!=['QUANTIFIER','BOUND_MENTION']
                or shared.get('token_ref') not in used
                or not licensed(state,shared.get('proof'),head_ref=shared['token_ref'],shared=True)):
            return None
    shared_refs={x['token_ref'] for x in shared_functions}
    parts=['«'+' '.join(t.span for t in g)+'»' for g in groups]
    punctuation=[t for t in markers if all(unicodedata.category(c).startswith('P') for c in t.span)]
    punctuation_refs={t.token_id for t in punctuation}
    links=[t for t in markers if t.token_id not in punctuation_refs]
    from .relation_markers import confirm
    checked=confirm(state,release,selector,region,cfg,kind,links,groups,established=marker_roles,owner=owner)
    if isinstance(checked,ContentRequired):return checked
    if not checked:return None
    # Coverage checks may refine an incomplete proposal. Completion still
    # requires nonempty operands; no probe can license an empty proposition.
    if not groups or any(not group for group in groups):return None
    names=(['parent clause with a content slot', 'content filling that slot'] if kind=='CONTENT' else
           ['condition','outcome when the condition holds','outcome when the condition does not hold'] if kind=='IF_ELSE' else
           ['condition','consequence'] if kind in {'IMPLIES','COUNTERFACTUAL'} else
           ['restriction and whole body'] if kind in {'FORALL','EXISTS'} else
           ['first proposition','second proposition'] if len(groups)==2 else
           ['content'] if len(groups)==1 else ['operand '+str(i+1) for i in range(len(groups))])
    description='; '.join(name+': '+part for name,part in zip(names,parts))
    if owner:
        description+='; selected content fills the slot of predicate «'+owner.span+'» @'+str(owner.start)+' in the parent'
    option={'candidate_id':'PARTITION','relation':kind,'operands':[[t.token_id for t in g] for g in groups],
        'marker_refs':[t.token_id for t in tokens if t in markers or t.token_id in shared_refs],
        'shared_functions':list(shared_functions),'shared_material':shared_material,'relation_proof':proof,
        'label':'Proposed split — apply '+RELATIONS[kind]+' to these parts: '+description+'; outer relation occurrences: '+
        (', '.join('«'+t.span+'» @'+str(t.start) for t in links) or 'none')+'; punctuation outside parts: «'+
        ' '.join(t.span for t in punctuation)+'»'}
    if owner:option.update(owner_ref=owner.token_id,owner_proof=owner_choice[1])
    from .composition_session import current
    runtime=current(state)
    proposal_signature=digest([state.source_uid,state.interpretation_version,region.region_id,
        runtime.input_signature() if runtime else None,runtime.context_signature() if runtime else None,
        state.text,[{k:v for k,v in option.items() if k not in {'relation_proof','owner_proof'}}]])
    prior=next((r for r in reversed(state.syntax_trace)
        if r.get('kind')=='COMPOSITION_OBLIGATION_FAILURE' and r.get('category')=='PARTITION_REJECTED'
        and r.get('witness',{}).get('proposal_signature')==proposal_signature),None)
    if prior:
        state.syntax_trace.append({'kind':'STRUCTURAL_REVISION_STALLED','region_ref':region.region_id,
            'source_range':list(region.source_range),'repeated_failure_ref':prior['failure_ref'],
            'reason':'SAME_REJECTED_PARTITION_WITH_UNCHANGED_INPUT'})
        state.diag('STRUCTURAL_REVISION_NO_PROGRESS',region.region_id)
        return None
    from .probe_prerequisites import from_proof
    shared_requirements=() if shared_material is None else tuple(from_proof(state,p) for p in
        [shared_material['scope_proof'],*shared_material['collection']['proofs']])
    validation_begin=len(state.syntax_trace)
    result=choose(state,release,selector,region,cfg,'structural_partition',[option],
        ('Shared source wording deliberately appears inside each alternative; this does not assert the alternatives jointly. ' if shared_material else '')+
        'Check ONE relation application: '+RELATIONS[kind]+'. '
        'Does the original source connect the quoted content parts by this relation, in the roles shown? '
        'The selected OUTER meaning applies to the parts; its own wording is outside them. '
        'Preserve their participants and any ADDITIONAL clauses, negation or modality nested inside a part. '
        'Do not require the selected outer operator to appear inside its own content as another operator. '
        'The parts are not independently asserted by this choice. '
        +('The parent has an intentionally open content slot filled by the other part; '
          'it need not be a standalone sentence and may contain other clauses. '
          'The established slot owner is «'+owner.span+'» @'+str(owner.start)+'. '
          'Check this content at that owner; other parent predicates keep their own clauses and scopes. ' if owner else '')+
        ('The marked quantifier occurrence also serves as the bound mention; preserve both functions. ' if shared_refs else '')+
        'Outer relation words may be separated in the source; they are not a new sentence. '
        'Choose the proposed application if it connects the right contents. '
        'Answer 0 if the relation or the assignment of its contents is wrong, or ? if the source does not decide. '
        'This choice does not resolve dictionary meanings or validate the internal parse of each part.',purpose=SelectionPurpose.CONFIRM,prerequisites=shared_requirements)
    if result is None:
        rejected=next((r for r in reversed(state.syntax_trace[validation_begin:])
            if r.get('kind')=='TASK_DOMAIN' and r.get('slot')=='structural_partition'
            and r.get('task_outcome')=='NONE_FIT_IN_ENUMERATED_GENERATOR'
            and r.get('enumeration_complete') is True
            and r.get('candidate_ids')==['PARTITION']
            and r.get('selection_purpose')==SelectionPurpose.CONFIRM.value),None)
        if rejected:
            from .composition_contracts import record_failure
            record_failure(state,region,'PARTITION_REJECTED',proof,
                'The proposed source split was explicitly rejected. This rejects this split only; '
                'it does not reject every split or the outer relation.',
                {'proposal':option,'rejection_domain_ref':rejected['task_ref'],
                 'proposal_signature':proposal_signature},search_complete=False)
    return ([t for t in tokens if t in markers or t.token_id in shared_refs],result[1]) if result else None


def function_ownership(state,release,selector,region,cfg,kind,groups,*,eligible_refs=None,protected_refs=(),owner_ref=None):
    """Repeated/discontinuous function tokens can belong to the outer edge.

    Source occurrences remain eligible unless addressed evidence protects them;
    no particle spelling determines its scope.
    Negation inside a child must remain there unless the selected outer relation
    actually owns it. The full partition is confirmed afterwards.
    """
    while True:
        possible=sorted([t for group in groups for t in group if
            (eligible_refs is None or t.token_id in eligible_refs) and
            t.token_id not in protected_refs and
            any(c.isalnum() for c in t.span)],key=lambda t:(t.start,t.end,t.token_id))
        if not possible:return groups
        options=[{'candidate_id':t.token_id,'token_ref':t.token_id,
            'label':'Outer relation owns «'+t.span+'» @'+str(t.start)+'; '+
                ('this is connective wording, not a predicate or participant, introducing «'+' '.join(x.span for x in groups[1])+'»; '
                 if kind=='CONTENT' else '')+'remove this occurrence from its part'} for t in possible]
        owner=next((t for g in groups for t in g if t.token_id==owner_ref),None)
        selected=choose(state,release,selector,region,cfg,'structural_function_owner',options,
            kind+' ('+RELATIONS[kind]+'). Current parts: '+
            '; '.join(str(i+1)+': «'+' '.join(t.span for t in group)+'»' for i,group in enumerate(groups))+'. '+
            'Which is the FIRST remaining occurrence in source order expressing this OUTER relation? '
            'Select that occurrence to move it out of its part. '
            +('Words introducing the condition or consequence belong to this outer conditional relation. '
              if kind in {'IMPLIES','IF_ELSE','COUNTERFACTUAL'} else '')+
            ('Part 1 is the parent, part 2 is its selected content. Parent predicate «'+(owner.span if owner else '')+'» is content and must remain. Select only grammatical connective wording introducing «'+
             ' '.join(t.span for t in groups[1])+'». Move only an introducer of THIS content; '
             'a conjunction introducing a different clause still inside the parent must stay there. ' if kind=='CONTENT' else '')+
            'Predicates and participants remain content. Negation, modality and quantification of an inner proposition stay inside it.',
            empty={'candidate_id':'KEEP_ALL','label':'keep all listed words in their parts'},purpose=SelectionPurpose.NEXT)
        if not selected:return None
        if selected[0]['candidate_id']=='KEEP_ALL':return groups
        tid=selected[0]['token_ref']
        groups=[[t for t in group if t.token_id!=tid] for group in groups]
        if any(not group for group in groups):return None


def child(state,release,selector,region,tokens,cfg,compose,request,contract):
    slot=request or InputSlot()
    # A nominal event is a typed option, not an inferred finite verb or a date.
    if not any(v.pos in {'VERB','INFN','ADJS'} for t in tokens for v in t.variants):
        heads=[t for t in tokens if any(v.pos in {'NOUN','NPRO'} for v in t.variants)]
        if heads:
            opts=[{'candidate_id':'PROPOSITION','label':'A complete clause: a predicate describes a participant, possibly without an explicit verb'}]
            opts.extend({'candidate_id':t.token_id,'head':t.token_id,'label':'Nominal event head «'+t.span+'» @'+str(t.start)} for t in heads)
            result=choose(state,release,selector,region,cfg,'structural_event_head',opts,
                contract+'. Target words: «'+' '.join(t.span for t in tokens)+'». '
                'Is this a complete clause, or a noun phrase naming an event/state? '
                'For a complete clause choose the complete-clause option; its predicate will be selected next. '
                'For an event noun phrase choose its head. A person or object name alone is not an event. '
                'If none fits, answer 0.')
            if not result:return [],None
            if result[0]['candidate_id']!='PROPOSITION':
                head=next(t for t in heads if t.token_id==result[0]['head'])
                slot=replace(slot,output_sort='EVENT_DESCRIPTION',head_ref=head.token_id,
                             allowed_cases=frozenset(c for v in head.variants for c in v.cases))
    frames=compose(tokens,slot)
    root=select_child(state,release,selector,region,frames,contract,
        'Preserve all selected source tokens and parent constraints; child content is not independently asserted.')
    return frames,root


def compose(state,release,selector,region,tokens,cfg,request,compose_child):
    if request and request.output_sort=='EVENT_DESCRIPTION':return None
    from .composition_session import current
    runtime=current(state)
    # Execution versions are not semantic inputs: unchanged probe evidence may
    # be replayed during clarification, then licensed in the new execution.
    options=[{'candidate_id':k,'relation':k,'label':v,'region_ref':region.region_id,
              'token_refs':[t.token_id for t in tokens],
              'source_uid':state.source_uid,
              'input_scope':runtime.input_signature() if runtime else None} for k,v in RELATIONS.items()]
    if request and request.surrounding_relations:
        for option in options:
            if option['relation'] in request.surrounding_relations:
                option['label']='An additional relation INSIDE the target words: '+option['label']+'; not the already handled outer relation'
    if request and request.pending_propositions:
        for option in options:
            if option['relation']=='CONTENT_REFERENCE':
                option['label']+='; only an ADDITIONAL content slot, not a child already assigned by the parent requirements'
    supplied=''
    if request and request.pending_proposition_roles:
        supplied=('A dependent infinitive is supplied separately; other clauses still inside the target need analysis. ')
    if request and request.agreement_source:
        supplied+='An infinitive here can receive agreement from a separately handled governor. '
    result=choose_open(state,release,selector,region,cfg,'structural_relation',options,supplied+
        'Classify ONLY the target words. Context explains their meaning but is not part of this choice. '
        'Choose the outermost relation expressed inside the target; inner relations are handled later. '
        'Choose one lexical predication only when TARGET itself contains no further outer relation; '
        'an outer relation already supplied by CONTEXT must not be selected again. '
        'The full content option requires both the parent predicate and dependent content to be present in this text. '
        'A reference to content or an omitted but understood content uses the content-reference option; an omitted participant alone does not. '
        'Numeric quantification is deferred.')
    if not result:return block(state,region)
    from .partial_readings import SupportedDomain
    if isinstance(result,SupportedDomain):
        from .structural_forest import retain
        retain(state,region,tokens,request,cfg,result)
        return block(state,region,reason='STRUCTURAL_FOREST_OPEN')
    option,proof=result;kind=option['relation']
    if kind=='LEXICAL':
        from .composition_contracts import LexicalRoute
        return LexicalRoute(region.region_id,tuple(t.token_id for t in tokens),proof,state.interpretation_version)
    if kind=='NOMINAL_DESCRIPTION':
        from .refinement_boundaries import general_boundary
        from .component_refinement import _compose_lexical_area
        boundary=general_boundary(state,release,selector,region,tokens,cfg)
        if not boundary:return block(state,region,reason='COMPONENT_REFINEMENT_UNRESOLVED')
        # The relation choice supplies applicability. An ordinary lexical area
        # never has to accept a relative-clause hypothesis from a word list.
        return _compose_lexical_area(state,release,selector,region,tokens,
            {**cfg,'_literal_relation':True,'_selected_refinement':boundary,'_skip_reuse':True},depth=cfg.get('_depth',0),request=request)
    if kind=='CONTENT_REFERENCE':
        from .content_reference_functions import compose as referenced_content
        return referenced_content(state,release,selector,region,tokens,cfg,request,compose_child,proof)
    if kind=='CONTENT':return content(state,release,selector,region,tokens,cfg,request,compose_child,proof)
    if kind=='GROUP':
        from .relation_partitions import group as propose
        selected=PartitionDomain(state,release,selector,region,tokens,cfg,kind,proof).resolve(propose)
        if not selected:return block(state,region)
        body=selected[0].groups[0]
        frames,root=child(state,release,selector,region,body,cfg,compose_child,
            replace(request or InputSlot(),inside_attitude=True),'GROUP content')
        if root is None:return block(state,region,frames)
        state.syntax_trace.append({'kind':'STRUCTURAL_RELATION_COMPOSED','relation':kind,
            'region_ref':region.region_id,'source_range':list(region.source_range),'tree':expression(root),
            'decision_ref':proof['decision_ref']})
        return frames
    if kind in {'FORALL','EXISTS'}:
        from .relation_quantifiers import compose as quantified
        return quantified(state,release,selector,region,tokens,cfg,request,compose_child,kind,proof)
    if kind in BINARY or kind=='IF_ELSE':
        from .relation_partitions import binary as propose
        selected=PartitionDomain(state,release,selector,region,tokens,cfg,kind,proof).resolve(propose)
        if not selected:return block(state,region)
        proposal,partition=selected;groups=proposal.groups
        frames=[];operands=[]
        for group in groups:
            slot=request or InputSlot()
            slot=replace(slot,surrounding_relations=(*slot.surrounding_relations,kind))
            children,root=child(state,release,selector,region,group,cfg,compose_child,slot,kind+' operand')
            frames.extend(children)
            if root is None:return block(state,region,frames)
            operands.append(expression(root))
        if kind=='IF_ELSE':
            from .conditional_composition import branch_tree
            tree=branch_tree(operands,[t.token_id for t in partition[0]])
        else:
            tree={'operator':kind,'operands':operands,'anchor_refs':[t.token_id for t in partition[0]]}
        attach_tree(frames,tree,region)
    else:
        from .relation_partitions import unary as propose
        selected=PartitionDomain(state,release,selector,region,tokens,cfg,kind,proof).resolve(propose)
        if not selected:return block(state,region)
        proposal,partition=selected;owned=proposal.groups[0];markers=partition[0]
        slot=request or InputSlot()
        slot=replace(slot,surrounding_relations=(*slot.surrounding_relations,kind))
        if kind in {'POSSIBLE','NECESSARY'}:
            slot=replace(slot,description_context=True)
        governors=[t for t in markers if any(v.pos=='ADJS' or v.pos=='VERB' and v.mood!='imperative' for v in t.variants)]
        if kind in {'POSSIBLE','NECESSARY'}:
            from .action_descriptions import passive_rule
            dependent=any(v.pos=='INFN' or passive_rule(v,cfg) for t in owned for v in t.variants)
            if not dependent:
                # No child reading can consume this agreement. Do not offer
                # an impossible control link or inherit one from an ancestor.
                governors=[];slot=replace(slot,agreement_source=None)
        if kind in {'POSSIBLE','NECESSARY'} and governors:
            from .component_policy import _morph
            from .probe_wording import reading as reading_text
            governor_options=[{'candidate_id':t.token_id+':'+digest(_morph(v)),
                'token_ref':t.token_id,'agreement_reading':_morph(v),
                'label':'Agreement/controller anchor «'+t.span+'»; personal agreement with a participant: '+reading_text(_morph(v))}
                for t in governors for v in t.variants if
                (v.pos=='ADJS' or v.pos=='VERB' and v.mood!='imperative') and not v.features & {'Impe','Prdx'}]
            selected=choose(state,release,selector,region,cfg,'structural_governor',
                [{'candidate_id':'INDEPENDENT','label':'No agreement governor: the child has independent predication'},
                 *governor_options],
                'Modal words: «'+' '.join(t.span for t in markers)+'». Content: «'+' '.join(t.span for t in owned)+'». '
                'Does a modal word supply person, number or gender agreement for a dependent infinitive? '
                'If the content already has its own conjugated predicate, choose no governor. '
                'Impersonal necessity or permission has no subject agreement: choose no governor. '
                'A passive predicate agrees with its patient, not its performer. '
                'A dictionary reading alone does not establish this connection.')
            if not selected:return block(state,region)
            if selected[0]['candidate_id']!='INDEPENDENT':
                source=next(t for t in governors if t.token_id==selected[0]['token_ref'])
                reading=selected[0]['agreement_reading']
                source=replace(source,variants=tuple(v for v in source.variants if _morph(v)==reading))
                slot=replace(slot,agreement_source=source)
            else:
                # Explicit independence supersedes an inherited agreement
                # source. Absence of a new governor task may still inherit it.
                slot=replace(slot,agreement_source=None)
        frames,root=child(state,release,selector,region,owned,cfg,compose_child,slot,kind+' content')
        if root is None:return block(state,region,frames)
        if kind=='QUERY':
            root.semantic['query_request']={'mode':'FORMULA'}
            root.semantic['query_intent_refs']=[proof['decision_ref']]
            root.semantic['query_anchor_refs']=[t.token_id for t in markers]
            tree=expression(root)
        else:
            tree={'operator':kind,'operands':[expression(root)],'anchor_refs':[t.token_id for t in markers]}
            attach_tree(frames,tree,region)
    state.syntax_trace.append({'kind':'STRUCTURAL_RELATION_COMPOSED','region_ref':region.region_id,
        'source_range':list(region.source_range),'relation':kind,'decision_ref':proof['decision_ref'],'tree':tree})
    return frames


def content_owner(state,release,selector,region,cfg,parent,body=None):
    """Select the slot's lexical owner before assigning connective material."""
    if body is None:
        return choose(state,release,selector,region,cfg,'structural_owner',
            [{'candidate_id':t.token_id,'owner_ref':t.token_id,
              'label':'Content belongs to predicate «'+t.span+'» @'+str(t.start)}
             for t in parent if any(c.isalnum() for c in t.span)],
            'Choose the predicate INSIDE TARGET whose dependent proposition or action description is also INSIDE TARGET. '
            'This selects the owner before selecting its content boundaries. '
            'A predicate outside TARGET, including the ancestor whose slot this target fills, is not this owner. '
            'Content already supplied separately by the parent requirements does not count as content inside TARGET. '
            'If several predicates have their own dependent contents here, select the FIRST such predicate in source order; '
            'the other constructions remain for recursive analysis. This is traversal order, not a claim that they lack content. '
            'Several numbers mean alternative owners at this first position, not all content-taking predicates. '
            'Do not select a participant or infer an unknown word’s lexical meaning.')
    body_text=' '.join(t.span for t in body)
    owners=[t for t in parent if any(c.isalnum() for c in t.span)]
    source_parts={'content_refs':[t.token_id for t in body],'parent_refs':[t.token_id for t in parent]}
    return choose(state,release,selector,region,cfg,'structural_owner',
        [{'candidate_id':t.token_id,'owner_ref':t.token_id,**source_parts,
          'label':'Content belongs to predicate «'+t.span+'» @'+str(t.start)} for t in owners],
        'Selected dependent content: «'+body_text+'». Remaining parent: «'+' '.join(t.span for t in parent)+'». '
        'Which predicate takes THIS content as what is said, thought, intended or otherwise described? '
        'Other parent predicates may own a different clause. Position alone is not evidence.')


def content(state,release,selector,region,tokens,cfg,request,compose_child,proof):
    from .relation_partitions import content as propose,content_checked
    selected=PartitionDomain(state,release,selector,region,tokens,cfg,'CONTENT',proof).resolve(propose,content_checked)
    if not selected:return block(state,region)
    proposal,partition=selected;parent,body=proposal.groups
    body_text=' '.join(t.span for t in body);body_ids={t.token_id for t in body}
    owner_choice=proposal.owner_choice
    from .structural_tasks import licensed
    if not owner_choice or not licensed(state,owner_choice[1],owner_ref=owner_choice[0]['owner_ref']):return block(state,region)
    owner=next(t for t in parent if t.token_id==owner_choice[0]['owner_ref'])
    source_parts={'content_refs':[t.token_id for t in body],'parent_refs':[t.token_id for t in parent]}
    link=content_role(state,release,selector,region,cfg,owner,parent,body_text,source_parts,
        reserved_roles=(request.pending_propositions or {}).get(owner.token_id,()) if request else ())
    if not link:return block(state,region)
    relation,license=link
    inherited=dict(request.pending_propositions or {}) if request else {}
    pending=dict(inherited)
    pending[owner.token_id]=frozenset(pending.get(owner.token_id,())) | {relation['role']}
    sources=dict(request.pending_proposition_sources or {}) if request else {}
    slot=replace(request or InputSlot(),pending_propositions=pending,
                 pending_proposition_sources={**sources,owner.token_id:tuple(t.token_id for t in body)})
    parents=compose_child(parent,slot)
    candidates=[f for f in parents if f.predicate_token_ref==owner.token_id and not f.semantic.get('structural_unresolved')]
    if len(candidates)!=1:return block(state,region,parents)
    target=candidates[0]
    child_slot=InputSlot(inside_attitude=True,description_context=True,
        surrounding_relations=(*(request.surrounding_relations if request else ()), 'CONTENT'),
        pending_propositions={ref:roles for ref,roles in inherited.items() if ref in body_ids},
        pending_proposition_sources={ref:refs for ref,refs in sources.items() if ref in body_ids})
    if any(v.pos=='INFN' for t in body for v in t.variants) and not any(v.pos=='VERB' for t in body for v in t.variants):
        from .control_arguments import controllers
        control=choose(state,release,selector,region,cfg,'structural_control',
            [{'candidate_id':'INDEPENDENT_CONTENT','independent_content':True,**source_parts,
              'label':'Independent content: no participant of «'+owner.span+'» is supplied as its infinitive subject'},
             *[{'candidate_id':'controller:'+digest(alias),'controller':alias,**source_parts,'label':'Same '+label+' of «'+owner.span+'»'}
               for alias,label in controllers(target)]],
            'Parent: «'+' '.join(t.span for t in parent)+'». Content: «'+body_text+'». '
            'Which participant, if any, is understood as the grammatical subject of THIS infinitive content? '
            'A passive subject receives the action; it need not perform it. '
            'A quoted or impersonal statement can have its own subject interpretation. '
            'Choose independent content if this connection is absent; the child will determine its own participants. '
            'Select a shared participant only when the source establishes that identity. Use ? if undecidable.')
        if not control:return block(state,region,parents)
        child_slot=replace(child_slot,controller=control[0].get('controller'),
                           independent_subject=bool(control[0].get('independent_content')))
    children,root=child(state,release,selector,region,body,cfg,compose_child,child_slot,'CONTENT of «'+owner.span+'»')
    frames=[*parents,*children]
    if root is None:return block(state,region,frames)
    target.semantic.setdefault('proposition_args',{})[relation['role']]={'tree':expression(root),
        'attitude':relation['attitude'],'holder_role':cfg['subject_role'],'structural_license':license}
    target.semantic['pending_proposition_roles']=[r for r in target.semantic.get('pending_proposition_roles',()) if r!=relation['role']]
    internalize(children,root,target)
    state.syntax_trace.append({'kind':'STRUCTURAL_RELATION_COMPOSED','relation':'CONTENT','region_ref':region.region_id,
        'source_range':list(region.source_range),'decision_ref':proof['decision_ref'],
        'owner_ref':target.frame_id,'content_ref':root.frame_id,'role':relation['role'],'attitude':relation['attitude']})
    return frames


def content_role(state,release,selector,region,cfg,owner,parent,body_text,source_parts,*,reserved_roles=(),prerequisites=()):
    role_registry={r['role_id'] for r in release.entries('RoleRegistry') if not r.get('allowed_argument_kinds') or set(r['allowed_argument_kinds']) & {'PROPOSITION','EVENT'}}
    senses={s['sense_id'] for s in release.entries('R-S') if any(s['lemma']==v.lemma and s['POS']==v.pos for v in owner.variants)}
    if senses:
        role_registry &= {r['role_id'] for v in release.entries('R-V') if v['sense_id'] in senses
                          for r in v['roles'] if set(r.get('argument_types',())) & {'PROPOSITION','EVENT'}}
    # These are addressed assignments for this predicate, not every possible
    # pending role and not assignments belonging to another predicate.
    reserved=sorted(set(reserved_roles));role_registry.difference_update(reserved)
    choices=[]
    from .probe_wording import proposition_role
    for role in sorted(role_registry):
        declared=[a for a in release.entries('AttitudeMap') if a['argument_role']==role and any(v.lemma==a['lemma'] for v in owner.variants)]
        attitudes=sorted({a['attitude'] for a in declared}) if declared else ['QUOTED','EMBEDDED','HYPOTHETICAL','UNKNOWN']
        for attitude in attitudes:
            choices.append({'candidate_id':role+':'+attitude,'owner_ref':owner.token_id,'role':role,'attitude':attitude,
                'reserved_roles':reserved,**source_parts,
                'label':role+' of «'+owner.span+'»; attitude='+attitude+
                '; '+proposition_role(role)})
    return choose(state,release,selector,region,cfg,'structural_content_role',choices,
        'Selected owner: «'+owner.span+'» @'+str(owner.start)+'. Selected dependent content: «'+body_text+'». '
        'Remaining parent: «'+' '.join(t.span for t in parent)+'». '
        +('Already assigned slots of THIS owner: '+', '.join(reserved)+'. Select a different slot; the assigned content is not being reconsidered. ' if reserved else '')+
        'Choose the role and status of THIS content for THIS predicate. '
        'QUOTED=reported; EMBEDDED=mental content; HYPOTHETICAL=intended/possible; UNKNOWN=unspecified. '
        'None asserts the child. No canonical lexical identity is inferred.',prerequisites=prerequisites)
