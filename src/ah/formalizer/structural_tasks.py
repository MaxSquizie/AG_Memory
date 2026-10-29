"""Addressed closed tasks with bounded candidate pages and explicit search state.

No graph generation, guessed words or writes. A NONE_FIT answer rejects only
the displayed page; an unknown answer leaves that task pending. The selected
local relation remains provisional until its children and source coverage close.
"""
from itertools import islice,chain
from .canonical_ledger import digest
from .component_probe import _probe
from .selection_evidence import selected_candidate
from .task_contracts import SelectionPurpose, required_selection_purpose


def enabled(release):
    return release.entries('ProposalPolicy')[0].get('composition',{}).get('structural_tasks')=='CLOSED_RELATIONS_V1'


def choose(state,release,selector,region,cfg,slot,options,question,*,empty=None,source_selection=None,prerequisites=(),purpose=SelectionPurpose.ALTERNATIVE):
    return _choose(state,release,selector,region,cfg,slot,options,question,empty=empty,source_selection=source_selection,prerequisites=prerequisites,purpose=purpose)


def choose_domain(state,release,selector,region,cfg,slot,options,question,*,prerequisites=()):
    """Return all supported alternatives only after the entire domain closes."""
    from .partial_readings import SupportedDomain
    result=_choose(state,release,selector,region,cfg,slot,options,question,retain_domain=True,prerequisites=prerequisites)
    if result is None or isinstance(result,SupportedDomain):return result
    value,proof=result
    return SupportedDomain((value,),proof['decision_ref'],proof['domain_ref'])


