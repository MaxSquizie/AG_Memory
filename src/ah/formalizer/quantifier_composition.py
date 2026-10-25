"""Released nominal binders feed the common proposition scope domains.

No noun occurrence becomes an entity witness. Restriction and body retain the
same bound variable, and only a closed quantified root can be asserted.
"""
import re
from .selection_evidence import selected_candidate
from copy import deepcopy
from .canonical_ledger import digest
from .component_source import view
from .component_probe import _probe
from .composition_domains import DomainNetwork
from .state import FrameCandidate,ResourceProvenance
from .morphology_domain import clean,license_use


def validate_rule(rule,roles):
    spec=rule.get('restriction_pattern',{})
    if (rule.get('operator') not in {'FORALL','EXISTS'} or rule.get('variable_sort')!='ENTITY'
            or set(spec)!={'head_pos','agreement','role','body_operator'}
            or not spec['head_pos'] or not set(spec['head_pos'])<={'NOUN','NPRO'}
            or not spec['agreement'] or not set(spec['agreement'])<={'cases','number','gender'}
            or spec['role'] not in roles
            or spec['body_operator']!=('IMPLIES' if rule['operator']=='FORALL' else 'AND')):
        raise ValueError('QUANTIFIER_RESTRICTION_RULE_INVALID')


def lexical_matches(state,release,region,tokens):
    raw=view(state,region,tokens);matches={}
    for rule in release.entries('ScopeLexicon'):
        if 'QUANTIFIED_NOMINAL' not in rule.get('attachment_kinds',()):continue
        for match in re.finditer(rule['pattern'],raw,re.I):
            lo,hi=region.source_range[0]+match.start(),region.source_range[0]+match.end()
            anchors=[t for t in tokens if lo<=t.start and t.end<=hi]
            if anchors:
                key=lo,hi,rule['operator']
                if key in matches and any(matches[key][1].get(k)!=rule.get(k)
                        for k in ('variable_sort','restriction_pattern')):
                    state.diag('QUANTIFIER_LEXICAL_SCOPE_UNRESOLVED',region.region_id)
                    return None
                matches[key]=(anchors,rule)
    return matches


def compatible(marker,reading,features):
    for feature in features:
        a=getattr(marker,feature);b=reading.get(feature)
        if feature=='cases':
            if not a or not b or not set(a)&set(b):return False
        elif a is not None and b is not None and a!=b:return False
    return True


def bind(state,release,selector,region,frames,matches,cfg):
    from .syntax_rules import SearchLimit
    remaining=release.entries('ProposalPolicy')[0].get('max_rule_steps',20000)
    def spend():
        nonlocal remaining
        remaining-=1
        if remaining<0:raise SearchLimit('QUANTIFIER_BINDING_SEARCH_INCOMPLETE')
    try:
        return _bind(state,release,selector,region,frames,matches,cfg,spend)
    except SearchLimit as exc:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',str(exc));return None


