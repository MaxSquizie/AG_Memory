"""Source-grounded partial clauses and closed questions for zero arguments.

No lexical exceptions, invented tokens, model graphs, or first-match identity.
The optional, release-pinned policy licenses grammatical role shapes only.
Uncovered material stays in the IR and blocks assertion of that fragment.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
from itertools import product
import re

from .canonical_ledger import digest
from .state import FrameCandidate, ResourceProvenance, Decision, Ground
from .selection_protocol import DecisionSchema, Relation
from .selector_wire import build_selector_prompt, validate_selector_reply


def policy(release):
    return release.entries('ProposalPolicy')[0].get('composition')


def _features(v):
    return {k: getattr(v, k) for k in ('gender', 'number', 'person') if getattr(v, k)}


def compatible(a, b):
    return all(not a.get(k) or not b.get(k) or a[k] == b[k]
               for k in ('number', 'gender', 'person'))


def _morph(v):
    raw = asdict(v)
    raw['cases'], raw['features'] = sorted(v.cases), sorted(v.features)
    return raw


def _probe(state, selector, release, key, slot, options, context):
    ids = tuple(o['candidate_id'] for o in options)
    d = Decision(slot, key, ids)
    state.decisions[key] = d
    if not ids or state.budget.llm_exhausted:
        d.outcome = 'UNRESOLVED'
        state.diag('COMPUTATION_LIMIT' if ids else 'NO_GROUNDED_CANDIDATE', key)
        return None
    from .clarifications import choice
    chosen = choice(state, key, ids)
    if chosen is not None:
        d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
        d.grounds.append(Ground('C', 'explicit clarification selection', chosen))
        return chosen
    schema = DecisionSchema(release.sha256, {
        o['candidate_id']: Relation(o['candidate_id'], o['label'], 0, (), o['label']) for o in options})
    prompt = build_selector_prompt(selector, slot_id=slot, frame_id=key,
        context_span=context, mentions={}, schema=schema, candidates=ids,
        contextual_statements=())
    try:
        state.budget.spend_llm()
        raw = selector.select(prompt)
        reply = validate_selector_reply(selector, raw, schema, ids, allowed=frozenset(ids))
        d.last_prompt, d.raw_response, d.selector_outcome = prompt, raw, reply.outcome
    except Exception as exc:
        d.outcome = 'UNRESOLVED'
        state.diag('COMPONENT_PROBE_FAILED', type(exc).__name__)
        return None
    if reply.outcome != 'ONE_SELECTED':
        d.outcome = 'INSUFFICIENT_CONTEXT' if reply.outcome == 'INSUFFICIENT_CONTEXT' else 'UNRESOLVED'
        from .clarifications import offer
        offer(state,key,'COMPONENT' if slot=='component_attachment' else 'IMPLICIT_ARGUMENT',context,options)
        return None
    chosen = reply.selected[0]
    d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
    d.grounds.append(Ground('M', 'closed source-grounded component question', chosen))
    return chosen


def compose(state, release, selector):
    """Build finite-clause alternatives including missing subject slots.

    First slice deliberately cannot assert coordination/control or infer the
    semantics of an arbitrary adjunct. Those become uncovered components, not
    silently discarded words. Existing complete SyntaxRules frames take priority
    as coverage, not as lexical winners over a newly guessed analysis.
    """
    cfg = policy(release)
    if not cfg:
        return
    state.require_structures_open('COMPONENT_COMPOSITION')
    evidence = {e.token_id:e for e in state.evidence}
    covered = {f.predicate_token_ref for f in state.frames}
    from .regions import protected_intervals
    protected_ranges=protected_intervals(state.text)
    for region in state.region_forest.regions:
        if region.kind != 'SENTENCE':
            continue
        tokens = [evidence[t] for t in region.token_refs]
        predicates = [e for e in tokens if any(v.pos == 'VERB' and v.mood != 'imperative' for v in e.variants)]
        # A multi-predicate region needs a licensed attachment/coordination.
        if len(predicates) != 1 or predicates[0].token_id in covered:
            continue
        p = predicates[0]
        raw = state.text[region.source_range[0]:region.source_range[1]]
        # Never flatten a scoped region into an asserted finite clause.
        protected = any(lo <= p.start < hi for lo,hi in protected_ranges)
        scope = protected or any(re.search(r['pattern'], raw, re.I) for r in release.entries('ScopeLexicon'))
        scope |= any(e.span in {'«','»','"','(',')','?',':'} for e in tokens)
        if scope:
            state.diag('COMPONENT_SCOPE_UNRESOLVED', region.region_id)
            continue
        temporal = set()
        for rule in release.entries('TemporalRules'):
            for m in re.finditer(rule['pattern'],raw,re.I):
                lo,hi = region.source_range[0]+m.start(),region.source_range[0]+m.end()
                temporal.update(e.token_id for e in tokens if lo <= e.start and e.end <= hi)
        prep_objects=set()
        after_prep=False
        for token in tokens:
            if any(v.pos=='PREP' for v in token.variants):
                after_prep=True
            elif after_prep and any(v.pos in {'NOUN','NPRO'} for v in token.variants):
                prep_objects.add(token.token_id); after_prep=False
            elif not any(v.pos=='ADJF' for v in token.variants):
                after_prep=False
        allowed_cases=set(cfg['open_case_roles']) | {c for val in release.entries('R-V') for role in val['roles'] for c in role.get('allowed_cases',())}
        nominals = [e for e in tokens if e.token_id not in temporal|prep_objects and e != p
                    and any(v.pos in {'NOUN','NPRO'} and set(v.cases)&allowed_cases for v in e.variants)]
        # No arbitrary truncation of the argument candidate inventory.
        if len(nominals) > 3:
            state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
            continue
        alternatives = {}
        for pv in p.variants:
            if pv.pos != 'VERB' or pv.mood == 'imperative':
                continue
            senses = [s for s in release.entries('R-S') if s['lemma'] == pv.lemma and s['POS'] == pv.pos and not s.get('anchor_pattern')]
            vals = [v for v in release.entries('R-V') if v['sense_id'] in {s['sense_id'] for s in senses}]
            if senses and not vals:
                state.diag('VALENCY_UNKNOWN', p.token_id)
                continue
            if not senses and not release.entries('OpenTemplatePolicy')[0]['allow']:
                continue
            shapes = vals if senses else [None]
            for val in shapes:
                if val and any(set(r.get('argument_types',())) != {'ENTITY'} or r.get('allowed_preps')
                               or r.get('cardinality',{}).get('max') != 1 for r in val['roles']):
                    continue
                roles = val['roles'] if val else [
                    {'role_id':r,'allowed_cases':[c for c,r2 in cfg['open_case_roles'].items() if r2==r],
                     'cardinality':{'min':int(r==cfg['subject_role'])}}
                    for r in sorted(set(cfg['open_case_roles'].values()) | {cfg['subject_role']})]
                variants = []
                for e in nominals:
                    choices = []
                    for mv in e.variants:
                        if mv.pos not in {'NOUN','NPRO'}:
                            continue
                        for role in roles:
                            if not set(mv.cases)&set(role.get('allowed_cases',())):
                                continue
                            if role['role_id']==cfg['subject_role'] and not compatible(_features(pv),_features(mv)):
                                continue
                            choices.append((role['role_id'],mv))
                    variants.append(choices)
                count = 1
                for choices in variants: count *= len(choices)
                if count > 256:
                    state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
                    alternatives.clear()
                    break
                for binding in product(*variants):
                    rs=[r for r,v in binding]
                    if len(set(rs))!=len(rs): continue
                    missing={r['role_id'] for r in roles if r.get('cardinality',{}).get('min',0)>0}-set(rs)
                    if missing-{cfg['subject_role']}: continue
                    # The optional rule licenses only subject ellipsis.
                    gap = cfg['subject_role'] in missing
                    if gap and pv.number not in {'sing','plur'}: continue
                    used={p.token_id,*temporal,*(e.token_id for e in nominals)}
                    units={e.token_id:{'head_ref':e.token_id,'anchor_refs':[e.token_id],
                            'surface':e.span,'mention_ref':e.token_id} for e in nominals}
                    # Adjacent agreeing adjectives belong to the noun unit;
                    # they are never independent entity actants.
                    for e,(_,mv) in zip(nominals,binding):
                        idx=tokens.index(e)-1
                        while idx>=0:
                            adj=tokens[idx]
                            if adj.token_id in used or not any(av.pos=='ADJF' and compatible(_features(av),_features(mv))
                                    and set(av.cases)&set(mv.cases) for av in adj.variants): break
                            used.add(adj.token_id); units[e.token_id]['anchor_refs'].insert(0,adj.token_id); idx-=1
                        anchors=[evidence[t] for t in units[e.token_id]['anchor_refs']]
                        units[e.token_id]['surface']=state.text[anchors[0].start:e.end]
                        if len(anchors)>1: units[e.token_id]['mention_ref']='mention:'+digest(units[e.token_id]['anchor_refs'])
                    uncovered=[e.token_id for e in tokens if e.token_id not in used and e.span not in {'.','!'}]
                    mapping={e.token_id:r for e,(r,v) in zip(nominals,binding)}
                    morph={p.token_id:_morph(pv),**{e.token_id:_morph(v) for e,(_,v) in zip(nominals,binding)}}
                    # Scores order search, never distinguish semantic choices.
                    canonical={t:{k:v for k,v in m.items() if k!='score'} for t,m in morph.items()}
                    key=digest([region.region_id,mapping,canonical,gap,uncovered])
                    fid='component:'+key
                    questions=[{'kind':'WHAT_EVENT','anchor_ref':p.token_id}]
                    if gap: questions.append({'kind':'WHO','gap_id':'gap:'+digest([fid,cfg['subject_role']]),'role':cfg['subject_role']})
                    questions.extend({'kind':'UNRESOLVED_COMPONENT','token_ref':tid} for tid in uncovered)
                    semantic={'proposed_roles':mapping,'morph_bindings':morph,'lexical_units':units,
                        'component_questions':questions,'uncovered_token_refs':uncovered,
                        'structural_unresolved':bool(uncovered),'component_region':region.region_id}
                    if gap:
                        semantic['implicit_arguments']={cfg['subject_role']:{'gap_id':questions[1]['gap_id'],
                            'features':_features(pv),'predicate_ref':p.token_id,'options':[]}}
                    alternatives[key]=FrameCandidate(fid,'FLAT',p.span,
                        tuple([p.span,*[e.span for e in nominals]]),tuple(e.span for e in nominals),
                        construction='COMPONENTS_V1',predicate_token_ref=p.token_id,
                        argument_token_refs=tuple(e.token_id for e in nominals),source_range=tuple(region.source_range),
                        semantic=semantic,provenance=ResourceProvenance(('COMPONENTS_V1',),{'release':release.sha256}))
        candidates=list(alternatives.values())
        if not candidates: continue
        if len(candidates)>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
            for f in candidates: f.semantic['structural_unresolved']=True
        elif len(candidates)>1:
            options=[]
            for f in candidates:
                roles=', '.join(r+'='+evidence[t].span for t,r in f.semantic['proposed_roles'].items())
                if f.semantic.get('implicit_arguments'): roles += '; subject omitted (identity unresolved)'
                options.append({'candidate_id':f.frame_id,'label':str(f.semantic['morph_bindings'][p.token_id]['lemma'])+'; '+roles+'; morphology='+str({t:{k:v for k,v in m.items() if k in {'cases','number','gender','pos'}} for t,m in f.semantic['morph_bindings'].items()})})
            if len(raw)>cfg['context_chars'] or all(f.semantic['uncovered_token_refs'] for f in candidates):
                chosen=None
            else:
                chosen=_probe(state,selector,release,region.region_id+'|composition','component_attachment',options,raw)
            for f in candidates:
                f.semantic['composition_decision']=region.region_id+'|composition'
                if f.frame_id!=chosen: f.semantic['structural_unresolved']=True
        state.frames.extend(candidates)
        state.syntax_trace.append({'composition_region':region.region_id,
            'candidates':[f.frame_id for f in candidates], 'coverage':'PARTIAL' if any(f.semantic['uncovered_token_refs'] for f in candidates) else 'COMPLETE'})


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
            group=[a.frame_id for a in state.frames if a.semantic.get('composition_decision')==f.semantic['composition_decision']]
            selected=choice(state,f.semantic['composition_decision'],group)
            if selected is not None:
                f.semantic['structural_unresolved']=f.frame_id!=selected or bool(f.semantic['uncovered_token_refs'])
        for role,gap in ({} if f.semantic.get('structural_unresolved') else f.semantic.get('implicit_arguments',{})).items():
            plural=gap['features'].get('number')=='plur'
            options=[]
            # A source centre is a hypothesis, never author/user identity.
            if not plural:
                options.append({'candidate_id':'narrative-centre','kind':'ANONYMOUS',
                    'entity_ref':'M:implicit:'+digest([source,'narrative-centre']),
                    'label':'Unidentified singular narrative centre of this source; NOT necessarily its author or uploader',
                    'participant_kind':'INDIVIDUAL'})
            options.append({'candidate_id':'new:'+gap['gap_id'],'kind':'ANONYMOUS',
                'entity_ref':'M:implicit:'+digest([source,gap['gap_id']]),
                'participant_kind':'GROUP' if plural else 'INDIVIDUAL',
                'label':'New unidentified group, plural, membership UNKNOWN (do not infer narrator or previous object as members)' if plural else 'Another unidentified individual; no identity with previous mentions established'})
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
        for tid in f.argument_token_refs:
            unit=f.semantic.get('lexical_units',{}).get(tid,{})
            mention=unit.get('mention_ref',tid); ev=evidence[tid]
            variants=[v for v in ev.variants if v.pos=='NOUN']
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
            chosen=_probe(state,selector,release,gap['gap_id'],'implicit_argument',options,state.text[lo:hi])
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
