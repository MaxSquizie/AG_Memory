"""Boundary proposals, separate from child composition and ownership validation."""
from .partition_domain import PartitionProposal,ContentRequired


def inputs(domain):
    return domain.state,domain.release,domain.selector,domain.region,domain.tokens,domain.cfg,domain.kind


def unary(domain):
    from .relation_composition import RELATIONS
    state,release,selector,region,tokens,cfg,kind=inputs(domain)
    # Unary function material can be internal ("Ivan NOT arrived"). The
    # complement owns every remaining token, not just a following suffix.
    chosen=domain.span(tokens,'structural_introducer',
        kind+' ('+RELATIONS[kind]+'): select only the complete words expressing this outer relation. '
        'Include the full linking expression and any conjunction introducing its content. '
        'Exclude words belonging to a different nested relation, even when adjacent to the outer marker. '
        'Exclude the content proposition, its subject and predicate. Separating commas may be included; '
        'do not end early just because the first word already signals the relation.',record_remainder=True,marker=True)
    if not chosen:return None
    markers=chosen[0];marker_refs={t.token_id for t in markers}
    owned=[t for t in tokens if t.token_id not in marker_refs]
    if kind=='QUERY':
        markers.extend(t for t in owned if t.span=='?')
        owned=[t for t in owned if t.span!='?']
    # Separator ownership is confirmed with the entire partition below.
    # Quotes, parentheses and question marks are not generic separators.
    while owned and owned[0].span in {',','.'}:markers.append(owned.pop(0))
    while owned and owned[-1].span in {',','.'}:markers.append(owned.pop())
    # Empty content is an incomplete proposal, not a reason to skip ownership
    # checks: those checks can return the words swallowed by the marker.
    return PartitionProposal([owned])


def binary(domain):
    from .relation_composition import RELATIONS,function_ownership
    state,release,selector,region,tokens,cfg,kind=inputs(domain)
    contracts=(['condition being checked','outcome when that condition holds','outcome when that condition does not hold']
        if kind=='IF_ELSE' else ['condition being checked','outcome when that condition holds']
        if kind in {'IMPLIES','COUNTERFACTUAL'} else ['first proposition','second proposition'])
    def select(i,groups):
        contract=contracts[i]
        return domain.span(tokens,'structural_operand_'+str(i+1),
            kind+' ('+RELATIONS[kind]+'): select the complete '+contract+'. '+
            ('Include only what is being checked, not what happens as a result. ' if contract=='condition being checked' else
             'Include only this outcome, not the condition or the alternative outcome. ' if contract.startswith('outcome') else '')+
            'Exclude words linking the two outer parts. Keep any relations nested inside this part.'+
            (' Already selected: '+'; '.join(contracts[j]+': «'+' '.join(t.span for t in group)+'»' for j,group in enumerate(groups))+'.' if groups else ''),
            exclude=[t.token_id for g in groups for t in g],
            covered=[t.token_id for g in groups for t in g],remaining_parts=len(contracts)-i-1)
    from .partition_sequences import select_parts
    groups=select_parts(domain,contracts,select)
    if groups is None:return None
    groups=function_ownership(state,release,selector,region,cfg,kind,groups)
    if groups is None:return None
    return PartitionProposal(groups)


def content(domain):
    from .relation_composition import function_ownership,content_owner
    state,release,selector,region,tokens,cfg,kind=inputs(domain)
    if domain.owner_choice is None:
        domain.owner_choice=content_owner(state,release,selector,region,cfg,tokens)
    if not domain.owner_choice:return None
    def select(i,groups):
        owner_ref=domain.owner_choice[0]['owner_ref'] if domain.owner_choice else None
        owner=next((t for t in tokens if t.token_id==owner_ref),None)
        owner_note=(' Selected owner INSIDE TARGET: «'+owner.span+'» @'+str(owner.start)+
                    ('. Select only the content of THIS predicate. ' if i==0 else '. Select the parent part containing THIS predicate. ')+
                    'The owner remains in the parent part. '
                    'An ancestor’s content slot is the context of this whole task, not the content being selected here.' if owner else '')
        if i==0:
            return domain.span(tokens,'structural_content',
                'Select the complete dependent content: a proposition or an infinitive action description '
                'that is said, thought, requested, intended or otherwise taken as content. '
                'Exclude the parent predicate and its participants, the introducing conjunction, colon, and enclosing '
                'quotation marks. IF the content is quoted, start inside its quotes. '
                'Unquoted content needs no quotation marks. Retain any operators inside that content.'+owner_note,
                exclude=[owner_ref] if owner_ref else (),remaining_parts=1,remaining_contiguous=False)
        body=groups[0];body_ids={t.token_id for t in body}
        rest=[t for t in tokens if t.token_id not in body_ids]
        return domain.span(rest,'structural_parent',
            'Selected dependent content: «'+' '.join(t.span for t in body)+'». It has been removed from the choices below. '
            'Select the remaining parent text: the predicate that takes this content, its participants and other attached clauses. '
            'Boundary punctuation may stay; punctuation and connecting words are checked separately.'+owner_note,
            covered=body_ids,must_include=[owner_ref] if owner_ref else ())
    from .partition_sequences import select_parts
    groups=select_parts(domain,['dependent content','parent clause'],select)
    if groups is None:return None
    body,parent=groups
    owner=domain.owner_choice
    groups=function_ownership(state,release,selector,region,cfg,'CONTENT',[parent,body],
        protected_refs=domain.required|{owner[0]['owner_ref']},owner_ref=owner[0]['owner_ref'])
    if groups is None:return None
    parent,body=groups
    from .content_separators import separate
    parent,separators=separate(state,region,tokens,parent,body)
    if owner[0]['owner_ref'] not in {t.token_id for t in parent}:raise ValueError('CONTENT_OWNER_LOST')
    return PartitionProposal([parent,body],separators,owner_choice=owner)


def group(domain):
    state,release,selector,region,tokens,cfg,kind=inputs(domain)
    chosen=domain.span(tokens,'structural_group',
        'Select the complete parenthesized proposition, excluding the outer delimiters.')
    if not chosen:return None
    body=chosen[0];refs={t.token_id for t in body};markers=[t for t in tokens if t.token_id not in refs]
    if [t.span for t in markers if t.span not in {',','.'}]!=['(',')']:
        return None
    return PartitionProposal([body])


def content_checked(proposal,partition):
    if proposal.data:
        accepted=partition and not isinstance(partition,ContentRequired)
        proposal.data['status']='CONFIRMED' if accepted else 'UNCONFIRMED'
        if accepted:proposal.data['decision_ref']=partition[1]['decision_ref']