def _bind(state,release,selector,region,frames,matches,cfg,spend):
    evidence={t.token_id:t for t in state.evidence};domains={};specs={}
    for bounds,(anchors,rule) in matches.items():
        mid='operator-slot:'+digest([region.region_id,*bounds])
        spec=rule['restriction_pattern'];values={}
        for frame in frames:
            if frame.semantic.get('structural_unresolved'):continue
            for tid in frame.argument_token_refs:
                spend()
                if rule.get('head_ref') and tid!=rule['head_ref']:continue
                reading=frame.semantic.get('morph_bindings',{}).get(tid)
                if not reading or reading['pos'] not in spec['head_pos']:continue
                if not rule.get('structural_license') and not any(compatible(v,reading,spec['agreement']) for token in anchors for v in token.variants):continue
                cid='quantifier-head:'+digest([mid,tid,clean(reading)])
                values[cid]={'candidate_id':cid,'head_ref':tid,'reading':clean(reading),
                    'label':rule['operator']+' «'+state.text[bounds[0]:bounds[1]]+'» binds the existing nominal «'+
                        evidence[tid].span+'» at '+str([evidence[tid].start,evidence[tid].end])+
                        '; restriction uses this noun; no individual witness or identity is asserted'}
        if not values or len(values)>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE' if values else 'QUANTIFIER_HEAD_UNRESOLVED',region.region_id)
            return None
        domains[mid]=values;specs[mid]=(bounds,anchors,rule)
    graph=DomainNetwork(domains);ids=list(domains)
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            graph.connect(a,b,lambda x,y:x['head_ref']!=y['head_ref'],'DISTINCT_SOURCE_BINDERS')
    selected={};attempted=set();questions={}
    while len(selected)<len(ids):
        if not graph.propagate(spend):
            state.diag('QUANTIFIER_BINDING_CONFLICT',region.region_id);return None
        signature=digest(graph.snapshot()['domains'])
        pending=[mid for mid in ids if mid not in selected and (mid,signature) not in attempted]
        if not pending:
            state.diag('QUANTIFIER_HEAD_UNRESOLVED',region.region_id);return None
        mid=min(pending,key=lambda m:(len(graph.domains[m]),ids.index(m)))
        options=list(graph.domains[mid].values());attempted.add((mid,signature))
        key=region.region_id+'|quantifier-head:'+digest([mid,options])
        from .component_probe_replay import supersede
        supersede(state,questions.get(mid),key);questions[mid]=key
        rule=specs[mid][2]
        if len(options)==1 and rule.get('head_license'):
            from .structural_tasks import licensed as task_licensed
            from .state import Decision,Ground
            if not task_licensed(state,rule['head_license'],head_ref=options[0]['head_ref']):return None
            chosen=options[0]['candidate_id']
            decision=Decision('nominal_attachment',key,(chosen,),selected=(chosen,),outcome='RESOLVED',
                lifecycle='PROVISIONAL',search_complete=True)
            decision.grounds.append(Ground('D','Selected binder head and its single compatible whole reading; source proof '+rule['head_license']['decision_ref'],chosen))
            state.decisions[key]=decision
        else:
            chosen=_probe(state,selector,release,key,'nominal_attachment',options,
                state.text[slice(*region.source_range)],region.source_range,
                question='The bound nominal is already selected when supplied. Select only its remaining compatible whole reading. '
                         'Do not introduce a named entity, an existential witness or an implicit lexical restriction.')
        if chosen not in graph.domains[mid]:continue
        selected[mid]=(graph.domains[mid][chosen],key)
        graph.restrict(mid,[chosen],'RESOLVED_BINDER_HEAD')
    state.syntax_trace.append({'kind':'QUANTIFIER_BINDING_DOMAIN','region_ref':region.region_id,
                              'constraint_state':graph.snapshot()})
    result={}
    for mid,(value,key) in selected.items():
        bounds,anchors,rule=specs[mid];head=value['head_ref'];reading=value['reading']
        variable=next(i+1 for i,t in enumerate(state.evidence) if t.token_id==anchors[0].token_id)
        uses=[]
        for frame in frames:
            if head in frame.argument_token_refs and not frame.semantic.get('structural_unresolved'):
                frame.semantic.setdefault('bound_arguments',{})[head]=variable;uses.append(frame.frame_id)
        license_use(state,head,reading,key,value['candidate_id'])
        role=rule['restriction_pattern']['role'];token=evidence[head]
        fid='quantifier-restriction:'+digest([mid,value])
        license={'rule':deepcopy(rule),'head_ref':head,'variable':variable,'decision_ref':key,
                 'candidate_id':value['candidate_id'],'marker_refs':[t.token_id for t in anchors]}
        semantic={'proposed_roles':{head:role},'bound_arguments':{head:variable},
            'morph_bindings':{head:reading},'lexical_units':{head:{'head_ref':head,'anchor_refs':[head],
                'surface':token.span,'mention_ref':head}},'quantifier_restriction':license,
            'component_region':region.region_id,'structural_unresolved':False,'proposition_args':{},
            'component_questions':[],'missing_required_roles':[],'uncovered_token_refs':[],
            'preposition_bindings':{},'relative_temporal':[],'requires_attachment_probe':False}
        restriction=FrameCandidate(fid,'FLAT',token.span,(token.span,),(token.span,),
            construction='COMPONENTS_V1',predicate_token_ref=head,argument_token_refs=(head,),
            source_range=tuple(region.source_range),semantic=semantic,
            provenance=ResourceProvenance(('QUANTIFIED_NOMINAL',),{'release':release.sha256}))
        result[mid]={'bounds':bounds,'anchors':[t.token_id for t in anchors],'operator':rule['operator'],
            'body_operator':rule['restriction_pattern']['body_operator'],'variable':variable,
            'restriction':restriction,'required_refs':uses,'head_ref':head}
    return result


def restriction_role(frame,tid):
    """The restriction's argument is a typed binder, not a surface case role."""
    license=frame.semantic.get('quantifier_restriction')
    if not license or license['head_ref']!=tid:return None
    if frame.semantic.get('bound_arguments',{}).get(tid)!=license['variable']:return None
    return license['rule']['restriction_pattern']['role']


def licensed(state,release,frame):
    license=frame.semantic.get('quantifier_restriction')
    if not license:return True
    rule=license['rule'];tid=license['head_ref']
    generic=rule.get('structural_license')
    if generic:
        from .structural_tasks import enabled,licensed as task_licensed
        if not enabled(release) or not task_licensed(state,generic,relation=rule['operator']):return False
        if not task_licensed(state,rule.get('head_license'),head_ref=tid):return False
        if rule['operator'] not in {'FORALL','EXISTS'} or rule.get('head_ref')!=tid:return False
        try:validate_rule(rule,{r['role_id'] for r in release.entries('RoleRegistry')})
        except (ValueError,KeyError,TypeError):return False
        if not task_licensed(state,rule.get('partition_license'),relation=rule['operator'],
                             marker_refs=license['marker_refs'],relation_proof=generic):return False
    elif rule not in release.entries('ScopeLexicon') or 'QUANTIFIED_NOMINAL' not in rule.get('attachment_kinds',()):return False
    decision=state.decisions.get(license['decision_ref'])
    if selected_candidate(decision) is None or license['candidate_id'] not in decision.selected:return False
    evidence={t.token_id:t for t in state.evidence}
    if tid not in evidence or any(t not in evidence for t in license['marker_refs']):return False
    markers=[evidence[t] for t in license['marker_refs']]
    if not markers:return False
    if not generic and not any([t.token_id for t in state.evidence if m.start()<=t.start and t.end<=m.end()]==license['marker_refs']
               for m in re.finditer(rule['pattern'],state.text,re.I)):return False
    reading=frame.semantic.get('morph_bindings',{}).get(tid)
    if not reading or not generic and not any(compatible(v,reading,rule['restriction_pattern']['agreement']) for t in markers for v in t.variants):return False
    from .nominal_readings import attested
    return (attested(state,tid,reading) and frame.predicate_token_ref==tid
        and frame.semantic['proposed_roles']=={tid:restriction_role(frame,tid)}
        and license['variable']==next(i+1 for i,t in enumerate(state.evidence) if t.token_id==markers[0].token_id))
