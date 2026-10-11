"""Prepare/freeze and resolve omitted participants through addressable choices."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_policy import policy, compatible, _features
from .component_probe import _probe

def prepare_implicit(state, release):
    """Freeze finite candidate sets, including local unresolved chain anchors."""
    cfg=policy(release)
    if not cfg: return
    state.require_structures_open('IMPLICIT_ARGUMENTS')
    evidence={e.token_id:e for e in state.evidence}
    source=state.observation.get('source_id') or state.source_uid
    previous=[]
    for f in sorted(state.frames,key=lambda f:(f.source_range,f.frame_id)):
        if f.semantic.get('composition_decision'):
            from .clarifications import choice
            group=list(dict.fromkeys(a.semantic.get('composition_bundle_root',a.frame_id) for a in state.frames if a.semantic.get('composition_decision')==f.semantic['composition_decision']))
            selected=choice(state,f.semantic['composition_decision'],group)
            if selected is not None:
                f.semantic['structural_unresolved']=f.semantic.get('composition_bundle_root',f.frame_id)!=selected or bool(f.semantic['uncovered_token_refs'] or f.semantic.get('missing_required_roles'))
        for role,gap in ({} if f.semantic.get('structural_unresolved') else f.semantic.get('implicit_arguments',{})).items():
            plural=gap['features'].get('number')=='plur'
            options=[]
            # A narrative-centre hypothesis is not a second person. Before any
            # identity is established there is one anonymous introduction for
            # this gap; continuity must be selected through CHAIN or MEMORY.
            options.append({'candidate_id':'new:'+gap['gap_id'],'kind':'ANONYMOUS',
                'entity_ref':'M:implicit:'+digest([source,gap['gap_id']]),
                'participant_kind':'GROUP' if plural else 'INDIVIDUAL',
                'label':'Unidentified group for this clause, membership UNKNOWN; no antecedent established (do not infer narrator or previous object as members)' if plural else 'Unidentified subject of this clause; no antecedent established. Does not identify the author/uploader or assert difference from other participants'})
            for earlier in previous:
                if earlier['end']>f.source_range[0] or f.source_range[0]-earlier['end']>cfg['context_chars']: continue
                if not compatible(gap['features'],earlier['features']): continue
                options.append({**earlier,'candidate_id':earlier['key'],
                    'label':'Same participant as '+earlier['label']+' (identity requires contextual evidence)'})
            # Equal entities from different paths remain one choice with unioned grounds.
            merged={}
            for opt in options:
                key=opt['candidate_id']
                if key in merged:
                    merged[key]['premise_support_refs']=sorted(set(merged[key].get('premise_support_refs',()))|set(opt.get('premise_support_refs',())))
                else: merged[key]=opt
            gap['options']=list(merged.values())
            gap['context_range']=[max(0,f.source_range[0]-cfg['context_chars']//2),f.source_range[1]]
            if len(gap['options'])>cfg['max_candidates'] or gap['context_range'][1]-gap['context_range'][0]>cfg['context_chars']:
                gap['search_incomplete']=True
            previous.append({'key':gap['gap_id'],'kind':'CHAIN','gap_ref':gap['gap_id'],
                'features':gap['features'],'end':f.source_range[1],
                'label':'omitted '+role+' at '+str(f.source_range)+' ('+f.anchor_span+')'})
        # Rejected whole-clause alternatives must not leak their hypothetical
        # noun readings into later reference choices (e.g. a preposition as M).
        decision=state.decisions.get(f.semantic.get('composition_decision'))
        if decision and decision.outcome=='RESOLVED' and f.semantic.get('composition_bundle_root',f.frame_id) not in decision.selected:
            continue
        for tid in f.argument_token_refs:
            unit=f.semantic.get('lexical_units',{}).get(tid,{})
            mention=unit.get('mention_ref',tid); ev=evidence[tid]
            if f.semantic.get('structural_unresolved') and any(v.pos!='NOUN' for v in ev.variants):
                continue
            selected_morph=f.semantic.get('morph_bindings',{}).get(tid)
            variants=[v for v in ev.variants if v.pos=='NOUN' and (not selected_morph or
                all(getattr(v,k)==selected_morph.get(k) for k in ('lemma','pos','number','gender')))]
            if not variants: continue  # pronoun resolution has its own closed question
            features=[_features(v) for v in variants]
            common={k:features[0][k] for k in features[0] if all(x.get(k)==features[0][k] for x in features)}
            previous.append({'key':'mention:'+mention,'kind':'MENTION','mention_ref':mention,
                'entity_ref':state.observation.get('entity_bindings',{}).get(mention) or 'M:'+digest([state.source_uid,mention]),
                'anchor_label':unit.get('surface',ev.span), 'features':common,'end':f.source_range[1],'label':unit.get('surface',ev.span)})


def resolve_implicit(state, release, selector):
    if not policy(release): return
    resolved=state.observation['implicit_bindings']={}
    for f in sorted(state.frames,key=lambda f:(f.source_range,f.frame_id)):
        for role,gap in f.semantic.get('implicit_arguments',{}).items():
            if f.semantic.get('structural_unresolved') or gap.get('search_incomplete'):
                state.diag('IMPLICIT_ARGUMENT_UNRESOLVED',gap['gap_id']); continue
            options=gap['options']
            lo,hi=gap['context_range']
            targets={o['candidate_id']:(resolved.get(o.get('gap_ref'),{}).get('entity_ref')
                if o['kind']=='CHAIN' else o.get('entity_ref')) for o in options}
            chosen=_probe(state,selector,release,gap['gap_id'],'implicit_argument',options,state.text[lo:hi],f.source_range,
                          equivalent_targets=targets,
                          question=('Resolve the omitted '+role+' of the TARGET clause below, not of another clause in the context.\n'
                            +'Target clause: '+state.text[slice(*f.source_range)]+'\n'
                            +'Target predicate: '+f.anchor_span+'; source range: '+str(f.source_range)+'\n'
                            +'Grammatical features of omitted participant: '+str(gap['features'])+'\n'
                            +'Use the preceding source context to choose a reference. An unidentified person can still be the same participant as an earlier omitted subject. '
                            +'Compatibility alone does not establish identity; retain insufficient context when evidence is insufficient.'))
            if chosen is None: continue
            opt=next(o for o in options if o['candidate_id']==chosen)
            if opt['kind']=='CHAIN':
                target=resolved.get(opt['gap_ref'])
                if target is None:
                    state.diag('IMPLICIT_CHAIN_UNRESOLVED',gap['gap_id']); continue
                value=deepcopy(target)
            else:
                value={k:deepcopy(v) for k,v in opt.items() if k in {'entity_ref','participant_kind','premise_support_refs'}}
                if opt['kind']=='MEMORY':
                    value['premise_support_refs']=list(min(tuple(path) for path in opt['grounding_paths']))
                value['anonymous']=opt['kind']=='ANONYMOUS'
                if opt['kind']=='MENTION': value['label']=opt['anchor_label']; value['anchor_mention']=opt['mention_ref']
            if any(v['entity_ref']==value['entity_ref'] and not compatible(v['features'],gap['features']) for v in resolved.values()):
                state.diag('IMPLICIT_CHAIN_FEATURE_CONFLICT',gap['gap_id']); continue
            value['decision_ref']=gap['gap_id']
            value['features']=gap['features']
            resolved[gap['gap_id']]=value


def add_memory_options(gap, rows, release):
    by_id={o['candidate_id']:o for o in gap['options']}
    for row in rows:
        if row.get('reference_kind')=='EVENT': continue
        features=row.get('features',())
        if features and not any(compatible(gap['features'],v) for v in features): continue
        cid='memory:'+row['entity_ref']
        old=by_id.get(cid,{})
        paths={tuple(path) for path in old.get('grounding_paths',())}
        paths.add(tuple(sorted(row['premise_support_refs'])))
        by_id[cid]={'candidate_id':cid,'kind':'MEMORY','entity_ref':row['entity_ref'],
            'label':'Memory participant '+row['label'],
            'grounding_paths':[list(path) for path in sorted(paths)]}
    gap['options']=list(by_id.values())
    if len(gap['options'])>policy(release)['max_candidates']: gap['search_incomplete']=True
