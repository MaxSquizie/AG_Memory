"""Addressed closed tasks with bounded candidate pages and explicit search state.

No graph generation, guessed words or writes. A NONE_FIT answer rejects only
the displayed page; an unknown answer leaves that task pending. The selected
local relation remains provisional until its children and source coverage close.
"""
from itertools import islice,chain
from .canonical_ledger import digest
from .component_probe import _probe


def enabled(release):
    return release.entries('ProposalPolicy')[0].get('composition',{}).get('structural_tasks')=='CLOSED_RELATIONS_V1'


def choose(state,release,selector,region,cfg,slot,options,question,*,empty=None):
    """Optional searches declare a typed completion outside the model domain.

    NONE_FIT closes only one page. EMPTY is licensed only after every page was
    examined and rejected; unknown, ambiguity and budget stops never close it.
    """
    if cfg.get('_task_constraints'):
        question+='\nEarlier attempt: '+cfg.get('_task_constraints_text',cfg['_task_constraints'])
    from .composition_session import current
    runtime=current(state)
    task_scope=runtime.input_signature() if runtime else None
    iterator=iter(options);page=0;previous=[];examined=0
    supported=[];pages=[];seen=set()
    limit=release.entries('ProposalPolicy')[0].get('max_rule_steps',20000)
    from .component_source import view,probe_context
    owned=set(region.token_refs)
    local=view(state,region,[t for t in state.evidence if t.token_id in owned])
    # Ownership limits the answer, not the evidence available for understanding it.
    context,target=probe_context(state,region,cfg,local)
    question=target+question
    if empty is not None:
        question+=' Optional search: select only matching positive options. If none matches, reject this page. After ALL pages have no match, the result is: '+empty['label']+'. Unknown is not an empty result.'
    def complete_empty():
        from .state import Decision,Ground
        key='task-empty:'+digest([region.region_id,task_scope,slot,question,sorted(seen),previous,empty])
        cid=empty['candidate_id']
        if cid in seen:raise ValueError('EMPTY_COMPLETION_IN_POSITIVE_DOMAIN')
        state.decisions[key]=Decision(slot,key,tuple(sorted(seen))+ (cid,),selected=(cid,),
            outcome='RESOLVED',search_complete=True,
            grounds=[Ground('D','complete optional domain has no supported occurrence',cid)])
        state.decisions[key].history.append({'kind':'EMPTY_DOMAIN','page_refs':list(previous),
            'positive_candidates':sorted(seen),'completion':empty})
        state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
            'status':'SELECTED','decision_ref':key,'enumeration_complete':True,
            'alternatives':[empty],'selected':cid,'task_outcome':'EMPTY','page_refs':list(previous)})
        from .component_probe_replay import supersede
        for rejected in previous:supersede(state,rejected,key)
        return empty,{'decision_ref':key,'candidate_id':cid,'domain_ref':key}
    if len(context)>cfg['context_chars']:
        state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',region.region_id)
        state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
            'slot':slot,'status':'BLOCKED','reason':'CONTEXT_LIMIT','examined':0})
        return None
    while True:
        values=list(islice(iterator,cfg['max_candidates']+1))
        has_more=len(values)>cfg['max_candidates']
        if has_more:
            iterator=chain(values[-1:],iterator);values=values[:-1]
        if not values:
            if empty is not None and not supported:return complete_empty()
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'EXHAUSTED','reason':'NO_REMAINING_CANDIDATES','examined':examined})
            return None
        examined+=len(values)
        choices=[{'candidate_id':v['candidate_id'],'label':v['label']} for v in values]
        key=region.region_id+'|task:'+digest([task_scope,slot,choices,question,page])
        fresh=0 if key in state.budget.task_candidate_pages else len(values)
        if examined>limit or state.budget.task_candidates_examined+fresh>limit:
            state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',region.region_id)
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'BLOCKED','reason':'SEARCH_LIMIT','examined':examined})
            return None
        ids=[v['candidate_id'] for v in values]
        if len(set(ids))!=len(ids) or seen.intersection(ids):
            raise ValueError('TASK_DUPLICATE_CANDIDATE')
        seen.update(ids)
        state.budget.task_candidate_pages[key]=len(values)
        state.budget.task_candidates_examined+=fresh
        selected=_probe(state,selector,release,key,slot,choices,context,region.source_range,
            question=question+' Select every supported option on THIS page; 0 rejects this page, ? means unknown.' )
        decision=state.decisions.get(key)
        outcome=('ONE_SELECTED' if decision and selected is not None and decision.outcome=='RESOLVED'
                 else decision.selector_outcome if decision else None)
        row={'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'source_range':list(region.source_range),
             'target_token_refs':list(region.token_refs),'context_policy':'TARGET_WITH_CONTEXT',
             'slot':slot,'decision_ref':key,'page':page,'examined':examined,
             'alternatives':values,'selected':selected,'status':'SELECTED' if selected else 'PENDING',
             'reason':outcome or 'PROBE_BLOCKED','enumeration_complete':False,
             'selection_provisional':True,'question':question}
        state.syntax_trace.append(row)
        pages.append(row)
        if decision is not None:decision.search_complete=False
        admissible=([selected] if selected else next((h['selected'] for h in reversed(getattr(decision,'history',()))
                    if isinstance(h,dict) and h.get('kind')=='CLOSED_PROBE_ALTERNATIVES'),[]))
        if outcome not in {'ONE_SELECTED','MULTIPLE_ADMISSIBLE','NONE_FIT'}:
            row['task_outcome']='UNKNOWN' if outcome=='INSUFFICIENT_CONTEXT' else 'RESOURCE_BLOCKED'
            return None
        supported.extend((v,key) for v in values if v['candidate_id'] in admissible)
        if outcome=='NONE_FIT':row['status']='REJECTED_PAGE';previous.append(key)
        if has_more:page+=1;continue
        from .task_contracts import SelectionReceipt
        receipt=SelectionReceipt(tuple(sorted(seen)),tuple(sorted(v['candidate_id'] for v,_ in supported)),True)
        domain_ref='task-domain:'+digest([region.region_id,task_scope,slot,question,receipt.candidates])
        state.syntax_trace.append({'kind':'TASK_DOMAIN','task_ref':domain_ref,'level':'T2_TP',
            'slot':slot,'source_range':list(region.source_range),'token_refs':list(region.token_refs),
            'page_refs':[p['decision_ref'] for p in pages],**receipt.record()})
        from .clarifications import choice
        explicit=choice(state,domain_ref,receipt.supported) if supported else None
        if explicit is not None:
            from .state import Decision,Ground
            value=next(v for v,_ in supported if v['candidate_id']==explicit)
            state.decisions[domain_ref]=Decision(slot,domain_ref,receipt.candidates,selected=(explicit,),
                outcome='RESOLVED',search_complete=True,grounds=[Ground('C','explicit clarification of the complete domain',explicit)])
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
                'status':'SELECTED','decision_ref':domain_ref,'enumeration_complete':True,
                'alternatives':[v for v,_ in supported],'selected':explicit,'domain_ref':domain_ref})
            from .component_probe_replay import supersede
            for p in pages:supersede(state,p['decision_ref'],domain_ref)
            return value,{'decision_ref':domain_ref,'candidate_id':explicit,'domain_ref':domain_ref}
        if len(supported)==1:
            value,winner=supported[0]
            selected_row=next(p for p in pages if p['decision_ref']==winner)
            selected_row.update(enumeration_complete=True,domain_ref=domain_ref,task_outcome='SUPPORTED')
            state.decisions[winner].search_complete=True
            if winner in state.component_probe_records:
                state.component_probe_records[winner]['decision']['search_complete']=True
            from .component_probe_replay import supersede
            for rejected in previous:supersede(state,rejected,winner)
            return value,{'decision_ref':winner,'candidate_id':value['candidate_id'],'domain_ref':domain_ref}
        if supported:
            from .state import Decision
            joint=Decision(slot,domain_ref,receipt.candidates,selected=receipt.supported,
                selector_outcome='MULTIPLE_ADMISSIBLE',outcome='AMBIGUOUS',search_complete=True)
            joint.history.append({'kind':'CLOSED_PROBE_ALTERNATIVES','selected':list(receipt.supported),
                                  'outcome':'MULTIPLE_ADMISSIBLE','page_refs':[p['decision_ref'] for p in pages]})
            state.decisions[domain_ref]=joint
            from .clarifications import offer
            offer(state,domain_ref,'COMPONENT',context,[v for v,_ in supported])
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
                'status':'PENDING','reason':'MULTIPLE_ADMISSIBLE','decision_ref':domain_ref,
                'enumeration_complete':True,'alternatives':[v for v,_ in supported],'selected':None})
        else:
            if empty is not None:return complete_empty()
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
                'status':'EXHAUSTED','reason':'NO_REMAINING_CANDIDATES','examined':examined,
                'enumeration_complete':True,'domain_ref':domain_ref})
        return None


