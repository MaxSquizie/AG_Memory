"""Grounded reference resolution over a declared, frozen observation window.

Names never create cross-observation identity. Morphology filters incompatible
antecedents; a selected reference carries concrete source support IDs, so a
later retraction invalidates its IdentityBinding through the ordinary cascade.
"""
from __future__ import annotations
from copy import deepcopy
import json
from .canonical_ledger import digest
from .state import ReferenceCandidate, Decision, Ground, ResourceProvenance
from .selection_protocol import Relation, DecisionSchema, build_selection_prompt, validate_selection_response


def freeze_context(store, release, source_tags):
    policy=release.resources.get('CorefPolicy',{}).get('entries',())
    if not source_tags: return []
    if len(policy)!=1: raise ValueError('RESOURCE_MISSING: CorefPolicy required for declared reference reads')
    if len(source_tags)>policy[0]['window_size']: raise ValueError('COREF_WINDOW_LIMIT')
    tags={tuple(t) for t in source_tags}
    with store._journal.atomic(), store._store._lock:
        store._refresh(); ledger=store.ledger; paths=ledger.paths(); rows=[]
        # Index candidates by the explicitly permitted sources, not name search.
        for bid,binding in sorted(ledger.data['bindings'].items()):
            if binding['status']!='LIVE' or tuple(binding.get('source_tag',())) not in tags: continue
            if any(s not in paths for s in binding.get('premise_support_refs',())): continue
            supports=sorted(sid for sid,s in ledger.data['supports'].items()
                            if sid in paths and bid in s.get('binding_refs',())
                            and s.get('source_tag')==binding.get('source_tag'))
            if not supports: continue
            uid=binding['target_ref']
            if not store._store.has_uid(uid) or store._store.kind_of(uid).value!='M': continue
            entity=store._store.get_element_any_domain(uid)
            name=entity.properties.get('name')
            rows.append({'entity_ref':uid,'binding_ref':bid,'source_tag':binding['source_tag'],
                         'premise_support_refs':supports,'features':deepcopy(binding.get('mention_features',[])),
                         'label':str(name.value) if name is not None else uid})
            if len(rows)>256: raise ValueError('COREF_CANDIDATE_LIMIT')
        return rows


def _compatible(variants, candidate_features, hard):
    if not variants or not candidate_features: return True
    return any(all(a.get(k) is None or b.get(k) is None or a[k]==b[k] for k in hard)
               for a in variants for b in candidate_features)


def mention_features(evidence):
    fields=('gender','number','person')
    out=[]
    for variant in evidence.variants:
        row={k:getattr(variant,k,None) for k in fields}
        animacy=set(variant.features)&{'anim','inan'}
        row['animacy']=next(iter(animacy)) if len(animacy)==1 else None
        out.append(row)
    return out


def prepare_references(state, release):
    policies=release.resources.get('CorefPolicy',{}).get('entries',())
    policy=policies[0] if len(policies)==1 else None
    context=state.observation.get('coreference_context',[])
    explicit=state.observation.get('entity_bindings',{})
    evidence={e.token_id:e for e in state.evidence}; slots={}; local_targets={}
    arguments={tid for f in state.frames for tid in f.argument_token_refs
               if tid not in f.semantic.get('bound_arguments',{})}
    provenance=ResourceProvenance(('COREF_DECLARED_WINDOW',),{'release':release.sha256})
    for tid in sorted(arguments):
        ev=evidence[tid]
        if tid in explicit or not any(v.pos=='NPRO' for v in ev.variants): continue
        candidates={}; rejected=[]
        persons={v.person for v in ev.variants if v.pos=='NPRO'}
        contextual='user_ref' if persons=={'1st'} else 'self_ref' if persons=={'2nd'} else None
        contextual_ref=state.observation.get('context_snapshot',{}).get(contextual) if contextual else None
        if contextual_ref:
            candidates[contextual_ref]=[{'entity_ref':contextual_ref,'binding_ref':'context:'+contextual,
                'source_kind':'CONTEXT','premise_support_refs':[],'features':mention_features(ev),'label':contextual_ref}]
        if policy and not contextual_ref:
            local=[]
            for antecedent in sorted(arguments,key=lambda t:evidence[t].start):
                a=evidence[antecedent]
                if a.start>=ev.start or not any(v.pos=='NOUN' for v in a.variants) or any(v.pos=='NPRO' for v in a.variants): continue
                if sum(1 for x in state.evidence if a.start<=x.start<ev.start)>policy['window_size']: continue
                units=[f.semantic.get('lexical_units',{}).get(antecedent,{}) for f in state.frames if antecedent in f.argument_token_refs]
                unit=units[0] if units else {}
                mention=unit.get('mention_ref',antecedent)
                uid=explicit.get(mention) or 'M:'+digest([state.source_uid,mention])
                local_targets.setdefault(uid,{'mention_ref':mention,'label':unit.get('surface',a.span)})
                local.append({'entity_ref':uid,'binding_ref':'local:'+mention,
                    'source_tag':[state.source_uid,state.interpretation_version],
                    'premise_support_refs':list(state.observation.get('entity_binding_grounds',{}).get(mention,[])),
                    'features':mention_features(a),'label':unit.get('surface',a.span),
                    'local_anchor_ref':antecedent})
            for candidate in [*context,*local]:
                uid=candidate['entity_ref']
                if not _compatible(mention_features(ev),candidate['features'],policy['hard_features']):
                    rejected.append({'entity_ref':uid,'reason':'HARD_FEATURE_CONFLICT'}); continue
                candidates.setdefault(uid,[]).append(candidate)
        elif not contextual_ref:
            state.diag('RESOURCE_MISSING','CorefPolicy: '+tid)
        def rank(uid):
            rows=candidates[uid]; criteria=[]
            for criterion in policy.get('ranking_criteria',()) if policy else ():
                if criterion=='EXPLICIT_REF': criteria.append(0 if any(r.get('source_kind')=='CONTEXT' for r in rows) else 1)
                elif criterion=='SAME_SOURCE': criteria.append(0 if any(r.get('source_tag',[None])[0]==state.source_uid for r in rows) else 1)
                elif criterion=='RECENCY':
                    order={tuple(tag):i for i,tag in enumerate(state.observation.get('coreference_sources',()))}
                    criteria.append(-max((order.get(tuple(r.get('source_tag',())),-1) for r in rows),default=-1))
            return (*criteria,uid)
        candidates={uid:candidates[uid] for uid in sorted(candidates,key=rank)}
        ids=tuple(candidates)
        state.memory_mentions=tuple(dict.fromkeys((*state.memory_mentions,*ids)))
        state.reference_candidates.append(ReferenceCandidate(ev.span,ids,evidence=[('D' if c.get('local_anchor_ref') or c.get('source_kind')=='CONTEXT' else 'P',json.dumps(c,ensure_ascii=False,sort_keys=True)) for cs in candidates.values() for c in cs],provenance=provenance))
        state.syntax_trace.append({'stage':'TD','mention_ref':tid,'rejected_reference_candidates':rejected,
                                   'coref_policy':release.version('CorefPolicy') if policy else None})
        slots[tid]=candidates
    state.observation['local_reference_targets']=local_targets
    return slots


