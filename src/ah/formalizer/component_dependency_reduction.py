"""Reduce local dependencies before the Cartesian predicate-role join."""
from .canonical_ledger import digest
from .component_dependency_domains import domains,clean
from .dependency_constraints import network, propagate
from .component_probe import _probe


def reduce(state,release,selector,region,tokens,p,pv,roles,nominals,groups,cfg,*,required_roots=None,required_readings=None,quantities=(),nominal_groups=()):
    pool=domains(tokens,nominals,groups,roles,pv,cfg,quantities,nominal_groups);fixed={};trace=[];deferred={}
    if required_roots is not None:
        for tid,choices in pool.items():
            pool[tid]={cid:o for cid,o in choices.items() if
                       (o['kind']=='ROOT' and o['role']==required_roots[tid] if tid in required_roots else o['kind']!='ROOT')}
    for tid,reading in (required_readings or {}).items():
        pool[tid]={cid:o for cid,o in pool[tid].items() if o.get('morph')==reading}
    graph=network(pool,nominal_groups);pool=graph.domains
    evidence={e.token_id:e for e in tokens}
    context_range=region.source_range
    paragraph=state.region_forest.container(*region.source_range,kinds={'PARAGRAPH'})
    if paragraph and paragraph.source_range[1]-paragraph.source_range[0]<=cfg['context_chars']:
        context_range=paragraph.source_range
    while True:
        if not propagate(graph,fixed):
            state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','region_ref':region.region_id,
                'predicate_ref':p.token_id,'predicate_reading':clean(pv),'roles':roles,
                'empty_domains':[tid for tid,choices in pool.items() if not choices]})
            state.diag('COMPONENT_DEPENDENCY_CONTRADICTION',region.region_id);return None
        if len(fixed)==len(pool):break
        # A locally unresolved slot must not stop independent constraints.
        # Retry only after its domain or the fixed environment has changed.
        environment=digest({t:clean_option(o) for t,o in fixed.items()})
        stamps={t:digest([list(pool[t]),environment]) for t in pool if t not in fixed}
        remaining=[t for t in stamps if deferred.get(t)!=stamps[t]]
        if not remaining:
            state.syntax_trace.append({'kind':'DEPENDENCY_RESIDUAL','region_ref':region.region_id,
                'predicate_ref':p.token_id,'fixed':{t:clean_option(o) for t,o in fixed.items()},
                'domains':{t:{cid:clean_option(o) for cid,o in pool[t].items()} for t in stamps},
                'constraint_state':graph.snapshot()})
            state.diag('COMPONENT_DEPENDENCY_UNRESOLVED',region.region_id)
            return None
        tid=min(remaining,key=lambda t:(len(pool[t]),evidence[t].start))
        choices=pool[tid]
        from .morphology_domain import proposed, license_use
        needs_license=any(proposed(o.get(field,{})) for o in choices.values() for field in ('morph','head_morph'))
        # Case compatibility and a nearby comma admit these attachments; they
        # do not establish a noun complement or an explanatory description.
        needs_attachment=any(o['kind'] in {'APPOSITION','CASE_DEPENDENCY'} for o in choices.values())
        if len(choices)==1 and not needs_license and not needs_attachment:
            cid=next(iter(choices));ground='D'
        else:
            if len(choices)>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
            options=[]
            from .probe_wording import reading as reading_text,role as role_text
            for cid,o in choices.items():
                reading=o.get('morph',{})
                if o['kind']=='ROOT': label='Direct role '+o['role']+' of predicate «'+p.span+'» ('+role_text(o['role'])+')'
                elif o['kind']=='DEFER_PP':label='Prepositional phrase; defer its host to the PP attachment question'
                else:label=o['kind']+' dependency on «'+evidence[o['host_ref']].span+'» at '+str(evidence[o['host_ref']].start)
                if o.get('head_morph'):label+='; internal head reading: '+reading_text(o['head_morph'])
                if o.get('host_layer')=='HEAD':label+='; agrees with internal head of quantity group'
                options.append({'candidate_id':cid,'label':label+'; '+reading_text(reading)})
            committed=[{'dependent':evidence[t].span,'attachment':o['kind'],
                        'host':evidence[o['host_ref']].span if 'host_ref' in o else o.get('role')} for t,o in fixed.items()]
            question='Choose the immediate grammatical attachment of «'+evidence[tid].span+'» at '+str(evidence[tid].start)+'. '
            kinds={o['kind'] for o in choices.values()}
            if 'GENITIVE' in kinds:
                question+='GENITIVE means a noun in the genitive case modifying another noun; it does not establish ownership. '
            if 'CASE_DEPENDENCY' in kinds:
                question+='CASE_DEPENDENCY means a complement of the named noun, not an argument of the verb. Matching case alone is insufficient. '
            if 'APPOSITION' in kinds:
                question+='APPOSITION is an explanatory nominal description, not entity identity. '
            if needs_license and any(o.get(field,{}).get('evidence_refs',[''])[0].startswith('usage-reading:') for o in choices.values() for field in ('morph','head_morph') if o.get(field,{}).get('evidence_refs')):
                question+='CONTEXTUAL readings are occurrence-local proposals: confirm the grammatical case together with this attachment. Preserve unknown surfaces; do not infer lexical meaning, name identity, gender, or silently correct spelling. '
            elif needs_license:
                question+='SUBSTANTIVE is a proposed noun-like use of an adjective, not a dictionary fact: select it only if this occurrence independently denotes an entity in the selected slot. '
            descriptions=['«'+evidence[t].span+'» is '+(
                role_text(o['role'])+' «'+p.span+'»' if o['kind']=='ROOT' else
                o['kind']+' attached to «'+evidence[o['host_ref']].span+'»' if 'host_ref' in o else
                'a prepositional phrase with its attachment still to be decided') for t,o in fixed.items()]
            if descriptions:question+='Already fixed dependencies: '+'; '.join(descriptions)+'. '
            question+='Choose the attachment supported by this sentence; preserve ambiguity if evidence is insufficient.'
            probe_key=region.region_id+'|dependency:'+digest([p.token_id,pv.lemma,roles,tid,options,committed,context_range])
            cid=_probe(state,selector,release,probe_key,'nominal_dependency',options,
                       state.text[slice(*context_range)],region.source_range,question=question)
            if cid is None:
                decision=state.decisions.get(probe_key)
                if decision and decision.selector_outcome=='NONE_FIT':
                    state.clarification_candidates=[r for r in state.clarification_candidates if r['decision_ref']!=probe_key]
                    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','region_ref':region.region_id,'predicate_ref':p.token_id,'decision_ref':probe_key,'reason':'NO_LICENSED_ATTACHMENT'})
                    return None
                deferred[tid]=stamps[tid]
                continue
            ground='M'
            for field in ('morph','head_morph'):
                license_use(state,tid,choices[cid].get(field,{}),probe_key,cid)
        fixed[tid]=choices[cid]
        trace.append({'kind':'FIXED_DEPENDENCY','token_ref':tid,'selected':cid,'ground':ground,
                      'remaining_domain_ids':list(choices)})
    state.syntax_trace.append({'kind':'DEPENDENCY_CONSTRAINT_CLOSURE','region_ref':region.region_id,
                              'predicate_ref':p.token_id,'constraint_state':graph.snapshot()})
    roots={t:(o['role'],o['variant'],o.get('prep_variant')) for t,o in fixed.items() if o['kind']=='ROOT'}
    deps=[{'head_ref':t,**{k:v for k,v in o.items() if k not in {'variant','prep_variant'}}}
          for t,o in fixed.items() if o['kind'] in {'GENITIVE','APPOSITION','CASE_DEPENDENCY'}]
    attributes=[{'head_ref':t,**{k:v for k,v in o.items() if k not in {'variant','prep_variant'}}}
                for t,o in fixed.items() if o['kind']=='ATTRIBUTE']
    return {'group_readings':{t:{'selected_head_reading':o['head_morph'],'external_reading':o['morph']}
                              for t,o in fixed.items() if 'head_morph' in o},'roots':roots,'dependencies':deps,'attributes':attributes,'trace':trace,
            'pp_readings':{t:o['morph'] for t,o in fixed.items() if o['kind']=='DEFER_PP'}}


def clean_option(option):
    return {k:v for k,v in option.items() if k not in {'variant','prep_variant'}}
