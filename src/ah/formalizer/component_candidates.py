"""Bounded whole-morphology/role joins for a single finite clause."""
from itertools import product
from .canonical_ledger import digest
from .state import FrameCandidate, ResourceProvenance
from .component_policy import _features, _morph
from .component_phrases import role_choices, nominal_units, phrase_questions


def enumerate_candidates(state, release, cfg, region, tokens, p, temporal, nominals, groups):
    alternatives = {}
    for pv in p.variants:
        quality = pv.pos in cfg.get('quality_predicate_pos', ())
        if not quality and (pv.pos != 'VERB' or pv.mood == 'imperative'): continue
        if quality and pv.pos == 'ADJF' and 'nom' not in pv.cases: continue
        senses = [s for s in release.entries('R-S') if s['lemma'] == pv.lemma and s['POS'] == pv.pos and not s.get('anchor_pattern')]
        vals = [v for v in release.entries('R-V') if v['sense_id'] in {s['sense_id'] for s in senses}]
        if senses and not vals:
            state.diag('VALENCY_UNKNOWN', p.token_id); continue
        if not senses and not release.entries('OpenTemplatePolicy')[0]['allow']: continue
        shapes = vals if senses else [None]
        for val in shapes:
            if val and any(set(r.get('argument_types',())) != {'ENTITY'}
                           or r.get('cardinality',{}).get('max') != 1 for r in val['roles']): continue
            case_roles = {c:r for c,r in cfg['open_case_roles'].items() if not quality or (c == 'nom' and r == cfg['subject_role'])}
            roles = val['roles'] if val else [
                {'role_id':r,'allowed_cases':[c for c,r2 in case_roles.items() if r2==r],
                 'cardinality':{'min':int(r==cfg['subject_role'])}}
                for r in sorted(set(case_roles.values()) | {cfg['subject_role']})]
            variants = [role_choices(e,roles,pv,cfg['subject_role'],groups.get(e.token_id)) for e in nominals]
            count = 1
            for choices in variants: count *= len(choices)
            if count > 256:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
                # Never retain a previous valency prefix as a complete search.
                return []
            for binding in product(*variants):
                assignments=[(e,b) for e,b in zip(nominals,binding) if b[0] is not None]
                rs=[b[0] for e,b in assignments]
                if len(set(rs))!=len(rs): continue
                missing={r['role_id'] for r in roles if r.get('cardinality',{}).get('min',0)>0}-set(rs)
                gap = not quality and cfg['subject_role'] in missing and pv.number in {'sing','plur'}
                unresolved_roles=sorted(missing-({cfg['subject_role']} if gap else set()))
                used={p.token_id,*temporal,*(e.token_id for e,b in assignments)}
                units=nominal_units(state,tokens,assignments,used)
                preps={}
                morph={p.token_id:_morph(pv)}
                for e,(_,mv,prep) in assignments:
                    morph[e.token_id]=_morph(mv)
                    if prep:
                        group=groups[e.token_id]; used.add(group['token_ref'])
                        preps[e.token_id]={'token_ref':group['token_ref'],'lemma':prep.lemma}
                        morph[group['token_ref']]=_morph(prep)
                from .component_predication import consume_copula
                copula = consume_copula(tokens, p, pv, cfg, used, morph) if quality else None
                uncovered=[e.token_id for e in tokens if e.token_id not in used and e.span not in {'.','!'}]
                ambiguous=any(g['ambiguous_pos'] for g in groups.values())
                mapping={e.token_id:r for e,(r,_,_) in assignments}
                canonical={t:{k:v for k,v in m.items() if k!='score'} for t,m in morph.items()}
                key=digest([region.region_id,mapping,canonical,gap,uncovered,unresolved_roles])
                fid='component:'+key
                questions=[{'kind':'WHAT_EVENT','anchor_ref':p.token_id}]
                if gap: questions.append({'kind':'WHO','gap_id':'gap:'+digest([fid,cfg['subject_role']]),'role':cfg['subject_role']})
                questions.extend({'kind':'MISSING_REQUIRED_ROLE','role':r,
                    'gap_id':'gap:'+digest([fid,r]),'predicate_ref':p.token_id} for r in unresolved_roles)
                questions.extend({'kind':'UNRESOLVED_COMPONENT','token_ref':tid} for tid in uncovered)
                questions.extend(phrase_questions(groups,mapping,fid))
                semantic={'proposed_roles':mapping,'morph_bindings':morph,'lexical_units':units,
                    'preposition_bindings':preps,'missing_required_roles':unresolved_roles,
                    'requires_attachment_probe':ambiguous or quality,
                    'quality_predication':quality, 'copula_ref':copula,
                    'component_questions':questions,'uncovered_token_refs':uncovered,
                    'structural_unresolved':bool(uncovered or unresolved_roles),'component_region':region.region_id}
                if gap:
                    semantic['implicit_arguments']={cfg['subject_role']:{'gap_id':questions[1]['gap_id'],
                        'features':_features(pv),'predicate_ref':p.token_id,'options':[]}}
                alternatives[key]=FrameCandidate(fid,'FLAT',p.span,
                    tuple([p.span,*[e.span for e,b in assignments]]),tuple(e.span for e,b in assignments),
                    construction='COMPONENTS_V1',predicate_token_ref=p.token_id,
                    argument_token_refs=tuple(e.token_id for e,b in assignments),source_range=tuple(region.source_range),
                    semantic=semantic,provenance=ResourceProvenance(('COMPONENTS_V1',),{'release':release.sha256}))
    return list(alternatives.values())