def licensed(state,proof,**expected):
    if not isinstance(proof,dict):return False
    key,cid=proof.get('decision_ref'),proof.get('candidate_id')
    decision=state.decisions.get(key)
    if not decision or decision.outcome!='RESOLVED' or tuple(decision.selected)!=(cid,):return False
    for row in state.syntax_trace:
        if row.get('kind')!='STRUCTURAL_TASK' or row.get('decision_ref')!=key or row.get('selected')!=cid:continue
        if not row.get('enumeration_complete'):return False
        return any(v.get('candidate_id')==cid and all(v.get(k)==value for k,value in expected.items())
                   for v in row.get('alternatives',()))
    return False


def span(state,release,selector,region,tokens,cfg,slot,question,*,exclude=(),record_remainder=False,admissible=None,initial=None):
    """Every source token boundary is reachable; no punctuation whitelist."""
    forbidden=set(exclude)
    eligible=[(i,t) for i,t in enumerate(tokens) if t.token_id not in forbidden]
    # A caller may propagate a proven, branch-local ownership requirement.
    # Remove a start only when every endpoint violates that requirement.
    def endpoints(a):
        for b in range(a,len(tokens)):
            if tokens[b].token_id in forbidden:break
            if admissible is None or admissible(tokens[a:b+1]):yield b
    if admissible is not None:
        eligible=[(i,t) for i,t in eligible if next(endpoints(i),None) is not None]
    if initial is not None and not any(initial[0].get('index')==i and initial[0].get('token_ref')==t.token_id for i,t in eligible):
        raise ValueError('INITIAL_SOURCE_BOUNDARY_OUTSIDE_DOMAIN')
    rejected=set()
    while len(rejected)<len(eligible):
        starts=({'candidate_id':'start:'+t.token_id,'label':'Start at «'+t.span+'» @'+str(t.start),
                 'index':i,'token_ref':t.token_id} for i,t in eligible if i not in rejected)
        start=initial or choose(state,release,selector,region,cfg,slot+'_start',starts,question+' Select the FIRST token.'+
            (' Earlier starts have no accepted endpoint: '+str(sorted(rejected))+'.' if rejected else ''))
        initial=None
        if start is None:return None
        a=start[0]['index']
        def ends():
            for b in endpoints(a):
                yield {'candidate_id':'end:'+tokens[b].token_id,'index':b+1,
                    **({'boundary_end_ref':tokens[b].token_id,
                        'selected_refs':[t.token_id for t in tokens[a:b+1]],
                        'remainder_refs':[t.token_id for t in [*tokens[:a],*tokens[b+1:]]]}
                       if record_remainder else {}),
                    'label':'End after «'+tokens[b].span+'» @'+str(tokens[b].end)+
                            '; selected words «'+' '.join(t.span for t in tokens[a:b+1])+'»'}
        end=choose(state,release,selector,region,cfg,slot+'_end',ends(),
            question+' The start is «'+tokens[a].span+'» @'+str(tokens[a].start)+'. Select the LAST token.')
        if end:return tokens[a:end[0]['index']],(start[1],end[1])
        if state.syntax_trace[-1].get('status')!='EXHAUSTED':return None
        rejected.add(a)
        state.syntax_trace.append({'kind':'STRUCTURAL_BOUNDARY_CONSTRAINT','region_ref':region.region_id,
            'source_range':list(region.source_range),'start_ref':tokens[a].token_id,'reason':'ALL_ENDS_REJECTED'})
    return None


