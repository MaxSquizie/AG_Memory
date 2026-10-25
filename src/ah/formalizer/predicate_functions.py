"""T2 predicative use and open argument roles over complete source domains.

Dictionary POS/case proposals order options; they never close this domain.
Whole readings remain linked and every semantic role requires source evidence.
"""
from .canonical_ledger import digest
from .component_policy import _morph
from .structural_tasks import choose


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


def head(state,release,selector,region,tokens,preferred,cfg):
    from .temporal_functions import owned_refs
    from .nominal_functions import rows
    excluded=owned_refs(state,tokens)|{r for row in rows(state,tokens) for r in row['function_refs'] if r!=row['head_ref']}
    ordered=list(dict.fromkeys([t.token_id for t in preferred]+[t.token_id for t in tokens]))
    evidence={t.token_id:t for t in tokens}
    options=[{'candidate_id':ref,'head_ref':ref,'label':'Predicate occurrence «'+evidence[ref].span+'» @'+str(evidence[ref].start)}
             for ref in ordered if ref not in excluded and any(c.isalnum() for c in evidence[ref].span)]
    options.append({'candidate_id':'NOMINAL','label':'A nominal/event description without a separate predication'})
    result=choose(state,release,selector,region,cfg,'predicate_function',options,
        'Which source occurrence predicates something of participants in this target? Any grammatical form can have predicative use. '
        'Select a nominal description only if there is no separate predication.')
    if not result:return None
    return (evidence[result[0]['head_ref']] if result[0].get('head_ref') else False,result[1])


def binding(state,release,selector,region,tokens,predicate,nominals,groups,cfg,projected=None):
    from .probe_wording import role as role_text,reading as reading_text
    registry=[r['role_id'] for r in release.entries('RoleRegistry')]
    forbidden={projected['rule']['host_role']} if projected else set()
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
            *[{'candidate_id':r,'label':role_text(r)} for r in roles if r not in forbidden],
            {'candidate_id':'NO_DIRECT_ROLE','label':'This occurrence belongs to another nominal or lexical child, not directly to this predicate'}],
            'What role does «'+token.span+'» @'+str(token.start)+' have in predicate «'+predicate.span+'»? '
            'Choose the released valency slot, not every semantic description of the participant. '
            'SUBJECT/OBJECT are core slots after voice projection; a grammatical subject stays SUBJECT even if it feels something. '
            'EXPERIENCER is an oblique/impersonal state participant outside those core slots. Case alone is not proof. '
            'Use SURFACE_ARG only when no more specific role is established.')
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
                'Predicate «'+predicate.span+'»: which whole reading of «'+token.span+'» fits its selected role '+role_text(role)+'? Preserve unknown features.')
            if not reading:return None
            variants=[unique[v['candidate_id']] for v in reading.values]
            if len(variants)>1:reading_domains.append(retain(state,region,predicate,token,role,reading))
        retain_role(state,region,predicate,token,selected,_morph(variants[0]) if len(variants)==1 else None)
        result.append([(role,variant,None) for variant in variants])
    count=1
    for values in result:count*=len(values)
    if count>cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return None
    return BindingDomain([list(values) for values in product(*result)],reading_domains)