def _choose(state,release,selector,region,cfg,slot,options,question,*,empty=None,retain_domain=False,source_selection=None,prerequisites=(),purpose=SelectionPurpose.ALTERNATIVE):
    """Optional searches declare a typed completion outside the model domain.

    NONE_FIT closes only one page. EMPTY is licensed only after every page was
    examined and rejected; unknown, ambiguity and budget stops never close it.
    """
    if not isinstance(purpose,SelectionPurpose):
        raise ValueError('SELECTION_PURPOSE_INVALID')
    required=required_selection_purpose(slot,source_selection)
    if required is not None and purpose!=required:
        raise ValueError('SELECTION_PURPOSE_CONSUMER_MISMATCH')
    # Confirmations are a finite, single proposal, never a paginated search.
    if purpose==SelectionPurpose.CONFIRM:
        options=list(islice(iter(options),2))
        if len(options)!=1 or empty is not None:
            raise ValueError('CONFIRMATION_REQUIRES_ONE_PROPOSAL')
    from .probe_prerequisites import errors as premise_errors
    prerequisites=tuple(prerequisites)
    prerequisite_records=[r.record() for r in prerequisites]
    def premises_live():
        errors=premise_errors(state,prerequisites)
        from .composition_session import current
        runtime=current(state)
        if runtime is not None:errors=(*errors,*runtime.input_errors())
        if errors:
            state.diag('PROBE_INPUT_INCOMPLETE',region.region_id+': '+', '.join(errors))
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'BLOCKED','reason':'PREMISE_CONTRACT_INVALID','errors':errors})
        return not errors
    if not premises_live():return None
    if source_selection is not None:
        errors=source_selection.errors(state,(),region.token_refs)
        if errors:
            state.diag('PROBE_INPUT_INCOMPLETE',region.region_id+': '+', '.join(errors))
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'BLOCKED','reason':'SOURCE_CONTRACT_INVALID','errors':errors})
            return None
    # Failure of a whole hypothesis does not refute every constituent choice.
    # Keep revision identity in keys without injecting the rejected hypothesis
    # into unrelated ownership, morphology and participant questions.
    from dataclasses import asdict
    revision_scope=digest([purpose.value,cfg.get('_task_constraints'),cfg.get('_ownership_feedback'),
                          asdict(source_selection) if source_selection is not None else None,prerequisite_records])
    if cfg.get('_task_constraints') and slot in {'structural_relation','structural_revision'}:
        question+='\nEarlier attempt: '+cfg.get('_task_constraints_text',cfg['_task_constraints'])
    if cfg.get('_ownership_feedback'):
        question+='\nOwnership revision: '+cfg['_ownership_feedback']
    from .composition_session import current
    runtime=current(state)
    task_scope=runtime.input_signature() if runtime else None
    iterator=iter(options);page=0;previous=[];examined=0
    supported=[];pages=[];seen=set();page_evidence=[]
    from .selection_domains import capture,valid as valid_enumeration
    from .structural_probe_inputs import source_signature,parent_signature
    basis=(source_signature(state),parent_signature(state))
    def enumeration_record():
        from .task_contracts import SelectionReceipt
        receipt=SelectionReceipt(tuple(sorted(seen)),tuple(sorted(v['candidate_id'] for v,_ in supported)),True,purpose=purpose)
        return {'page_refs':[p['decision_ref'] for p in pages],
                'page_evidence':list(page_evidence),
                'supported_payloads':{v['candidate_id']:digest(v) for v,_ in supported},**receipt.record()}
    def enumeration_live():
        if (basis!=(source_signature(state),parent_signature(state))
                or not valid_enumeration(state,enumeration_record())):
            state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',region.region_id)
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'BLOCKED','reason':'ENUMERATION_EVIDENCE_CHANGED'})
            return False
        return True
    limit=release.entries('ProposalPolicy')[0].get('max_rule_steps',20000)
    from .component_source import view,probe_context
    owned=set(region.token_refs)
    local=view(state,region,[t for t in state.evidence if t.token_id in owned])
    # Ownership limits the answer, not the evidence available for understanding it.
    context,target=probe_context(state,region,cfg,local)
    question=target+purpose.wording()+" "+question
    if empty is not None:
        question+=' Optional search: examine the listed candidates; 0 means none of THESE fits, not missing context.'
    def complete_empty():
        if not premises_live() or not enumeration_live():return None
        from .state import Decision,Ground
        key='task-empty:'+digest([region.region_id,task_scope,revision_scope,slot,question,sorted(seen),page_evidence,empty])
        state.syntax_trace.append({'kind':'TASK_DOMAIN','task_ref':key,'level':'T2_TP',
            'slot':slot,'source_range':list(region.source_range),'token_refs':list(region.token_refs),
            'prerequisites':prerequisite_records,**enumeration_record()})
        cid=empty['candidate_id']
        if cid in seen:raise ValueError('EMPTY_COMPLETION_IN_POSITIVE_DOMAIN')
        state.decisions[key]=Decision(slot,key,tuple(sorted(seen))+ (cid,),selected=(cid,),
            lifecycle='PROVISIONAL',search_complete=True,
            grounds=[Ground('D','enumerated caller generator has no supported candidate',cid)])
        state.decisions[key].history.append({'kind':'EMPTY_DOMAIN','page_refs':list(previous),
            'positive_candidates':sorted(seen),'completion':empty})
        state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
            'status':'SELECTED','decision_ref':key,'enumeration_complete':True,
            'payload_hash':digest(empty),'alternatives':[empty],'selected':cid,'task_outcome':'EMPTY','enumeration_scope':'CALLER_GENERATOR','interpretation_complete':False,'page_refs':list(previous),'selection_purpose':purpose.value,'prerequisites':prerequisite_records})
        return empty,{'decision_ref':key,'candidate_id':cid,'domain_ref':key,'payload_hash':digest(empty),'selection_purpose':purpose.value}
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
                'slot':slot,'status':'EXHAUSTED','reason':'NO_REMAINING_CANDIDATES','examined':examined,
                'enumeration_complete':True})
            return None
        examined+=len(values)
        choices=[{'candidate_id':v['candidate_id'],'label':v['label']} for v in values]
        key=region.region_id+'|task:'+digest([task_scope,revision_scope,slot,values,question,page])
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
        from .structural_probe_inputs import inputs
        page_inputs=inputs(state,region,slot,values,question,context,page,source_selection,prerequisites,purpose)
        selected=_probe(state,selector,release,key,slot,choices,context,region.source_range,
            inputs=page_inputs,
            offer_clarification=False,
            question=question)
        if not premises_live():return None
        decision=state.decisions.get(key)
        outcome=('ONE_SELECTED' if selected is not None and selected_candidate(decision)==selected
                 else decision.selector_outcome if decision else None)
        row={'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'source_range':list(region.source_range),
             'target_token_refs':list(region.token_refs),'context_policy':'TARGET_WITH_CONTEXT',
             'slot':slot,'decision_ref':key,'page':page,'examined':examined,
             'alternatives':values,'selected':selected,'status':'SELECTED' if selected else 'PENDING',
             'reason':outcome or 'PROBE_BLOCKED','enumeration_complete':False,
             'selection_provisional':True,'question':question,'selection_purpose':purpose.value,'prerequisites':prerequisite_records}
        state.syntax_trace.append(row)
        pages.append(row)
        if decision is not None:decision.search_complete=False
        admissible=([selected] if selected else next((h['selected'] for h in reversed(getattr(decision,'history',()))
                    if isinstance(h,dict) and h.get('kind')=='CLOSED_PROBE_ALTERNATIVES'),[]))
        if outcome not in {'ONE_SELECTED','MULTIPLE_ADMISSIBLE','NONE_FIT'}:
            row['task_outcome']='UNKNOWN' if outcome=='INSUFFICIENT_CONTEXT' else 'RESOURCE_BLOCKED'
            return None
        evidence=capture(state,key,values)
        if evidence is None:
            state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',region.region_id);return None
        page_evidence.append(evidence)
        supported.extend((v,key) for v in values if v['candidate_id'] in admissible)
        if outcome=='NONE_FIT':row['status']='REJECTED_PAGE';previous.append(key)
        if has_more:page+=1;continue
        if not enumeration_live():return None
        from .task_contracts import SelectionReceipt
        receipt=SelectionReceipt(tuple(sorted(seen)),tuple(sorted(v['candidate_id'] for v,_ in supported)),True,purpose=purpose)
        domain_ref='task-domain:'+digest([region.region_id,task_scope,slot,question,receipt.candidates,page_evidence,[(p['decision_ref'],p['alternatives']) for p in pages]])
        state.syntax_trace.append({'kind':'TASK_DOMAIN','task_ref':domain_ref,'level':'T2_TP',
            'slot':slot,'source_range':list(region.source_range),'token_refs':list(region.token_refs),
            'page_refs':[p['decision_ref'] for p in pages],'selection_purpose':purpose.value,'prerequisites':prerequisite_records,
            'page_evidence':list(page_evidence),
            'supported_payloads':{v['candidate_id']:digest(v) for v,_ in supported},**receipt.record()})
        from .clarifications import choice
        explicit=choice(state,domain_ref,receipt.supported) if supported else None
        if explicit is not None:
            from .state import Decision,Ground
            value=next(v for v,_ in supported if v['candidate_id']==explicit)
            state.decisions[domain_ref]=Decision(slot,domain_ref,receipt.candidates,selected=(explicit,),
                lifecycle='PROVISIONAL',search_complete=True,grounds=[Ground('C','explicit clarification of the complete domain',explicit)])
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
                'status':'SELECTED','decision_ref':domain_ref,'enumeration_complete':True,
                'selection_purpose':purpose.value,'prerequisites':prerequisite_records,'alternatives':[v for v,_ in supported],'selected':explicit,'domain_ref':domain_ref,'payload_hash':digest(value)})
            return value,{'decision_ref':domain_ref,'candidate_id':explicit,'domain_ref':domain_ref,'payload_hash':digest(value),'selection_purpose':purpose.value}
        if len(supported)==1:
            value,winner=supported[0]
            from copy import deepcopy
            decision=deepcopy(state.decisions[winner])
            decision.frame_id=domain_ref;decision.candidates=receipt.candidates
            decision.search_complete=True;decision.outcome=None
            state.decisions[domain_ref]=decision
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
                'status':'SELECTED','decision_ref':domain_ref,'enumeration_complete':True,
                'selection_purpose':purpose.value,'prerequisites':prerequisite_records,'alternatives':[value],'selected':value['candidate_id'],'domain_ref':domain_ref,
                'payload_hash':digest(value),'task_outcome':'SUPPORTED'})
            return value,{'decision_ref':domain_ref,'candidate_id':value['candidate_id'],
                          'domain_ref':domain_ref,'payload_hash':digest(value),'selection_purpose':purpose.value}
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
            if retain_domain:
                from .partial_readings import SupportedDomain
                return SupportedDomain(tuple(v for v,_ in supported),domain_ref,domain_ref)
        else:
            if empty is not None:return complete_empty()
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'slot':slot,
                'status':'EXHAUSTED','reason':'NO_REMAINING_CANDIDATES','examined':examined,
                'enumeration_complete':True,'domain_ref':domain_ref})
        return None


