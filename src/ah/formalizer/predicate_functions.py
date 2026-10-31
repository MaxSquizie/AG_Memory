"""T2 predicative use and open argument roles over complete source domains.

Dictionary POS/case proposals order options; they never close this domain.
Whole readings remain linked and every semantic role requires source evidence.
"""
from .canonical_ledger import digest
from .component_policy import _morph
from .structural_tasks import choose
from .probe_prerequisites import accepted


def subject_presence(state,release,selector,region,predicate,variant,nominals,binding,cfg):
    """An open predicate's explicit arguments do not close omitted slots.

    This task runs after occurrence roles, before frame construction. It only
    establishes whether a subject is understood; reference resolution still
    owns its identity. Morphology licenses agreement, not personal use itself.
    """
    from .probe_wording import reading as reading_text,role as role_text
    roles={t.token_id:r for t,(r,_,_) in zip(nominals,binding) if r}
    common={'predicate_ref':predicate.token_id,'predicate_reading':_morph(variant),'roles':roles}
    result=choose(state,release,selector,region,cfg,'predicate_subject_presence',[
        {'candidate_id':'OMITTED','omitted':True,**common,
         'label':'An understood subject is omitted from this target; preserve a participant slot whose identity remains to be resolved'},
        {'candidate_id':'ABSENT','omitted':False,**common,
         'label':'This use has no subject participant; do not invent one (for example an impersonal predication)'}],
        'Predicate «'+predicate.span+'»: '+reading_text(_morph(variant))+'. '
        'Already established explicit participants: '+('; '.join('«'+t.span+'»='+role_text(roles[t.token_id])
            for t in nominals if t.token_id in roles) or 'none')+'. '
        'None is the subject. Does this use still have an understood subject, or is there no subject slot? '
        'Context may identify an omitted subject, but do not choose its identity here. '
        'Do not replace an established explicit role or use agreement alone to infer personal meaning. Use ? if undecidable.')
    if result:
        from .structural_tasks import licensed
        if licensed(state,result[1],**common,omitted=result[0]['omitted']):return result
    return None


def head(state,release,selector,region,tokens,preferred,cfg,*,request=None):
    from .temporal_functions import owned_refs
    from .nominal_functions import rows
    excluded=owned_refs(state,tokens)|{r for row in rows(state,tokens) for r in row['function_refs'] if r!=row['head_ref']}
    ordered=list(dict.fromkeys([t.token_id for t in preferred]+[t.token_id for t in tokens]))
    evidence={t.token_id:t for t in tokens}
    route=cfg.get('_lexical_route')
    # The parent already selected these occurrences as predicates taking
    # content. In a proven single-predication region, its sole required owner
    # is therefore the head. Neither morphology nor a singleton search is the
    # evidence. A nested region cannot inherit another region's route proof.
    if route is not None and route.region_ref==region.region_id and request:
        route.validate(state,region,tokens)
        owners={ref for ref,roles in (request.pending_propositions or {}).items() if roles and ref in evidence}
        owners.update(ref for ref,slots in (request.proposition_slots or {}).items() if slots and ref in evidence)
        if owners:
            from .composition_session import current
            from .composition_dispatcher import canonical
            runtime=current(state)
            basis=canonical({'owner_refs':sorted(owners),'route_proof':route.proof,
                   'input_scope':runtime.input_signature() if runtime else None,
                   'pending_propositions':request.pending_propositions,
                   'proposition_slots':request.proposition_slots})
            if len(owners)!=1 or owners & excluded:
                from .composition_contracts import record_failure
                record_failure(state,region,'HYPOTHESIS_CONFLICT',route.proof,
                    'The single-predication route cannot satisfy the established content owners and occurrence functions.',
                    {**basis,'excluded_owner_refs':sorted(owners & excluded)},search_complete=False)
                state.diag('LEXICAL_ROUTE_CONFLICT',region.region_id)
                return None
            ref=next(iter(owners))
            proof={'kind':'CONTENT_OWNER_HEAD','head_ref':ref,**basis}
            state.syntax_trace.append({**proof,'kind':'PREDICATE_HEAD_DERIVED','region_ref':region.region_id,
                'source_range':list(region.source_range),'derivation':'ONE_PREDICATION_WITH_ESTABLISHED_CONTENT_OWNER'})
            return evidence[ref],proof
    options=[{'candidate_id':ref,'head_ref':ref,'label':'Predicate occurrence «'+evidence[ref].span+'» @'+str(evidence[ref].start)}
             for ref in ordered if ref not in excluded and any(c.isalnum() for c in evidence[ref].span)]
    options.append({'candidate_id':'NOMINAL','label':'A nominal/event description without a separate predication'})
    result=choose(state,release,selector,region,cfg,'predicate_function',options,
        'Which source occurrence predicates something of participants in this target? Any grammatical form can have predicative use. '
        'Select a nominal description only if there is no separate predication.')
    if not result:return None
    return (evidence[result[0]['head_ref']] if result[0].get('head_ref') else False,result[1])


