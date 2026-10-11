"""Reduce local dependencies before the Cartesian predicate-role join."""
from .canonical_ledger import digest
from .component_dependency_domains import domains,prune
from .component_probe import _probe


def reduce(state,release,selector,region,tokens,p,pv,roles,nominals,groups,cfg):
    pool=domains(tokens,nominals,groups,roles,pv,cfg);fixed={};trace=[]
    evidence={e.token_id:e for e in tokens}
    context_range=region.source_range
    paragraph=state.region_forest.container(*region.source_range,kinds={'PARAGRAPH'})
    if paragraph and paragraph.source_range[1]-paragraph.source_range[0]<=cfg['context_chars']:
        context_range=paragraph.source_range
    while len(fixed)<len(pool):
        if not prune(pool,fixed):
            state.diag('COMPONENT_DEPENDENCY_CONTRADICTION',region.region_id);return None
        remaining=[t for t in pool if t not in fixed]
        tid=min(remaining,key=lambda t:(len(pool[t]),evidence[t].start))
        choices=pool[tid]
        if len(choices)==1:
            cid=next(iter(choices));ground='D'
        else:
            if len(choices)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
            options=[]
            for cid,o in choices.items():
                reading={k:v for k,v in o.get('morph',{}).items() if k in {'lemma','pos','cases','number','gender'}}
                if o['kind']=='ROOT': label='Direct role '+o['role']+' of predicate «'+p.span+'»'
                elif o['kind']=='DEFER_PP':label='Prepositional phrase; defer its host to the PP attachment question'
                else:label=o['kind']+' dependency on «'+evidence[o['host_ref']].span+'» at '+str(evidence[o['host_ref']].start)
                options.append({'candidate_id':cid,'label':label+'; whole reading='+str(reading)})
            committed=[{'dependent':evidence[t].span,'attachment':o['kind'],
                        'host':evidence[o['host_ref']].span if 'host_ref' in o else o.get('role')} for t,o in fixed.items()]
            question='Choose the immediate grammatical attachment of «'+evidence[tid].span+'» at '+str(evidence[tid].start)+'. '
            question+='GENITIVE records a nominal dependency, not ownership. APPOSITION records an explanation, not entity identity. '
            question+='Already fixed dependencies: '+str(committed)+'. Preserve ambiguity if evidence is insufficient.'
            probe_key=region.region_id+'|dependency:'+digest([p.token_id,pv.lemma,roles,tid,options,committed,context_range])
            previous=state.decisions.get(probe_key)
            cid=previous.selected[0] if previous and previous.outcome=='RESOLVED' and len(previous.selected)==1 else None
            if previous is None:
                cid=_probe(state,selector,release,probe_key,'nominal_dependency',options,
                           state.text[slice(*context_range)],region.source_range,question=question)
            if cid is None:
                state.diag('COMPONENT_DEPENDENCY_UNRESOLVED',region.region_id);return None
            ground='M'
        fixed[tid]=choices[cid]
        trace.append({'kind':'FIXED_DEPENDENCY','token_ref':tid,'selected':cid,'ground':ground,
                      'remaining_domain_ids':list(choices)})
    roots={t:(o['role'],o['variant'],o.get('prep_variant')) for t,o in fixed.items() if o['kind']=='ROOT'}
    deps=[{'head_ref':t,**{k:v for k,v in o.items() if k not in {'variant','prep_variant'}}}
          for t,o in fixed.items() if o['kind'] in {'GENITIVE','APPOSITION'}]
    return {'roots':roots,'dependencies':deps,'trace':trace}