def _licensed(state,proof,*,_visiting=None,**expected):
    """Validate the finite dependency graph without recursive Python calls."""
    if not isinstance(proof,dict):return False
    from .partial_readings import retired_refs
    retired=retired_refs(state.syntax_trace)
    rows={};domains={}
    for row in state.syntax_trace:
        if row.get('kind')=='STRUCTURAL_TASK':
            rows[(row.get('decision_ref'),row.get('selected'))]=row
        elif row.get('kind')=='TASK_DOMAIN':domains[row.get('task_ref')]=row
    active=set(_visiting or ());done=set();stack=[(proof,False,expected)]
    while stack:
        current,leaving,required=stack.pop()
        if not isinstance(current,dict):return False
        key,cid=current.get('decision_ref'),current.get('candidate_id')
        identity=digest(current)
        if leaving:
            active.remove(key);done.add(identity);continue
        if key in active:return False
        if identity in done and not required:continue
        domain=current.get('domain_ref')
        if key in retired or domain in retired:return False
        if retired.intersection(domains.get(domain,{}).get('page_refs',())):return False
        if domain not in domains:return False
        from .selection_domains import valid as valid_enumeration
        if not valid_enumeration(state,domains[domain],retired):return False
        decision=state.decisions.get(key)
        if selected_candidate(decision)!=cid or decision.search_complete is not True:return False
        row=rows.get((key,cid))
        if row is None or not row.get('enumeration_complete'):return False
        if (current.get('selection_purpose')!=row.get('selection_purpose')
                or current.get('selection_purpose')!=domains[domain].get('selection_purpose')):return False
        if row.get('task_outcome')=='EMPTY':
            if domains[domain].get('supported_ids'):return False
        elif domains[domain].get('supported_payloads',{}).get(cid)!=current.get('payload_hash'):return False
        if not any(v.get('candidate_id')==cid and digest(v)==current.get('payload_hash')==row.get('payload_hash')
                   and all(v.get(k)==value for k,value in required.items()) for v in row.get('alternatives',())):return False
        active.add(key);stack.append((current,True,{}))
        for premise in row.get('prerequisites',()):
            prior=state.decisions.get(premise['proof'].get('decision_ref'))
            if prior is None or prior.slot_id!=premise['slot']:return False
            if digest(premise['value'])!=premise['proof'].get('payload_hash'):return False
            stack.append((premise['proof'],False,{}))
    return True