def source_set(state,release,selector,region,tokens,cfg,slot,question,*,exclude=(),record_remainder=False,admissible=None,partial_admissible=None,initial=None):
    """Select a finite union of source intervals without enumerating 2**n sets.

    Every step either closes the set or adds an occurrence. The final whole
    ownership contract, not the first interval, checks propagated constraints.
    """
    chosen=span(state,release,selector,region,tokens,cfg,slot,
        question+' Select the first continuous piece; other pieces can be added next.',exclude=exclude,
        record_remainder=record_remainder,initial=initial,admissible=partial_admissible)
    if not chosen:return None
    return extend_source_set(state,release,selector,region,tokens,cfg,slot,question,
                             chosen[0],chosen[1],exclude=exclude,admissible=admissible,partial_admissible=partial_admissible)


def extend_source_set(state,release,selector,region,tokens,cfg,slot,question,selected,proofs,*,exclude=(),admissible=None,partial_admissible=None):
    selected,proofs=list(selected),list(proofs);forbidden=set(exclude)
    while True:
        used={t.token_id for t in selected}
        remaining=[t for t in tokens if t.token_id not in used|forbidden]
        if not remaining:break
        def ends(a):
            for b in range(a,len(tokens)):
                if tokens[b].token_id in used|forbidden:break
                if partial_admissible is None or partial_admissible([*selected,*tokens[a:b+1]]):yield b
        reachable={tokens[a].token_id for a in range(len(tokens)) if next(ends(a),None) is not None}
        can_finish=admissible is None or admissible(selected)
        more=choose(state,release,selector,region,cfg,slot+'_continue',[
            *[{'candidate_id':t.token_id,'token_ref':t.token_id,
               'label':'Another piece starts at «'+t.span+'» @'+str(t.start)} for t in remaining if t.token_id in reachable]],
            question+' Already included: «'+' '.join(t.span for t in selected)+'». '
            'Select the start of another piece if one exists. Intervening words retain their own meaning.',
            empty={'candidate_id':'DONE','label':'no further source words belong to this part'} if can_finish else None)
        if not more:return None
        proofs.append(more[1])
        if more[0]['candidate_id']=='DONE':break
        a=next(i for i,t in enumerate(tokens) if t.token_id==more[0]['token_ref'])
        choices=[]
        for b in ends(a):
            choices.append({'candidate_id':tokens[b].token_id,'end':b+1,
                'label':'End after «'+tokens[b].span+'» @'+str(tokens[b].end)})
        end=choose(state,release,selector,region,cfg,slot+'_piece_end',choices,
            question+' Next piece starts at «'+tokens[a].span+'». Select its last word.')
        if not end:return None
        selected.extend(tokens[a:end[0]['end']]);proofs.append(end[1])
    selected.sort(key=lambda t:t.start)
    if admissible is not None and not admissible(selected):
        state.diag('STRUCTURAL_CONTENT_UNCOVERED',region.region_id);return None
    state.syntax_trace.append({'kind':'SOURCE_SET','slot':slot,'region_ref':region.region_id,
        'selected_refs':[t.token_id for t in selected],
        'remainder_refs':[t.token_id for t in tokens if t.token_id not in {x.token_id for x in selected}],
        'proofs':proofs,'search_complete':True})
    return selected,tuple(proofs)