def resolve_references(state, slots, selector, release):
    explicit=dict(state.observation.get('entity_bindings',{}))
    grounds=deepcopy(state.observation.get('entity_binding_grounds',{})); unresolved=[]
    evidence={e.token_id:e for e in state.evidence}
    for tid,candidates in slots.items():
        ids=tuple(candidates); d=Decision('reference',tid,ids)
        state.decisions[tid+'|reference']=d
        for uid,rows in candidates.items():
            if any(r.get('source_kind')=='CONTEXT' for r in rows):
                d.grounds.append(Ground('D','explicit interaction-context speaker/addressee Ref',uid))
            elif any(r.get('local_anchor_ref') for r in rows):
                d.grounds.append(Ground('D','same-observation antecedent anchors: '+json.dumps(sorted(r['local_anchor_ref'] for r in rows if r.get('local_anchor_ref'))),uid))
            else:
                d.grounds.append(Ground('P','declared antecedent support paths: '+json.dumps(sorted({s for r in rows for s in r['premise_support_refs']})),uid))
        if len(ids)==1:
            d.selected=ids; d.outcome='RESOLVED'; d.grounds.append(Ground('D','one compatible grounded antecedent',ids[0]))
        elif ids and not state.budget.llm_exhausted:
            relations={uid:Relation(uid,rows[0]['label'],1,('REFERENT',),json.dumps(rows,ensure_ascii=False,sort_keys=True)) for uid,rows in candidates.items()}
            schema=DecisionSchema(release.sha256,relations)
            prompt=build_selection_prompt(slot_id='reference',frame_id=tid,context_span=state.text,
                mentions={tid:evidence[tid].span},schema=schema,candidates=ids,contextual_statements=state.context_facts)
            try:
                state.budget.spend_llm(); raw=selector.select(prompt)
                reply=validate_selection_response(raw,schema,allowed=frozenset(ids))
                d.last_prompt=prompt; d.raw_response=raw; d.selector_outcome=reply.outcome; d.selected=reply.selected
                d.outcome='RESOLVED' if reply.outcome=='ONE_SELECTED' else 'AMBIGUOUS' if reply.outcome=='MULTIPLE_ADMISSIBLE' else 'INSUFFICIENT_CONTEXT' if reply.outcome=='INSUFFICIENT_CONTEXT' else 'UNRESOLVED'
                if d.outcome=='RESOLVED': d.grounds.append(Ground('M','bounded antecedent selection',d.selected[0]))
            except Exception as exc:
                d.outcome='UNRESOLVED'; state.diag('COREF_SELECTION_FAILED',type(exc).__name__)
        else:
            d.outcome='UNRESOLVED'
        if d.outcome=='RESOLVED':
            uid=d.selected[0]; explicit[tid]=uid
            # One concrete grounding path suffices; independent alternatives
            # remain separate candidate evidence, not an all-of dependency.
            row=min(candidates[uid],key=lambda r:(tuple(r['premise_support_refs']),r['binding_ref']))
            grounds[tid]=list(row['premise_support_refs']) if row.get('local_anchor_ref') else row['premise_support_refs'][:1]
        else:
            unresolved.append(tid); state.diag('REFERENCE_AMBIGUOUS' if ids else 'REFERENCE_UNKNOWN',tid)
    state.observation['entity_bindings']=explicit
    state.observation['entity_binding_grounds']=grounds
    state.observation['unresolved_references']=unresolved
