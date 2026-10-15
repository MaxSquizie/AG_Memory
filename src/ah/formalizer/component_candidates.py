"""Bounded whole-morphology/role joins for a single finite clause."""
from itertools import product
from copy import deepcopy
from .canonical_ledger import digest
from .state import FrameCandidate, ResourceProvenance
from .component_policy import _features, _morph
from .component_phrases import role_choices, nominal_units, phrase_questions
from .component_omissions import licensed_gaps


def enumerate_candidates(state, release, cfg, region, tokens, p, temporal, nominals, groups, *, selector=None, attachment=None, nominal_groups=(), infinitive=None,proposition_slots=None,agreement_source=None,pending_roles=(),qualitative_groups=()):
    alternatives = {}
    grouped={t for g in nominal_groups for t in g["member_refs"]}
    connectors={t for g in nominal_groups for t in g["marker_refs"]}
    governors=[v for v in agreement_source.variants if v.pos=='ADJS' or v.pos=='VERB' and v.mood!='imperative'] if agreement_source else [None]
    for pv,gv in product(p.variants,governors):
        from .participial_roles import projection
        projected = projection(pv, attachment, cfg)
        controlled=infinitive is not None and pv.pos=='INFN'
        governed=gv is not None and pv.pos=='INFN'
        if gv is not None and not governed:continue
        agreement=gv or pv
        if infinitive is not None and not controlled:continue
        quality = pv.pos in cfg.get('quality_predicate_pos', ())
        from .component_predication import nominal_predicate
        nominal=nominal_predicate(pv,cfg)
        if nominal:
            # A noun's lexical gender/number is not subject agreement.
            from dataclasses import replace
            agreement=replace(pv,gender=None,number=None,person=None)
        if attachment and projected is None: continue
        if not projected and not controlled and not governed and not quality and not nominal and (pv.pos != 'VERB' or pv.mood == 'imperative'): continue
        if quality and pv.pos == 'ADJF' and 'nom' not in pv.cases: continue
        senses = [s for s in release.entries('R-S') if not p.is_oov() and s['lemma'] == pv.lemma and s['POS'] == pv.pos and not s.get('anchor_pattern')]
        vals = [v for v in release.entries('R-V') if v['sense_id'] in {s['sense_id'] for s in senses}]
        if senses and not vals:
            state.diag('VALENCY_UNKNOWN', p.token_id); continue
        if not senses and not release.entries('OpenTemplatePolicy')[0]['allow']: continue
        shapes = vals if senses else [None]
        for val in shapes:
            supplied=deepcopy(proposition_slots or {})
            reserved=set(pending_roles)
            if val:reserved &= {r['role_id'] for r in val['roles'] if set(r.get('argument_types',())) & {'PROPOSITION','EVENT'}}
            if any(not any(a['lemma']==pv.lemma and a['argument_role']==role and a['attitude']==arg['attitude']
                           for a in release.entries('AttitudeMap')) for role,arg in supplied.items()):continue
            if val and (not set(supplied)<={r['role_id'] for r in val['roles']} or any(
                (not set(r.get('argument_types',())) & {'PROPOSITION','EVENT'} if r['role_id'] in set(supplied)|reserved
                 else set(r.get('argument_types',())) != {'ENTITY'})
                or r.get('cardinality',{}).get('max') != 1 for r in val['roles'])): continue
            case_roles = {c:r for c,r in (projected['rule']['case_roles'] if projected else cfg['open_case_roles']).items() if not (quality or nominal) or (c == 'nom' and r == cfg['subject_role'])}
            roles = val['roles'] if val else [
                {'role_id':r,'allowed_cases':[c for c,r2 in case_roles.items() if r2==r],
                 'cardinality':{'min':int(r==cfg['subject_role'] and (not projected or bool(projected.get('relative_marker')) and projected['rule']['host_role']!=r))}}
                for r in sorted(set(case_roles.values()) | {cfg['subject_role']})]
            if projected and projected.get('relative_marker') and val:
                marker_cases=projected['marker_reading'].cases
                if not any(r['role_id']==projected['rule']['host_role'] and marker_cases & set(r.get('allowed_cases',())) and not r.get('allowed_preps') for r in roles):
                    continue
            if projected:
                roles = [r for r in roles if r['role_id'] != projected['rule']['host_role']]
            pending_required={r['role_id'] for r in roles if r['role_id'] in reserved and r.get('cardinality',{}).get('min',0)>0}
            roles=[r for r in roles if r['role_id'] not in set(supplied)|reserved
                   and not (controlled and r['role_id']==cfg['subject_role'])]
            reduction=None
            # Released time syntax owns its colon and numeric readings; these
            # are not apposition markers or attributes of a nominal argument.
            dependency_tokens=[e for e in tokens if e.token_id not in temporal]
            from .morphology_domain import proposed
            needs_reduction=any(proposed(_morph(v)) for e in nominals for v in e.variants) or bool(qualitative_groups) or len(nominals)>3 or cfg.get('dependency_reduction') and (any(
                e.token_id not in groups and e.token_id not in grouped and any(v.pos in {'NOUN','NPRO'} and set(v.cases)&({'gen'}|set(cfg.get('nominal_dependency_cases',()))) for v in e.variants)
                for e in nominals) or any(e.span in cfg.get('apposition_markers',()) for e in dependency_tokens))
            if needs_reduction:
                from .component_dependency_reduction import reduce
                reduction=reduce(state,release,selector,region,dependency_tokens,p,agreement,roles,nominals,groups,cfg,quantities=qualitative_groups,nominal_groups=nominal_groups)
                if reduction is None: continue
            variants = [role_choices(e,roles,agreement,cfg['subject_role'],groups.get(e.token_id),coordinated=e.token_id in grouped) for e in nominals]
            if reduction is not None:
                variants=[[reduction['roots'].get(e.token_id,(None,None,None))] for e in nominals]
            count = 1
            for choices in variants: count *= len(choices)
            if count > cfg['max_candidates']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
                # Never retain a previous valency prefix as a complete search.
                return []
            for binding in product(*variants):
                assignments=[(e,b) for e,b in zip(nominals,binding) if b[0] is not None]
                rs=[b[0] for e,b in assignments]
                from .component_nominal_groups import valid_roles
                if not valid_roles({e.token_id:b[0] for e,b in assignments},nominal_groups):continue
                if any(not set(g['cases']).intersection(*(set(b[1].cases) for e,b in assignments if e.token_id in g['member_refs'])) for g in nominal_groups):continue
                missing={r['role_id'] for r in roles if r.get('cardinality',{}).get('min',0)>0}-set(rs)
                gaps = licensed_gaps(roles,missing,agreement,cfg,quality=quality or nominal,valency=val)
                if projected and 'pssv' in pv.features:
                    # Passive agreement describes the patient, never licenses
                    # an omitted agent with the patient's number/gender.
                    gaps.pop(cfg['subject_role'],None)
                unresolved_roles=sorted(missing-set(gaps)-({cfg['subject_role']} if controlled else set()))
                used={p.token_id,*temporal,*connectors,*(e.token_id for e,b in assignments)}
                units=nominal_units(state,tokens,assignments,used)
                preps={}
                morph={p.token_id:_morph(pv)}
                if gv is not None:morph[agreement_source.token_id]=_morph(gv)
                for e,(_,mv,prep) in assignments:
                    morph[e.token_id]=_morph(mv)
                    if prep:
                        group=groups[e.token_id]; used.add(group['token_ref'])
                        preps[e.token_id]={'token_ref':group['token_ref'],'lemma':prep.lemma}
                        morph[group['token_ref']]=_morph(prep)
                from .component_predication import consume_copula
                copula = consume_copula(tokens, p, pv, cfg, used, morph) if quality else None
                if nominal:
                    subjects=[(e,mv) for e,(r,mv,_) in assignments if r==cfg['subject_role']]
                    if len(subjects)!=1:continue
                    subject,subject_reading=subjects[0]
                    copula=consume_copula(tokens,p,subject_reading,cfg,used,morph)
                    if 'nom' not in pv.cases and not copula:continue
                    lo,hi=sorted((subject.start,p.start))
                    used.update(t.token_id for t in tokens if lo<t.start<hi and t.span in {'—','–','-'})
                deps=reduction['dependencies'] if reduction else []
                used.update(d['head_ref'] for d in deps)
                used.update(d['marker_ref'] for d in deps if d.get('marker_ref'))
                uncovered=[e.token_id for e in tokens if e.token_id not in used and e.span not in {'.','!'}]
                ambiguous=any(g['ambiguous_pos'] for g in groups.values())
                mapping={e.token_id:r for e,(r,_,_) in assignments}
                canonical={t:{k:v for k,v in m.items() if k!='score'} for t,m in morph.items()}
                key_parts=[region.region_id,mapping,canonical,gaps,uncovered,unresolved_roles,deps,nominal_groups,infinitive,supplied,sorted(reserved)]
                if projected: key_parts.append([projected['host'].token_id,projected['rule']])
                if reduction:key_parts.append(reduction['group_readings'])
                key=digest(key_parts)
                fid='component:'+key
                questions=[{'kind':'WHAT_EVENT','anchor_ref':p.token_id}]
                for role in gaps:
                    questions.append({'kind':'WHO' if role==cfg['subject_role'] else 'ARGUMENT_CONTENT',
                        'gap_id':'gap:'+digest([fid,role]),'role':role})
                questions.extend({'kind':'MISSING_REQUIRED_ROLE','role':r,
                    'gap_id':'gap:'+digest([fid,r]),'predicate_ref':p.token_id} for r in unresolved_roles)
                questions.extend({'kind':'UNRESOLVED_COMPONENT','token_ref':tid} for tid in uncovered)
                questions.extend(phrase_questions(groups,mapping,fid))
                semantic={'nominal_groups':nominal_groups,'proposed_roles':mapping,'morph_bindings':morph,'lexical_units':units,
                    'proposition_args':supplied,
                    'pending_proposition_roles':sorted(pending_required),
                    'allowed_proposition_roles':sorted(reserved) if val else None,
                    'agreement_source_ref':agreement_source.token_id if agreement_source else None,
                    'preposition_bindings':preps,'missing_required_roles':unresolved_roles,
                    'requires_attachment_probe':ambiguous or quality or nominal,
                    'quality_predication':quality, 'nominal_predication':nominal, 'copula_ref':copula,
                    'component_questions':questions,'uncovered_token_refs':uncovered,
                    'structural_unresolved':bool(uncovered or unresolved_roles),'component_region':region.region_id}
                if reduction is not None:
                    semantic['group_readings']=reduction['group_readings']
                    semantic['nominal_dependencies']=deps
                    semantic['attribute_constraints']=reduction['attributes']
                    semantic['pp_readings']=reduction['pp_readings']
                    semantic['component_questions'].extend(reduction['trace'])
                if controlled:
                    if cfg['subject_role'] in rs:continue
                    from .control_arguments import bind
                    bind(semantic,infinitive,cfg['subject_role'])
                    gaps.pop(cfg['subject_role'],None)
                if gaps:
                    semantic['implicit_arguments']={role:{**gap,'gap_id':'gap:'+digest([fid,role]),
                        'predicate_ref':p.token_id,'options':[]} for role,gap in gaps.items()}
                candidate=FrameCandidate(fid,'FLAT',p.span,
                    tuple([p.span,*[e.span for e,b in assignments]]),tuple(e.span for e,b in assignments),
                    construction='COMPONENTS_V1',predicate_token_ref=p.token_id,
                    argument_token_refs=tuple(e.token_id for e,b in assignments),source_range=tuple(region.source_range),
                    semantic=semantic,provenance=ResourceProvenance(('COMPONENTS_V1',),{'release':release.sha256}))
                if controlled:
                    from .control_arguments import expose_mentions
                    expose_mentions(candidate,infinitive,state.evidence)
                if projected:
                    from .participial_roles import add_host
                    add_host(candidate,projected)
                alternatives[key]=candidate
    return list(alternatives.values())