def licensed(state,proof,*,_visiting=None,**expected):
    result=_licensed(state,proof,_visiting=_visiting,**expected)
    # A failed read matters too: otherwise a cached pending result cannot see
    # a repaired prerequisite. Payload expectations remain part of the read.
    from .dispatch_evidence import observe
    if _visiting is None:observe(state,'PROOF',{'proof':proof,'expected_payload':expected},result)
    return result


def span(state,release,selector,region,tokens,cfg,slot,question,*,exclude=(),record_remainder=False,admissible=None,initial=None,prerequisites=()):
    """Every source token boundary is reachable; no punctuation whitelist."""
    from .structural_probe_inputs import collection
    from .probe_prerequisites import from_proof
    forbidden=set(exclude)
    begin=len(state.syntax_trace)
    def exhausted():
        # This closes the first-piece search under these restrictions only.
        # It is not exhaustion of every partition of the original source.
        state.syntax_trace.append({'kind':'SOURCE_SPAN_EXHAUSTED','region_ref':region.region_id,
            'slot':slot,'available_refs':[t.token_id for t in tokens if t.token_id not in forbidden],
            'excluded_refs':sorted(forbidden),'domain_refs':[r['task_ref'] for r in state.syntax_trace[begin:]
                if r.get('kind')=='TASK_DOMAIN'], 'search_complete':False,
            'first_piece_search_complete':True})
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
            (' No offered endpoint was accepted for these earlier starts under the current restrictions: '+
             ', '.join('«'+tokens[i].span+'» @'+str(tokens[i].start) for i in sorted(rejected))+
             '. This does not reject the remaining starts.' if rejected else ''),
            source_selection=collection('START',tokens,exclude=forbidden),prerequisites=prerequisites)
        initial=None
        if start is None:
            if state.syntax_trace[-1].get('status')=='EXHAUSTED':exhausted()
            return None
        a=start[0]['index']
        def ends():
            for b in endpoints(a):
                yield {'candidate_id':'end:'+tokens[b].token_id,'index':b+1,'token_ref':tokens[b].token_id,
                    **({'boundary_end_ref':tokens[b].token_id,
                        'selected_refs':[t.token_id for t in tokens[a:b+1]],
                        'remainder_refs':[t.token_id for t in [*tokens[:a],*tokens[b+1:]]]}
                       if record_remainder else {}),
                    'label':'End after «'+tokens[b].span+'» @'+str(tokens[b].end)+
                            '; selected words «'+' '.join(t.span for t in tokens[a:b+1])+'»'}
        end=choose(state,release,selector,region,cfg,slot+'_end',ends(),
            question+' The start is «'+tokens[a].span+'» @'+str(tokens[a].start)+'. Select the LAST token.',
            source_selection=collection('END',tokens,exclude=forbidden,start=tokens[a].token_id),
            prerequisites=(*prerequisites,from_proof(state,start[1])))
        if end:return tokens[a:end[0]['index']],(start[1],end[1])
        if state.syntax_trace[-1].get('status')!='EXHAUSTED':return None
        rejected.add(a)
        state.syntax_trace.append({'kind':'STRUCTURAL_BOUNDARY_CONSTRAINT','region_ref':region.region_id,
            'source_range':list(region.source_range),'start_ref':tokens[a].token_id,'reason':'ALL_ENDS_REJECTED'})
    exhausted()
    return None


