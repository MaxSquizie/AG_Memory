"""General source relation tasks; spelling is not an admission requirement.

The model selects registered types and source boundaries through closed tasks.
Children use the same composer. Coverage and ordinary T3/T5 still validate every
selected structure; no child is returned as assertible after a parent failure.
"""
from dataclasses import replace
from .canonical_ledger import digest
from .composition_tree import InputSlot,expression,internalize,leaves
from .composition_children import select_child
from .structural_tasks import choose,span
import unicodedata


RELATIONS={
    'LEXICAL':'One lexical predication or nominal description; no logical operator or dependent clause inside the target. A separately supplied content slot may remain open',
    'NOT':'Negation of a proposition (not lexical opposition)',
    'POSSIBLE':'Possibility or ability; does not assert occurrence',
    'NECESSARY':'Necessity or obligation; preserve its scope',
    'AND':'Both propositions hold',
    'OR':'At least one proposition holds; inclusive alternative',
    'XOR':'Exactly one alternative holds',
    'IMPLIES':'Conditional: antecedent implies consequent; direction must be selected',
    'COUNTERFACTUAL':'Counterfactual condition and its consequence; not material implication',
    'BEFORE':'First event/proposition occurs before the second',
    'AFTER':'First event/proposition occurs after the second',
    'DURING':'First event/proposition occurs during the second',
    'CONTENT':'The target contains BOTH a parent predicate AND its dependent content: speech, thought, quotation or a controlled infinitive',
    'FORALL':'Universal nonnumeric quantification over a restricted variable',
    'EXISTS':'Existential nonnumeric quantification; no particular witness identity',
    'QUERY':'A question about content; no assertion of the content',
    'GROUP':'Parentheses group an entire proposition without changing its logical meaning',
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


def confirm_partition(state,release,selector,region,tokens,cfg,kind,groups,proof):
    refs=[t.token_id for group in groups for t in group]
    if len(refs)!=len(set(refs)) or not refs:return None
    used=set(refs);markers=[t for t in tokens if t.token_id not in used]
    parts=['«'+' '.join(t.span for t in g)+'»' for g in groups]
    punctuation=[t for t in markers if all(unicodedata.category(c).startswith('P') for c in t.span)]
    punctuation_refs={t.token_id for t in punctuation}
    links=[t for t in markers if t.token_id not in punctuation_refs]
    names=(['parent clause with a content slot', 'content filling that slot'] if kind=='CONTENT' else
           ['condition','consequence'] if kind in {'IMPLIES','COUNTERFACTUAL'} else
           ['restriction and whole body'] if kind in {'FORALL','EXISTS'} else
           ['part '+str(i+1) for i in range(len(groups))])
    description='; '.join(name+': '+part for name,part in zip(names,parts))
    option={'candidate_id':'PARTITION','relation':kind,'operands':[[t.token_id for t in g] for g in groups],
        'marker_refs':[t.token_id for t in markers],'relation_proof':proof,
        'label':'Proposed split — '+description+'; outer relation occurrences: '+
        (', '.join('«'+t.span+'» @'+str(t.start) for t in links) or 'none')+'; punctuation outside parts: «'+
        ' '.join(t.span for t in punctuation)+'»'}
    result=choose(state,release,selector,region,cfg,'structural_partition',[option],
        'Does this split preserve the source meaning as: '+RELATIONS[kind]+'? '
        'Each part keeps its participants, predicate and inner negation, modality or quantifiers. '
        +('The parent intentionally has an open content slot: the second part fills it. '
          'The parent does not need to be a complete standalone sentence. ' if kind=='CONTENT' else '')+
        'The parts are NOT asserted separately: the selected outer relation is applied to them. '
        'Moving words into that relation preserves their meaning; it does not delete negation, modality or a condition. '
        'The listed outer occurrences need not be adjacent and do not form a new sentence. '
        'Words expressing the outer relation must be outside the parts, '
        'including words introducing a condition or consequence. Punctuation may separate or enclose the parts. '
        'An implicit relation needs no linking word. Choose the split if it preserves the meaning; '
        'answer 0 if words have been assigned to the wrong part, and ? if the text does not decide.')
    return (markers,result[1]) if result else None


def function_ownership(state,release,selector,region,cfg,kind,groups):
    """Repeated/discontinuous function tokens can belong to the outer edge.

    Morphology proposes them; no particle spelling determines its scope.
    Negation inside a child must remain there unless the selected outer relation
    actually owns it. The full partition is confirmed afterwards.
    """
    while True:
        possible=[t for group in groups for t in group if any(v.pos in {'PRCL','CONJ'} for v in t.variants)]
        if not possible:return groups
        options=[{'candidate_id':'KEEP_ALL','label':'Keep all listed words inside their parts: '+
            ', '.join('«'+t.span+'» @'+str(t.start) for t in possible)}]
        options.extend({'candidate_id':t.token_id,'token_ref':t.token_id,
            'label':'Outer relation owns «'+t.span+'» @'+str(t.start)+'; remove this occurrence from its part'} for t in possible)
        selected=choose(state,release,selector,region,cfg,'structural_function_owner',options,
            kind+' ('+RELATIONS[kind]+'). Current parts: '+
            '; '.join(str(i+1)+': «'+' '.join(t.span for t in group)+'»' for i,group in enumerate(groups))+'. '+
            'Which listed word expresses the relation BETWEEN these parts? Select that occurrence to move it out of its part. '
            +('Words introducing the condition or consequence belong to this outer conditional relation. '
              if kind in {'IMPLIES','COUNTERFACTUAL'} else '')+
            'Keep all only if none expresses the outer relation. Negation, modality and quantification of an inner proposition stay inside it.')
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
    options=[{'candidate_id':k,'relation':k,'label':v} for k,v in RELATIONS.items()]
    if request and request.surrounding_relations:
        for option in options:
            if option['relation'] in request.surrounding_relations:
                option['label']='An additional relation INSIDE the target words: '+option['label']+'; not the already handled outer relation'
    supplied=''
    if request and request.pending_proposition_roles:
        supplied=('A dependent infinitive is supplied separately; other clauses still inside the target need analysis. ')
    if request and request.agreement_source:
        supplied+='An infinitive here can receive agreement from a separately handled governor. '
    result=choose(state,release,selector,region,cfg,'structural_relation',options,supplied+
        'Classify ONLY the target words. Context explains their meaning but is not part of this choice. '
        'Choose the outermost relation expressed inside the target; inner relations are handled later. '
        'Choose one lexical predication when these words describe one event or state, even if the surrounding text asks about it or makes it possible. '
        'The content option requires both the parent predicate and dependent content to be present in this text. '
        'Numeric quantification is deferred.')
    if not result:return block(state,region)
    option,proof=result;kind=option['relation']
    if kind=='LEXICAL':return None
    if kind=='CONTENT':return content(state,release,selector,region,tokens,cfg,request,compose_child,proof)
    if kind=='GROUP':
        chosen=span(state,release,selector,region,tokens,cfg,'structural_group',
            'Select the complete parenthesized proposition, excluding the outer delimiters.')
        if not chosen:return block(state,region)
        body=chosen[0];refs={t.token_id for t in body};markers=[t for t in tokens if t.token_id not in refs]
        if [t.span for t in markers if t.span not in {',','.'}]!=['(',')']:
            return block(state,region)
        if not confirm_partition(state,release,selector,region,tokens,cfg,kind,[body],proof):return block(state,region)
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
    if kind in BINARY:
        groups=[]
        for i in range(2):
            contract=('antecedent' if i==0 else 'consequent') if kind in {'IMPLIES','COUNTERFACTUAL'} else 'operand '+str(i+1)
            chosen=span(state,release,selector,region,tokens,cfg,'structural_operand_'+str(i+1),
                kind+' ('+RELATIONS[kind]+'): select the complete '+contract+'. '+
                ('This is the condition that is sufficient for the other part. ' if contract=='antecedent' else
                 'This is the consequence when the condition holds. ' if contract=='consequent' else '')+
                'Exclude words linking the two outer parts. Keep any relations nested inside this part.'+
                (' Already selected part 1: «'+' '.join(t.span for t in groups[0])+'».' if groups else ''),
                exclude=[t.token_id for g in groups for t in g])
            if not chosen:return block(state,region)
            groups.append(chosen[0])
        groups=function_ownership(state,release,selector,region,cfg,kind,groups)
        if groups is None:return block(state,region)
        partition=confirm_partition(state,release,selector,region,tokens,cfg,kind,groups,proof)
        if not partition:return block(state,region)
        frames=[];operands=[]
        for group in groups:
            slot=request or InputSlot()
            slot=replace(slot,surrounding_relations=(*slot.surrounding_relations,kind))
            children,root=child(state,release,selector,region,group,cfg,compose_child,slot,kind+' operand')
            frames.extend(children)
            if root is None:return block(state,region,frames)
            operands.append(expression(root))
        tree={'operator':kind,'operands':operands,'anchor_refs':[t.token_id for t in partition[0]]}
        attach_tree(frames,tree,region)
    else:
        # Unary function material can be internal ("Ivan NOT arrived"). The
        # complement owns every remaining token, not just a following suffix.
        chosen=span(state,release,selector,region,tokens,cfg,'structural_introducer',
            kind+' ('+RELATIONS[kind]+'): select only the complete words expressing this outer relation. '
            'Include the full linking expression and any conjunction introducing its content. '
            'Exclude words belonging to a different nested relation, even when adjacent to the outer marker. '
            'Exclude the content proposition, its subject and predicate. Separating commas may be included; '
            'do not end early just because the first word already signals the relation.')
        if not chosen:return block(state,region)
        markers=chosen[0];marker_refs={t.token_id for t in markers}
        owned=[t for t in tokens if t.token_id not in marker_refs]
        if kind=='QUERY':
            markers.extend(t for t in owned if t.span=='?')
            owned=[t for t in owned if t.span!='?']
        # Separator ownership is confirmed with the entire partition below.
        # Quotes, parentheses and question marks are not generic separators.
        while owned and owned[0].span in {',','.'}:markers.append(owned.pop(0))
        while owned and owned[-1].span in {',','.'}:markers.append(owned.pop())
        if not owned or not confirm_partition(state,release,selector,region,tokens,cfg,kind,[owned],proof):
            return block(state,region)
        slot=request or InputSlot()
        slot=replace(slot,surrounding_relations=(*slot.surrounding_relations,kind))
        governors=[t for t in markers if any(v.pos=='ADJS' or v.pos=='VERB' and v.mood!='imperative' for v in t.variants)]
        if kind in {'POSSIBLE','NECESSARY'} and governors:
            selected=choose(state,release,selector,region,cfg,'structural_governor',
                [{'candidate_id':'INDEPENDENT','label':'No agreement governor: the child has independent predication'},
                 *[{'candidate_id':t.token_id,'token_ref':t.token_id,'label':'Agreement/controller anchor «'+t.span+'»'} for t in governors]],
                'Modal words: «'+' '.join(t.span for t in markers)+'». Content: «'+' '.join(t.span for t in owned)+'». '
                'Does a modal word supply person, number or gender agreement for a dependent infinitive? '
                'If the content already has its own conjugated predicate, choose no governor. '
                'A dictionary reading alone does not establish this connection.')
            if not selected:return block(state,region)
            if selected[0]['candidate_id']!='INDEPENDENT':
                slot=replace(slot,agreement_source=next(t for t in governors if t.token_id==selected[0]['token_ref']))
        frames,root=child(state,release,selector,region,owned,cfg,compose_child,slot,kind+' content')
        if root is None:return block(state,region,frames)
        if kind=='QUERY':
            root.semantic['query_request']={'mode':'FORMULA'}
            root.semantic['query_intent_refs']=[proof['decision_ref']]
            tree=expression(root)
        else:
            tree={'operator':kind,'operands':[expression(root)],'anchor_refs':[t.token_id for t in markers]}
            attach_tree(frames,tree,region)
    state.syntax_trace.append({'kind':'STRUCTURAL_RELATION_COMPOSED','region_ref':region.region_id,
        'source_range':list(region.source_range),'relation':kind,'decision_ref':proof['decision_ref'],'tree':tree})
    return frames


def content(state,release,selector,region,tokens,cfg,request,compose_child,proof):
    chosen=span(state,release,selector,region,tokens,cfg,'structural_content',
        'Select the complete dependent proposition: what is said, thought, intended or otherwise taken as content. '
        'Exclude the parent predicate and its participants, the introducing conjunction, colon, and enclosing '
        'quotation marks. Start at the first word INSIDE quoted content; retain any operators inside that content.')
    if not chosen:return block(state,region)
    body=chosen[0];body_ids={t.token_id for t in body}
    rest=[t for t in tokens if t.token_id not in body_ids]
    parent_span=span(state,release,selector,region,rest,cfg,'structural_parent',
        'Select the lexical parent clause, including its participants but excluding the content introducer.')
    if not parent_span:return block(state,region)
    parent=parent_span[0]
    if not confirm_partition(state,release,selector,region,tokens,cfg,'CONTENT',[parent,body],proof):return block(state,region)
    owners=[t for t in parent if any(v.pos in {'VERB','INFN','ADJF','ADJS','NOUN'} for v in t.variants)]
    owner_choice=choose(state,release,selector,region,cfg,'structural_owner',
        [{'candidate_id':t.token_id,'owner_ref':t.token_id,'label':'Content belongs to predicate «'+t.span+'» @'+str(t.start)} for t in owners],
        'Select the lexical predicate which owns this proposition. Position alone is not evidence.')
    if not owner_choice:return block(state,region)
    owner=next(t for t in owners if t.token_id==owner_choice[0]['owner_ref'])
    role_registry={r['role_id'] for r in release.entries('RoleRegistry') if not r.get('allowed_argument_kinds') or set(r['allowed_argument_kinds']) & {'PROPOSITION','EVENT'}}
    senses={s['sense_id'] for s in release.entries('R-S') if any(s['lemma']==v.lemma and s['POS']==v.pos for v in owner.variants)}
    if senses:
        role_registry &= {r['role_id'] for v in release.entries('R-V') if v['sense_id'] in senses
                          for r in v['roles'] if set(r.get('argument_types',())) & {'PROPOSITION','EVENT'}}
    choices=[]
    from .probe_wording import proposition_role
    for role in sorted(role_registry):
        declared=[a for a in release.entries('AttitudeMap') if a['argument_role']==role and any(v.lemma==a['lemma'] for v in owner.variants)]
        attitudes=sorted({a['attitude'] for a in declared}) if declared else ['QUOTED','EMBEDDED','HYPOTHETICAL','UNKNOWN']
        for attitude in attitudes:
            choices.append({'candidate_id':role+':'+attitude,'owner_ref':owner.token_id,'role':role,'attitude':attitude,
                'label':role+' of «'+owner.span+'»; attitude='+attitude+
                '; '+proposition_role(role)+
                ' (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)'})
    link=choose(state,release,selector,region,cfg,'structural_content_role',choices,
        'Choose the content role AND attitude supported by this source. No canonical lexical identity is inferred.')
    if not link:return block(state,region)
    relation,license=link
    inherited=dict(request.pending_propositions or {}) if request else {}
    pending=dict(inherited)
    pending[owner.token_id]=frozenset(pending.get(owner.token_id,())) | {relation['role']}
    slot=replace(request or InputSlot(),pending_propositions=pending)
    parents=compose_child(parent,slot)
    candidates=[f for f in parents if f.predicate_token_ref==owner.token_id and not f.semantic.get('structural_unresolved')]
    if len(candidates)!=1:return block(state,region,parents)
    target=candidates[0]
    child_slot=InputSlot(inside_attitude=True,
        pending_propositions={ref:roles for ref,roles in inherited.items() if ref in body_ids})
    if any(v.pos=='INFN' for t in body for v in t.variants) and not any(v.pos=='VERB' for t in body for v in t.variants):
        from .control_arguments import controllers
        control=choose(state,release,selector,region,cfg,'structural_control',
            ({'candidate_id':'controller:'+digest(alias),'controller':alias,'label':'Same '+label+' of «'+owner.span+'»'} for alias,label in controllers(target)),
            'Choose the dependent infinitive subject/controller. Do not invent identity from proximity.')
        if not control:return block(state,region,parents)
        child_slot=replace(child_slot,controller=control[0]['controller'])
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