def binding(state,release,selector,region,tokens,predicate,nominals,groups,cfg,projected=None,*,reserved_roles=()):
    from .probe_wording import role as role_text,reading as reading_text
    registry=[r['role_id'] for r in release.entries('RoleRegistry')]
    forbidden=set(reserved_roles)|({projected['rule']['host_role']} if projected else set())
    from .partial_readings import BindingDomain,retain
    from itertools import product
    result=[];reading_domains=[]
    for token in nominals:
        if token.token_id in groups:
            result.append([(None,None,None)]);continue  # The relation remains a lexical child.
        choices=[v for v in token.variants if v.pos in {'NOUN','NPRO'}]
        if not choices:return None
        priorities=[cfg['open_case_roles'][c] for v in choices for c in sorted(v.cases) if c in cfg['open_case_roles']]
        roles=list(dict.fromkeys([*priorities,*registry]))
        # A catch-all role is an explicit last option, not a semantic prior.
        roles=[r for r in roles if r!='SURFACE_ARG']+(['SURFACE_ARG'] if 'SURFACE_ARG' in roles else [])
        selected=choose(state,release,selector,region,cfg,'predicate_argument_role',[
            *[{'candidate_id':r,'label':role_text(r),'predicate_ref':predicate.token_id,
               'token_ref':token.token_id,'reserved_roles':sorted(forbidden)} for r in roles if r not in forbidden],
            {'candidate_id':'NO_DIRECT_ROLE','predicate_ref':predicate.token_id,'token_ref':token.token_id,
             'reserved_roles':sorted(forbidden),
             'label':'This occurrence belongs to another nominal or lexical child, not directly to this predicate'}],
            'What role does «'+token.span+'» @'+str(token.start)+' have in predicate «'+predicate.span+'»? '
            'Choose the released valency slot, not every semantic description of the participant. '
            'SUBJECT/OBJECT are core slots after voice projection; a grammatical subject stays SUBJECT even if it feels something. '
            'EXPERIENCER is an oblique/impersonal state participant outside those core slots. Case alone is not proof. '
            'Use SURFACE_ARG only when no more specific role is established.'+
            (' Already supplied by this predicate\'s accepted input contract and unavailable to a different argument: '+
             '; '.join(role_text(r) for r in sorted(forbidden))+'. These restrictions do not apply to other predicates.' if forbidden else ''))
        if not selected:return None
        role=selected[0]['candidate_id']
        from .component_constraints import retain_role
        if role=='NO_DIRECT_ROLE':
            retain_role(state,region,predicate,token,selected)
            result.append([(None,None,None)]);continue
        unique={digest({k:v for k,v in _morph(m).items() if k!='score'}):m for m in choices}
        if len(unique)==1:variants=list(unique.values())
        else:
            from .structural_tasks import choose_domain
            from .morphology_domain import clean
            reading=choose_domain(state,release,selector,region,cfg,'predicate_argument_reading',[
                {'candidate_id':cid,'reading':clean(v),'token_ref':token.token_id,'predicate_ref':predicate.token_id,
                 'role':role,'label':reading_text(_morph(v))} for cid,v in unique.items()],
                'Predicate «'+predicate.span+'» @'+str(predicate.start)+': which whole reading of «'+token.span+'» @'+str(token.start)+' fits its selected role '+role_text(role)+'? Preserve unknown features.',
                prerequisites=(accepted('predicate_argument_role',selected),))
            if not reading:return None
            variants=[unique[v['candidate_id']] for v in reading.values]
            reading_domains.append(retain(state,region,predicate,token,role,reading))
        retain_role(state,region,predicate,token,selected)
        result.append([(role,variant,None) for variant in variants])
    count=1
    for values in result:count*=len(values)
    if count>cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
    return BindingDomain([list(values) for values in product(*result)],reading_domains)