def source_set(state,release,selector,region,tokens,cfg,slot,question,*,exclude=(),record_remainder=False,admissible=None,partial_admissible=None,initial=None,prerequisites=()):
    """Select a finite union of source intervals without enumerating 2**n sets.

    Every step either closes the set or adds an occurrence. The final whole
    ownership contract, not the first interval, checks propagated constraints.
    """
    chosen=span(state,release,selector,region,tokens,cfg,slot,
        question+' Select the first continuous piece; other pieces can be added next.',exclude=exclude,
        record_remainder=record_remainder,initial=initial,admissible=partial_admissible,prerequisites=prerequisites)
    if not chosen:return None
    return extend_source_set(state,release,selector,region,tokens,cfg,slot,question,
                             chosen[0],chosen[1],exclude=exclude,admissible=admissible,partial_admissible=partial_admissible)


def extend_source_set(state,release,selector,region,tokens,cfg,slot,question,selected,proofs,*,exclude=(),admissible=None,partial_admissible=None):
    from .structural_probe_inputs import collection
    from .probe_prerequisites import from_proof
    selected,proofs=list(selected),list(proofs);forbidden=set(exclude)
    completion_reason=None;completion_proof=None
    while True:
        # The peer sees source order, not the order in which pieces happened
        # to be discovered. A later repair can add an earlier occurrence.
        selected.sort(key=lambda t:(t.start,t.end,t.token_id))
        used={t.token_id for t in selected}
        remaining=[t for t in tokens if t.token_id not in used|forbidden]
        if not remaining:
            completion_reason='ALL_AVAILABLE_OCCURRENCES';break
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
            'Are any words OF THIS SAME PART still missing? If the part is complete, answer 0. '
            'Otherwise select where its FIRST missing piece begins. Words of another part are not a continuation of this part. '
            'Do not select the next clause just because it comes next, or select already included words again.',
            empty={'candidate_id':'DONE','label':'no further source words belong to this part'} if can_finish else None,
            source_selection=collection('CONTINUE',tokens,selected,forbidden),purpose=SelectionPurpose.NEXT,
            prerequisites=tuple(from_proof(state,p) for p in proofs))
        if not more:return None
        proofs.append(more[1])
        if more[0]['candidate_id']=='DONE':
            completion_reason='NO_SUPPORTED_ADDITION';completion_proof=more[1];break
        a=next(i for i,t in enumerate(tokens) if t.token_id==more[0]['token_ref'])
        choices=[]
        for b in ends(a):
            choices.append({'candidate_id':tokens[b].token_id,'end':b+1,'token_ref':tokens[b].token_id,
                'label':'End after «'+tokens[b].span+'» @'+str(tokens[b].end)})
        end=choose(state,release,selector,region,cfg,slot+'_piece_end',choices,
            'Expression being collected: '+question+' Already included: «'+' '.join(t.span for t in selected)+'». Next piece starts at «'+tokens[a].span+'». Select ONLY its last word.',
            source_selection=collection('PIECE_END',tokens,selected,forbidden,start=tokens[a].token_id),
            prerequisites=(from_proof(state,more[1]),))
        if not end:return None
        selected.extend(tokens[a:end[0]['end']]);proofs.append(end[1])
    if not all(licensed(state,p) for p in proofs):
        state.diag('SOURCE_SELECTION_PREMISE_RETIRED',region.region_id);return None
    selected.sort(key=lambda t:t.start)
    if admissible is not None and not admissible(selected):
        state.diag('STRUCTURAL_CONTENT_UNCOVERED',region.region_id);return None
    from .source_collections import CollectionReceipt,valid as valid_collection
    receipt=CollectionReceipt(tuple(t.token_id for t in tokens),tuple(t.token_id for t in selected),
        tuple(t.token_id for t in tokens if t.token_id in forbidden),tuple(proofs),completion_reason,completion_proof)
    record=receipt.record()
    if not valid_collection(state,record):
        state.diag('SOURCE_COLLECTION_UNRESOLVED',region.region_id);return None
    state.syntax_trace.append({'kind':'SOURCE_SET','slot':slot,'region_ref':region.region_id,
        'remainder_refs':[t.token_id for t in tokens if t.token_id not in {x.token_id for x in selected}],**record})
    return selected,tuple(proofs)
