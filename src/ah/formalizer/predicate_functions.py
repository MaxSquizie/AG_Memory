"""T2 predicative use and open argument roles over complete source domains.

Dictionary POS/case proposals order options; they never close this domain.
Whole readings remain linked and every semantic role requires source evidence.
"""
from .canonical_ledger import digest
from .component_policy import _morph
from .structural_tasks import choose


def head(state,release,selector,region,tokens,preferred,cfg):
    from .temporal_functions import owned_refs
    from .nominal_functions import rows
    excluded=owned_refs(state,tokens)|{r for row in rows(state,tokens) for r in row['function_refs']}
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
    result=[]
    for token in nominals:
        if token.token_id in groups:
            result.append((None,None,None));continue  # The relation remains a lexical child.
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
        if role=='NO_DIRECT_ROLE':result.append((None,None,None));continue
        unique={digest({k:v for k,v in _morph(m).items() if k!='score'}):m for m in choices}
        if len(unique)==1:variant=next(iter(unique.values()))
        else:
            reading=choose(state,release,selector,region,cfg,'predicate_argument_reading',[
                {'candidate_id':cid,'label':reading_text(_morph(v))} for cid,v in unique.items()],
                'Predicate «'+predicate.span+'»: which whole reading of «'+token.span+'» fits its selected role '+role_text(role)+'? Preserve unknown features.')
            if not reading:return None
            variant=unique[reading[0]['candidate_id']]
        result.append((role,variant,None))
    return result
