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


def choose(state,release,selector,region,cfg,slot,options,question):
    if cfg.get('_task_constraints'):
        question+='\nEarlier attempt: '+cfg.get('_task_constraints_text',cfg['_task_constraints'])
    iterator=iter(options);page=0;previous=[];examined=0
    limit=release.entries('ProposalPolicy')[0].get('max_rule_steps',20000)
    from .component_source import view,probe_context
    owned=set(region.token_refs)
    local=view(state,region,[t for t in state.evidence if t.token_id in owned])
    # Ownership limits the answer, not the evidence available for understanding it.
    context,target=probe_context(state,region,cfg,local)
    question=target+question
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
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'EXHAUSTED','reason':'NO_REMAINING_CANDIDATES','examined':examined})
            return None
        examined+=len(values)
        spent={r['decision_ref']:len(r.get('alternatives',())) for r in state.syntax_trace
               if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')}
        if examined>limit or sum(spent.values())+len(values)>limit:
            state.diag('STRUCTURAL_TASK_SEARCH_INCOMPLETE',region.region_id)
            state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
                'slot':slot,'status':'BLOCKED','reason':'SEARCH_LIMIT','examined':examined})
            return None
        choices=[{'candidate_id':v['candidate_id'],'label':v['label']} for v in values]
        key=region.region_id+'|task:'+digest([slot,choices,question,page])
        selected=_probe(state,selector,release,key,slot,choices,context,region.source_range,
            question=question+(' More options remain on another page; 0 rejects only this page.' if has_more else ''))
        decision=state.decisions.get(key)
        outcome=decision.selector_outcome if decision else None
        row={'kind':'STRUCTURAL_TASK','region_ref':region.region_id,'source_range':list(region.source_range),
             'target_token_refs':list(region.token_refs),'context_policy':'TARGET_WITH_CONTEXT',
             'slot':slot,'decision_ref':key,'page':page,'examined':examined,
             'alternatives':values,'selected':selected,'status':'SELECTED' if selected else 'PENDING',
             'reason':outcome or 'PROBE_BLOCKED','enumeration_complete':not has_more,
             'selection_provisional':True,'question':question}
        state.syntax_trace.append(row)
        if selected:
            from .component_probe_replay import supersede
            for rejected in previous:supersede(state,rejected,key)
            return next(v for v in values if v['candidate_id']==selected),{'decision_ref':key,'candidate_id':selected}
        if outcome!='NONE_FIT':return None
        row['status']='REJECTED_PAGE';previous.append(key);page+=1


def licensed(state,proof,**expected):
    if not isinstance(proof,dict):return False
    key,cid=proof.get('decision_ref'),proof.get('candidate_id')
    decision=state.decisions.get(key)
    if not decision or decision.outcome!='RESOLVED' or tuple(decision.selected)!=(cid,):return False
    for row in state.syntax_trace:
        if row.get('kind')!='STRUCTURAL_TASK' or row.get('decision_ref')!=key or row.get('selected')!=cid:continue
        return any(v.get('candidate_id')==cid and all(v.get(k)==value for k,value in expected.items())
                   for v in row.get('alternatives',()))
    return False


def span(state,release,selector,region,tokens,cfg,slot,question,*,exclude=(),show_remainder=False):
    """Every source token boundary is reachable; no punctuation whitelist."""
    forbidden=set(exclude)
    eligible=[(i,t) for i,t in enumerate(tokens) if t.token_id not in forbidden]
    rejected=set()
    while len(rejected)<len(eligible):
        starts=({'candidate_id':'start:'+t.token_id,'label':'Start at «'+t.span+'» @'+str(t.start),
                 'index':i,'token_ref':t.token_id} for i,t in eligible if i not in rejected)
        start=choose(state,release,selector,region,cfg,slot+'_start',starts,question+' Select the FIRST token.'+
            (' Earlier starts have no accepted endpoint: '+str(sorted(rejected))+'.' if rejected else ''))
        if start is None:return None
        a=start[0]['index']
        def ends():
            for b in range(a,len(tokens)):
                if tokens[b].token_id in forbidden:break
                yield {'candidate_id':'end:'+tokens[b].token_id,'index':b+1,
                    'label':'End after «'+tokens[b].span+'» @'+str(tokens[b].end)+
                            '; selected words «'+' '.join(t.span for t in tokens[a:b+1])+'»'+
                            ('; content left for this relation: «'+' '.join(t.span for t in [*tokens[:a],*tokens[b+1:]])+'»'
                             if show_remainder else '')}
        end=choose(state,release,selector,region,cfg,slot+'_end',ends(),
            question+' The start is «'+tokens[a].span+'» @'+str(tokens[a].start)+'. Select the LAST token.')
        if end:return tokens[a:end[0]['index']],(start[1],end[1])
        if state.syntax_trace[-1].get('status')!='EXHAUSTED':return None
        rejected.add(a)
        state.syntax_trace.append({'kind':'STRUCTURAL_BOUNDARY_CONSTRAINT','region_ref':region.region_id,
            'source_range':list(region.source_range),'start_ref':tokens[a].token_id,'reason':'ALL_ENDS_REJECTED'})
    return None
