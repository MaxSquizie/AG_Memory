# Реестр v2: все найденные границы вызова

Это статические карточки. source — код сборки запроса, не окончательный текст конкретного исполнения.
Семантические выводы и непроверенные обязательства вынесены в FAMILY_REVIEW.md и CLOSURE.md.

## P001 — src/ah/formalizer/attitude_composition.py:88

Владелец: `ah.formalizer.attitude_composition.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:240 (ah.formalizer.component_refinement._compose_lexical_area).

```python
_probe(state,selector,release,key,'attitude_attachment',choices,
                    state.text[slice(*region.source_range)],region.source_range,
                    question='Which released parent/role owns this full proposition content? '
                    'Check its start AND end and the remaining parent. A conjunction reading must introduce a clause, '
                    'not a pronoun argument. Delimiters alone do not identify a speaker or assert the child event.')
```

## P002 — src/ah/formalizer/component_clause.py:64

Владелец: `ah.formalizer.component_clause.build_clause`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_predication.py:75 (ah.formalizer.component_predication.compose_alternatives).

```python
_probe(state,selector,release,region.region_id+'|composition','component_attachment',options,raw,region.source_range)
```

## P003 — src/ah/formalizer/component_dependency_reduction.py:86

Владелец: `ah.formalizer.component_dependency_reduction.reduce`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose_domain`.

Статические вызывающие: src/ah/formalizer/component_candidates.py:126 (ah.formalizer.component_candidates.enumerate_candidates); src/ah/formalizer/component_nominal_utterance.py:35 (ah.formalizer.component_nominal_utterance.candidates).

```python
choose_domain(state,release,selector,region,cfg,'nominal_dependency',options,question)
```

## P004 — src/ah/formalizer/component_infinitives.py:18

Владелец: `ah.formalizer.component_infinitives.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:292 (ah.formalizer.component_refinement._compose_lexical_area).

```python
choose(state,release,selector,region,cfg,'infinitive_head',choices,
        'Select the head of a dependent infinitive inside TARGET, or the whole-target description '
        'when that is permitted. This selects a proposed head, not its subject or factual occurrence.')
```

## P005 — src/ah/formalizer/component_infinitives.py:27

Владелец: `ah.formalizer.component_infinitives.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.source_set`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:292 (ah.formalizer.component_refinement._compose_lexical_area).

```python
source_set(state,release,selector,region,tokens,cfg,'infinitive_content',
        'Select the complete dependent infinitive content, including its complements. '
        'Exclude the parent predicate, its participants, and other clauses. '
        'The remaining parent must retain the predicate that takes this content. '
        'A boundary does not establish the controller or assert the action.',
        initial=selected,admissible=admissible)
```

## P006 — src/ah/formalizer/component_infinitives.py:63

Владелец: `ah.formalizer.component_infinitives.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:292 (ah.formalizer.component_refinement._compose_lexical_area).

```python
choose(state,release,selector,region,cfg,'infinitive_link',choices,
        'Select a source-supported infinitive relation AND subject control. '
        'Distinguish what the parent predicate is about (OBJECT) from why a separate parent action is performed (PURPOSE). '
        'UNKNOWN leaves the status unspecified; HYPOTHETICAL presents the child as intended or possible. '
        'A complement may have a different controller: answer 0 if no candidate represents the source, or ? if the evidence is insufficient. Do not assign identity from proximity.')
```

## P007 — src/ah/formalizer/component_nominal_groups.py:49

Владелец: `ah.formalizer.component_nominal_groups.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:315 (ah.formalizer.component_refinement._compose_lexical_area).

```python
_probe(state,selector,release,key,'nominal_coordination',[
        {'candidate_id':'NOMINAL','label':'Conjoined participants in ONE nominal slot: '+'; '.join(labels)},
        {'candidate_id':'OTHER','label':'The connector has another scope; these nominal groups are not established'}],
        state.text[slice(*region.source_range)],region.source_range,
        question='Which units does the written conjunction connect in this area? '
        'Do not infer that the members are one entity or that an event happened. Case and role are resolved later.')
```

## P008 — src/ah/formalizer/component_nominal_questions.py:10

Владелец: `ah.formalizer.component_nominal_questions.choose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_nominal_questions.py:27 (ah.formalizer.component_nominal_questions.select_units); src/ah/formalizer/component_nominal_questions.py:69 (ah.formalizer.component_nominal_questions.select_units); src/ah/formalizer/component_nominal_questions.py:114 (ah.formalizer.component_nominal_questions.select_hosts).

```python
_probe(state,selector,release,key,'nominal_attachment',options,
        state.text[slice(*region.source_range)],region.source_range,question=question)
```

## P009 — src/ah/formalizer/component_nominal_questions.py:27

Владелец: `ah.formalizer.component_nominal_questions.select_units`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_nominal_questions.choose`.

Статические вызывающие: src/ah/formalizer/component_nominal_tree.py:63 (ah.formalizer.component_nominal_tree.bundles).

```python
choose(state,release,selector,region,['segmentation',frame.frame_id],options,
            'Choose the phrase boundaries under the existing predicate and nominal slots. '
            'Preserve every source token; do not merge competing covers. If none of the proposed boundaries fits, answer 0; use ? only when evidence is insufficient.')
```

## P010 — src/ah/formalizer/component_nominal_questions.py:69

Владелец: `ah.formalizer.component_nominal_questions.select_units`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_nominal_questions.choose`.

Статические вызывающие: src/ah/formalizer/component_nominal_tree.py:63 (ah.formalizer.component_nominal_tree.bundles).

```python
choose(state,release,selector,region,local_key,options,
            'Which complete morphological reading fits this phrase in the source? '
            'Do not resolve identities or replace the source words.')
```

## P011 — src/ah/formalizer/component_nominal_questions.py:114

Владелец: `ah.formalizer.component_nominal_questions.select_hosts`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_nominal_questions.choose`.

Статические вызывающие: src/ah/formalizer/component_nominal_tree.py:67 (ah.formalizer.component_nominal_tree.bundles).

```python
choose(state,release,selector,region,key,options,
                question(state,frame,units,views,target,u))
```

## P012 — src/ah/formalizer/component_participants.py:110

Владелец: `ah.formalizer.component_participants.resolve_implicit`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
_probe(state,selector,release,gap['gap_id'],'implicit_argument',options,state.text[lo:hi],f.source_range,
                          equivalent_targets=targets,
                          question=('Resolve the omitted '+role+' of the TARGET clause below, not of another clause in the context.\n'
                            +'Target clause: '+state.text[slice(*f.source_range)]+'\n'
                            +'Target predicate: '+f.anchor_span+'; source range: '+str(f.source_range)+'\n'
                            +'Grammatical features of omitted participant: '+str(gap['features'])+'\n'
                            +'Choose the reference supported for THIS omission. Grammatical compatibility or proximity alone does not establish identity. '
                            +'A group member is not the whole group. Use the target speech perspective, not the uploader identity. '
                            +'The anonymous option preserves an unspecified referent; it does not assert a new, different person. '
                            +'Later clauses may supply evidence. If several candidates fit, preserve the alternatives.'))
```

## P013 — src/ah/formalizer/component_predication.py:187

Владелец: `ah.formalizer.component_predication.compose_alternatives`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:323 (ah.formalizer.component_refinement._compose_lexical_area).

```python
_probe(state, selector, release, region.region_id+'|composition',
                        'component_attachment', options, context, region.source_range,
                        question=target_question+(local['question'] if local else
                            'Which remaining interpretation fits the target? Previously selected roles, readings and attachments '
                            'are constraints, not questions to reopen. Retain alternatives when the text does not distinguish them.'))
```

## P014 — src/ah/formalizer/component_probe.py:68

Владелец: `ah.formalizer.component_probe._live_probe`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.selection_exchange.exchange`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
exchange(state,selector,d,prompt,schema,ids,maximum)
```

## P015 — src/ah/formalizer/component_probe.py:125

Владелец: `ah.formalizer.component_probe._probe.run`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.component_probe_replay.execute`.

Статические вызывающие: src/ah/formalizer/component_probe.py:138 (ah.formalizer.component_probe._probe).

```python
execute(_live_probe,state,selector,release,key,slot,options,context,source_range,
                      equivalent_targets=equivalent_targets,question=question,dependency_signature=dependency_signature,
                      offer_clarification=offer_clarification)
```

## P016 — src/ah/formalizer/component_refinement.py:193

Владелец: `ah.formalizer.component_refinement._compose_area`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:49 (ah.formalizer.component_refinement.compose_area.calculate).

```python
choose(state,release,selector,region,cfg,'structural_revision',[
                {'candidate_id':'REVISE','label':'The text supports a different relation or different boundaries; reconsider them'},
                {'candidate_id':'DEFER','label':'No different reading is supported; leave the parse unresolved'}],
                constraint_text+' Does the text support revising these choices?')
```

## P017 — src/ah/formalizer/component_refinement.py:278

Владелец: `ah.formalizer.component_refinement._compose_lexical_area`. Класс: REFINEMENT_WRAPPER. Разрешённое имя: `ah.formalizer.refinement_boundaries.select`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:113 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:209 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:225 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/relation_composition.py:255 (ah.formalizer.relation_composition.compose).

```python
select(state,release,selector,region,search_tokens,cfg)
```

## P018 — src/ah/formalizer/component_refinement.py:382

Владелец: `ah.formalizer.component_refinement._compose_lexical_area`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:113 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:209 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:225 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/relation_composition.py:255 (ah.formalizer.relation_composition.compose).

```python
_probe(state,selector,release,region.region_id+'|refinement-host','nominal_attachment',choices,
        state.text[slice(*region.source_range)],region.source_range,
        question='Which existing nominal does «'+state.text[body[0].start:body[-1].end]+
        '» describe? Choose its immediate host. Do not resolve pronoun identities or invent an entity.')
```

## P019 — src/ah/formalizer/component_refinement.py:420

Владелец: `ah.formalizer.component_refinement._compose_lexical_area`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:113 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:209 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:225 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/relation_composition.py:255 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'structural_marker_reading',
                [{'candidate_id':cid,'reading':_morph(v),'label':describe_reading(_morph(v))} for cid,v in unique.items()],
                'Choose the whole reading of the source connector under the selected host and child constraints.')
```

## P020 — src/ah/formalizer/component_refinement.py:446

Владелец: `ah.formalizer.component_refinement._compose_lexical_area`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:113 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:209 (ah.formalizer.component_refinement._compose_area); src/ah/formalizer/component_refinement.py:225 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/relation_composition.py:255 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'structural_description_role',[
                {'candidate_id':r['role_id'],'label':r['role_id']+': '+role_text(r['role_id'])} for r in release.entries('RoleRegistry')],
                'Which participant role does «'+host.span+'» fill inside «'+' '.join(t.span for t in body)+'»?')
```

## P021 — src/ah/formalizer/component_temporal_scope.py:20

Владелец: `ah.formalizer.component_temporal_scope.resolve`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
_probe(state,selector,release,key,'temporal_scope',[
            {'candidate_id':'SOURCE_ASSERTED','label':label+' is directly asserted by the source; other modifiers preserve this temporal relation'},
            {'candidate_id':'EMBEDDED','label':'The temporal relation is only embedded under modality, negation, report, or another unasserted scope'}],
            raw,region.source_range,question='Resolve the scope of the written temporal phrase. '
            'Do not infer occurrence, calendar dates or world truth. Select SOURCE_ASSERTED only if the wording itself asserts this ordering for the named event. '
            'Select EMBEDDED for an explicitly non-asserted scope; answer ? if the wording is insufficient.')
```

## P022 — src/ah/formalizer/composition_boundaries.py:52

Владелец: `ah.formalizer.composition_boundaries.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:245 (ah.formalizer.component_refinement._compose_lexical_area).

```python
_probe(state, selector, release, key, 'composition_boundary', options,
        state.text[lo:hi], region.source_range,
        question='Select the outer connection of this source area before parsing its children. '
        'Do not move an operator across the selected boundary. If one operator governs the whole '
        'coordination, select that outer operator; its content slot must remain the whole area. '
        'For a plain associative chain of actions choose the leftmost outer connector; '
        'this is structural bracketing, not temporal order. Grammar and context override this preference.')
```

## P023 — src/ah/formalizer/composition_children.py:40

Владелец: `ah.formalizer.composition_children.select_child`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/attitude_composition.py:97 (ah.formalizer.attitude_composition.compose); src/ah/formalizer/component_coordination.py:38 (ah.formalizer.component_coordination.coordinate); src/ah/formalizer/component_infinitives.py:46 (ah.formalizer.component_infinitives.compose); src/ah/formalizer/component_infinitives.py:78 (ah.formalizer.component_infinitives.compose); src/ah/formalizer/component_refinement.py:231 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:355 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:399 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:410 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:453 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/composition_source_union.py:63 (ah.formalizer.composition_source_union.merge); src/ah/formalizer/operator_composition.py:54 (ah.formalizer.operator_composition.compose); src/ah/formalizer/relation_composition.py:207 (ah.formalizer.relation_composition.child); src/ah/formalizer/relation_quantifiers.py:42 (ah.formalizer.relation_quantifiers.compose); src/ah/formalizer/relative_composition.py:51 (ah.formalizer.relative_composition.compose); src/ah/formalizer/relative_composition.py:53 (ah.formalizer.relative_composition.compose).

```python
choose(state,release,selector,region,cfg,'child_slot',options,question)
```

## P024 — src/ah/formalizer/composition_children.py:44

Владелец: `ah.formalizer.composition_children.select_child`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/attitude_composition.py:97 (ah.formalizer.attitude_composition.compose); src/ah/formalizer/component_coordination.py:38 (ah.formalizer.component_coordination.coordinate); src/ah/formalizer/component_infinitives.py:46 (ah.formalizer.component_infinitives.compose); src/ah/formalizer/component_infinitives.py:78 (ah.formalizer.component_infinitives.compose); src/ah/formalizer/component_refinement.py:231 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:355 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:399 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:410 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:453 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/composition_source_union.py:63 (ah.formalizer.composition_source_union.merge); src/ah/formalizer/operator_composition.py:54 (ah.formalizer.operator_composition.compose); src/ah/formalizer/relation_composition.py:207 (ah.formalizer.relation_composition.child); src/ah/formalizer/relation_quantifiers.py:42 (ah.formalizer.relation_quantifiers.compose); src/ah/formalizer/relative_composition.py:51 (ah.formalizer.relative_composition.compose); src/ah/formalizer/relative_composition.py:53 (ah.formalizer.relative_composition.compose).

```python
_probe(state,selector,release,key,'child_slot',options,
            state.text[slice(*region.source_range)],region.source_range,question=question)
```

## P025 — src/ah/formalizer/composition_morphology.py:63

Владелец: `ah.formalizer.composition_morphology.prepare.domain`. Класс: LOCAL_COMPUTE_WRAPPER. Разрешённое имя: `ah.formalizer.composition_morphology.prepare.select`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
select()
```

## P026 — src/ah/formalizer/content_reference_functions.py:18

Владелец: `ah.formalizer.content_reference_functions.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:178 (ah.formalizer.content_reference_functions.omitted_content); src/ah/formalizer/relation_composition.py:259 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'content_reference_presence',[
        {'candidate_id':'OMITTED','presence':'OMITTED','label':'The content is understood but no pointer wording is present in this target'},
        {'candidate_id':'EXPLICIT','presence':'EXPLICIT','label':'Some target words explicitly point to content expressed elsewhere'}],
        'The selected relation takes a proposition or action as content, not an entity participant. '
        'Is the content entirely omitted, or is there explicit pointer wording? Do not choose its source or role yet.')
```

## P027 — src/ah/formalizer/content_reference_functions.py:26

Владелец: `ah.formalizer.content_reference_functions.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.source_set`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:178 (ah.formalizer.content_reference_functions.omitted_content); src/ah/formalizer/relation_composition.py:259 (ah.formalizer.relation_composition.compose).

```python
source_set(state,release,selector,region,tokens,cfg,'content_pointer',
            'Select all wording that points to THIS content, including its grammatical introducer. '
            'Keep the owning predicate and its other participants outside this set.')
```

## P028 — src/ah/formalizer/content_reference_functions.py:38

Владелец: `ah.formalizer.content_reference_functions.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:178 (ah.formalizer.content_reference_functions.omitted_content); src/ah/formalizer/relation_composition.py:259 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'content_reference_source',[
        *[option for option,_ in sources],
        {'candidate_id':'OTHER_SOURCE','label':'The intended content is not among these established structures, or has not yet been interpreted'}],
        'Owner «'+owner.span+'». Pointer: '+('«'+' '.join(t.span for t in pointer)+'»' if pointer else 'omitted')+'. '
        'Which content fills the referred/omitted slot of THIS owner? Select that content itself, not an earlier statement ABOUT requesting, reporting or considering it. '
        'The source subject is shown to identify the source; the subject of its current use is determined separately. '
        'The inventory is limited to completed structures in this run. It does not prove absence elsewhere. '
        'Select the other-source option when a different source is required; use ? when the text does not identify the source.')
```

## P029 — src/ah/formalizer/content_reference_functions.py:75

Владелец: `ah.formalizer.content_reference_functions.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:178 (ah.formalizer.content_reference_functions.omitted_content); src/ah/formalizer/relation_composition.py:259 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'content_reference_kind',[
        {'candidate_id':'SAME_CONTENT','mode':'SAME_CONTENT','source_hash':option['source_hash'],
         'label':'The content keeps its established participants independently of the current owner; this use expresses no shared-subject constraint'},
        {'candidate_id':'CONTROLLED_ACTION','mode':'CONTROLLED_ACTION','source_hash':option['source_hash'],
         'label':'The current construction requires the action subject to be one of its own participants. Bind that participant to the action; preserve its other roles and scope, without equating events'}],
        'Source: '+option['label']+'. Current owner: «'+' '.join(t.span for t in parent)+'». '
        'Does the current construction CONTROL the subject of the referenced action, or merely refer to independent content? '
        'For other required substitutions answer 0; they must not be silently reduced to a subject change.')
```

## P030 — src/ah/formalizer/content_reference_functions.py:87

Владелец: `ah.formalizer.content_reference_functions.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:178 (ah.formalizer.content_reference_functions.omitted_content); src/ah/formalizer/relation_composition.py:259 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'content_reference_control',[
            {'candidate_id':'controller:'+digest(alias),'controller':alias,'source_hash':option['source_hash'],
             'label':'Subject of action «'+option['source_words']+'» = '+label+' of «'+owner.span+'»'} for alias,label in controllers(target)],
            'Referenced action: «'+option['source_words']+'». Current owner: «'+' '.join(t.span for t in parent)+'». '
            'Who is understood to carry out/be the subject of THAT ACTION in this use? '
            'Choose the action subject, not automatically the subject of the owning predicate. '
            'A request can ask its recipient to act; a report can describe another person acting. Resolve THIS construction from the context.')
```

## P031 — src/ah/formalizer/content_reference_functions.py:160

Владелец: `ah.formalizer.content_reference_functions.omitted_content`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:117 (ah.formalizer.component_refinement._compose_area).

```python
choose(state,release,selector,region,cfg,'omitted_content_presence',[
        {'candidate_id':'ABSENT','presence':'ABSENT',**parts,
         'label':'No propositional/action content is omitted in this use; the existing participants suffice'},
        {'candidate_id':'OMITTED','presence':'OMITTED',**parts,
         'label':'An understood proposition/action is omitted: preserve a content slot and resolve what fills it'}],
        'Target predicate «'+root.anchor_span+'» in «'+' '.join(t.span for t in tokens)+'». '
        'Does this use leave an understood ACTION/PROPOSITION unspoken? This is about what is said, intended, achieved or otherwise taken as content. '
        'An omitted person or thing is a different question. Do not invent an optional topic or purpose. '
        'Choose omitted content only when this use actually refers to it; use ? if undecidable.')
```

## P032 — src/ah/formalizer/contextual_agreement.py:54

Владелец: `ah.formalizer.contextual_agreement.resolve`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/composition_morphology.py:51 (ah.formalizer.composition_morphology.prepare.recover); src/ah/formalizer/native_frontend.py:695 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,key,'lexical_recovery',choices,context,region.source_range,
                question=target+'Is a grammatical inflection error supported by this context? The proposed head is «'+head.span+'». '
                'Edit distance merely proposes candidates, not proof. Keep the original if a legitimate uncorrected reading remains; answer ? if uncertain. Do not alter names or infer a new lexical meaning.')
```

## P033 — src/ah/formalizer/contextual_oov.py:63

Владелец: `ah.formalizer.contextual_oov.resolve`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose_domain`.

Статические вызывающие: src/ah/formalizer/composition_morphology.py:57 (ah.formalizer.composition_morphology.prepare.select); src/ah/formalizer/native_frontend.py:697 (ah.formalizer.native_frontend._interpret_state).

```python
choose_domain(state,release,selector,region,cfg,'structural_oov_function',
                    [{'candidate_id':pos,'label':pos_description(pos),'address':address} for pos in functions],
                    'Which part of speech does the ONE marked occurrence ⟦'+token.span+'⟧ have? '
                    'Addressed source: '+marked+'\nOther equally spelled words are not selected. '
                    'Choose its function in the sentence; no lemma, case or identity is established by this answer.')
```

## P034 — src/ah/formalizer/coreference.py:258

Владелец: `ah.formalizer.coreference.resolve_references`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:1038 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,tid+'|reference','reference',options,
                state.text[slice(*bounds)],bounds,
                question='What does «'+evidence[tid].span+'» @'+str(evidence[tid].start)+' refer to? '
                'A sole candidate in this bounded window is not proof. Choose a source-supported reference. List alternative referents when several fit; 0 means none fits, ? means evidence is insufficient.')
```

## P035 — src/ah/formalizer/directional_goal.py:36

Владелец: `ah.formalizer.directional_goal.constrain`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_nominal_tree.py:71 (ah.formalizer.component_nominal_tree.bundles).

```python
_probe(state,selector,release,key,'referent_constraint',choices,
            state.text[slice(*region.source_range)],region.source_range,
            question='Do these expressions constrain one destination of «'+frame.anchor_span+'»? '
            'This is a local slot constraint, not identification of a remembered place. '
            'Do not infer arrival, coordinates, distance or absolute height.')
```

## P036 — src/ah/formalizer/discourse_scopes.py:72

Владелец: `ah.formalizer.discourse_scopes.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:808 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,key,'speech_act',[
                {'candidate_id':'ASSERTION','label':'The speaker asserts the WHOLE statement, including a report that someone said/thought something; the reported content need not be true'},
                {'candidate_id':'QUERY','label':'The speaker asks for information or confirmation'},
                {'candidate_id':'COMMAND','label':'The speaker requests or directs an action'},
                {'candidate_id':'CONTENT','label':'The ENTIRE target is merely quoted/mentioned, with no assertion about it; not just a quote nested inside an asserted report'}],
                state.text[slice(*bounds)],bounds,
                question='What does the current speaker do with the WHOLE target? '
                'An assertion that someone said something is an assertion about that speech, not an assertion of its content. '
                'Likewise, asserting negation, possibility or a condition does not assert the inner event. '
                'Preserve the accepted internal structure; decide only the explicit act at its outermost level. '
                'Classify a question as QUERY even when it could indirectly suggest a request; do not infer an unstated command. '+
                ('Accepted syntax: '+'; '.join(content_links)+'. ' if content_links else ''))
```

## P037 — src/ah/formalizer/discourse_scopes.py:119

Владелец: `ah.formalizer.discourse_scopes.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:808 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,scope['scope_ref']+'|addressee','discourse_addressee',options,
                              state.text[slice(*parent.source_range)],parent.source_range,
                              question='Who is addressed by this quoted speech? A recipient role alone is not sufficient evidence.')
```

## P038 — src/ah/formalizer/document_scopes.py:44

Владелец: `ah.formalizer.document_scopes.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:691 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,row['decision_ref'],'document_scope',[
                {'candidate_id':'HEADER','label':'Calendar header dates the following entry, until the next peer calendar header or end of source. Nested temporal expressions retain their own scope.'},
                {'candidate_id':'INLINE','label':'Ordinary text; does not establish a temporal area over the following entry.'}],
                context,tuple(row['source_range']),question='Classify the source line «'+row['raw']+
                '». Layout alone is not evidence of date scope. Do not infer a year, timezone or clock boundaries. Proposed area: '+str(row['scope_range']))
```

## P039 — src/ah/formalizer/fake_selector.py:183

Владелец: `ah.formalizer.fake_selector`. Класс: EXAMPLE. Разрешённое имя: `sel.select`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
sel.select(prompt)
```

## P040 — src/ah/formalizer/kernel.py:54

Владелец: `ah.formalizer.kernel.BoundedExecutor.select`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.kernel.BoundedExecutor.executor.select`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
self.executor.select(prompt)
```

## P041 — src/ah/formalizer/kernel.py:58

Владелец: `ah.formalizer.kernel.BoundedExecutor.propose_local`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.kernel.BoundedExecutor.executor.propose_local`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
self.executor.propose_local(prompt)
```

## P042 — src/ah/formalizer/lexical_embedding.py:66

Владелец: `ah.formalizer.lexical_embedding.LexicalEmbeddingRanker.rank`. Класс: EMBEDDING_TRANSPORT. Разрешённое имя: `adapter.select`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
adapter.select(request,run_id,ordinal=1)
```

## P043 — src/ah/formalizer/naming_probe.py:83

Владелец: `ah.formalizer.naming_probe.naming_probe`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `selector.select`.

Статические вызывающие: src/ah/formalizer/naming_probe.py:88 (ah.formalizer.naming_probe.run_naming).

```python
selector.select(_naming_prompt(reading,context_facts))
```

## P044 — src/ah/formalizer/native_frontend.py:548

Владелец: `ah.formalizer.native_frontend._propose`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `selector.propose_local`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:773 (ah.formalizer.native_frontend._interpret_state).

```python
selector.propose_local(prompt)
```

## P045 — src/ah/formalizer/native_frontend.py:570

Владелец: `ah.formalizer.native_frontend._propose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:773 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,structure_key,'structure_attachment',options,state.text,(0,len(state.text)),
            question='Which proposed arrangement of the source occurrences fits the text? Compare the displayed links and readings; do not infer world truth.')
```

## P046 — src/ah/formalizer/native_frontend.py:1076

Владелец: `ah.formalizer.native_frontend._interpret_state`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:675 (ah.formalizer.native_frontend._run_native).

```python
_probe(state,selector,release,f.frame_id+'|predicate_value','predicate_value',options,
            context,f.source_range,
            question='Which lexical use applies to this occurrence in its selected structure? '+established+'Choose a catalog entry when its lexical meaning fits. Tense, date, negation and modality are handled by the structure, not new lexical senses. Choose an unlisted use only when no listed meaning fits; use ? when uncertain.')
```

## P047 — src/ah/formalizer/nominal_functions.py:34

Владелец: `ah.formalizer.nominal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_predication.py:42 (ah.formalizer.component_predication.compose_alternatives).

```python
choose(state,release,selector,region,cfg,'nominal_function',[
            {'candidate_id':'RELATION','label':'An adposition or multiword relational unit: words introducing a noun/pronoun and linking it to an action or another noun (place, destination, origin, instrument, possession or another relation)'},
            {'candidate_id':'REFERENCE','label':'An expression points to which person/thing is meant, using context or an earlier mention'},
            {'candidate_id':'QUANTITY','label':'An expression says how many or how much of a noun group; keep its wording'}],
            'Look for words in THIS target that introduce or specify a noun/pronoun. '
            'A preposition connecting a place to a verb counts as RELATION, even when the verb already has a place role. '
            'Choose the function of the FIRST remaining such expression, not all functions anywhere in the sentence. '
            'A name by itself or an ordinary descriptive adjective does not count. '
            'Already assigned functions (do not select the same function of the same occurrence again): '+
            '; '.join(k+': «'+' '.join(t.span for t in tokens if t.token_id in refs)+'»' for k,refs in used_by_kind.items())+'.',
            empty={'candidate_id':'DONE','label':'no further nominal relation, referential determiner or quantity expression'})
```

## P048 — src/ah/formalizer/nominal_functions.py:52

Владелец: `ah.formalizer.nominal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.source_set`.

Статические вызывающие: src/ah/formalizer/component_predication.py:42 (ah.formalizer.component_predication.compose_alternatives).

```python
source_set(state,release,selector,region,tokens,cfg,'nominal_function_source',
            kind+': select ONLY the connecting/determining/quantity expression. '
            'Exclude a separate nominal head and unrelated modifiers. Include a word that itself BOTH expresses this function and stands for its nominal bearer.',exclude=used_by_kind[kind])
```

## P049 — src/ah/formalizer/nominal_functions.py:58

Владелец: `ah.formalizer.nominal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_predication.py:42 (ah.formalizer.component_predication.compose_alternatives).

```python
choose(state,release,selector,region,cfg,'nominal_function_head',[
            {'candidate_id':t.token_id,'head_ref':t.token_id,'shared_function':t.token_id in refs,
             'label':'Nominal head «'+t.span+'» @'+str(t.start)+(' (this occurrence also carries the selected function)' if t.token_id in refs else '')}
            for t in tokens if (kind!='RELATION' or t.token_id not in refs) and any(c.isalnum() for c in t.span)],
            kind+': selected function expression is «'+expression+'». '
            +('Which noun/pronoun is its complement: the entity/place introduced BY this expression, not the outside predicate or participant it attaches to? '
              if kind=='RELATION' else 'Which noun/pronoun is determined or counted by this expression? ')+
            'Select the nominal bearer. A reference or quantity word may itself be that bearer; choose it only if the text supplies no separate head for this expression.')
```

## P050 — src/ah/formalizer/nominal_functions.py:79

Владелец: `ah.formalizer.nominal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_predication.py:42 (ah.formalizer.component_predication.compose_alternatives).

```python
choose(state,release,selector,region,cfg,'nominal_identity_function',[
                {'candidate_id':'CONTEXTUAL','label':'Identify the nominal from context; identity with a prior mention is not explicitly required'},
                {'candidate_id':'SAME','label':'The source explicitly requires the same referent as a prior mention'}],
                'Reference expression: «'+' '.join(t.span for t in owned)+'». What identity constraint is stated?')
```

## P051 — src/ah/formalizer/nominal_functions.py:86

Владелец: `ah.formalizer.nominal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_predication.py:42 (ah.formalizer.component_predication.compose_alternatives).

```python
choose(state,release,selector,region,cfg,'nominal_external_case',[
                {'candidate_id':c,'label':label} for c,label in [('nom','Nominative case'),('gen','Genitive case'),
                ('dat','Dative case'),('acc','Accusative case'),('abl','Instrumental case'),('loc','Prepositional/locative case'),('voc','Vocative case')]],
                'Which external grammatical case does this whole quantity group take here? Its inner noun can have a different case.')
```

## P052 — src/ah/formalizer/nominal_reference_groups.py:82

Владелец: `ah.formalizer.nominal_reference_groups.project`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_predication.py:69 (ah.formalizer.component_predication.compose_alternatives).

```python
_probe(state, selector, release, key, 'nominal_attachment', [
                {'candidate_id':'REFERENCE', 'label':raw+': determiner identifies an antecedent of the noun'+
                 ('; modifier requires the SAME antecedent' if identity else '')},
                {'candidate_id':'OTHER', 'label':'These words do not form this referential noun group; keep original analyses'}],
                state.text[slice(*region.source_range)], region.source_range,
                question='Choose the grammatical function of the whole noun group, not its antecedent. Do not infer identity from proximity.')
```

## P053 — src/ah/formalizer/nominal_reference_memory.py:68

Владелец: `ah.formalizer.nominal_reference_memory.resolve`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:1098 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,decision,'reference',options,context,(start,end),
                    equivalent_targets={o['candidate_id']:r['entity_ref'] for o,r in zip(options,rows)},
                    question='Resolve «'+constraint['raw']+'» as one noun group. Constraint='+
                    constraint['identity_constraint']+'. Select only a compatible antecedent supported by these source excerpts. '+
                    'Proximity and name spelling alone do not prove identity. An already introduced unnamed or relative place is a valid antecedent: unknown coordinates/name do not make its reference unresolved. '
                    'Choose the existing referent, not a new object. If several antecedents fit, list their numbers; use ? when evidence is insufficient to assess them.')
```

## P054 — src/ah/formalizer/open_set_probe.py:65

Владелец: `ah.formalizer.open_set_probe.propose_value`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `selector.select`.

Статические вызывающие: src/ah/formalizer/open_set_probe.py:105 (ah.formalizer.open_set_probe.maybe_extend).

```python
selector.select(build_probe_prompt(slot_id, miss_texts, existing_values, slot_definition=slot_definition, existing_definitions=existing_definitions))
```

## P055 — src/ah/formalizer/partition_domain.py:108

Владелец: `ah.formalizer.partition_domain.PartitionDomain.span`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.source_set`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
span(self.state,self.release,self.selector,self.region,tokens,self.cfg,slot,question,
                    admissible=complete,partial_admissible=partial,**kwargs)
```

## P056 — src/ah/formalizer/partition_role_revision.py:58

Владелец: `ah.formalizer.partition_role_revision.revise`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/partition_domain.py:170 (ah.formalizer.partition_domain.PartitionDomain.resolve).

```python
choose(state,domain.release,domain.selector,domain.region,domain.cfg,'structural_marker_revision',alternatives,
        'Current outer relation: '+RELATIONS[domain.kind]+'. '
        'No first piece was accepted from the still available occurrences: '+remaining+'. '
        'The earlier function assignments below excluded their occurrences from that search. '
        'Does the ORIGINAL SOURCE support changing one of those assignments as shown? '
        'A failed search does not prove any assignment wrong or exhaust every possible parse. '
        'Select only a source-supported correction, not the correction that would merely let execution continue. '
        'Other established functions and the outer relation remain fixed. '
        '0 means no listed correction is supported; ? means insufficient evidence.')
```

## P057 — src/ah/formalizer/partition_sequences.py:24

Владелец: `ah.formalizer.partition_sequences.select_parts`. Класс: PARTITION_BUILDER_CALLBACK. Разрешённое имя: `select`.

Статические вызывающие: src/ah/formalizer/relation_partitions.py:52 (ah.formalizer.relation_partitions.binary); src/ah/formalizer/relation_partitions.py:88 (ah.formalizer.relation_partitions.content).

```python
select(index,groups)
```

## P058 — src/ah/formalizer/partition_sequences.py:55

Владелец: `ah.formalizer.partition_sequences.select_parts`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_partitions.py:52 (ah.formalizer.relation_partitions.binary); src/ah/formalizer/relation_partitions.py:88 (ah.formalizer.relation_partitions.content).

```python
choose(state,domain.release,domain.selector,domain.region,local_cfg,
                'structural_ownership_revision',options,
                'Current outer relation: '+RELATIONS[domain.kind]+'. No accepted '+roles[index]+
                ' could be built from the still available words «'+remaining+'». '
                'Earlier assignments exclude their words from this part. Which assignment below contains '
                'words that the SOURCE places in the missing part and therefore needs reconsideration? '
                'Select the assignment to reconsider NEXT; multiple numbers are alternative next repairs, not a joint change. '
                'Failure alone is not evidence that an assignment is wrong. '
                '0: no listed assignment is shown wrong by the source; ?: insufficient evidence.')
```

## P059 — src/ah/formalizer/pipeline.py:626

Владелец: `ah.formalizer.pipeline.t3._attempt`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `selector.select`.

Статические вызывающие: src/ah/formalizer/pipeline.py:646 (ah.formalizer.pipeline.t3).

```python
selector.select(prompt)
```

## P060 — src/ah/formalizer/predicate_functions.py:21

Владелец: `ah.formalizer.predicate_functions.subject_presence`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_candidates.py:94 (ah.formalizer.component_candidates.enumerate_candidates).

```python
choose(state,release,selector,region,cfg,'predicate_subject_presence',[
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
```

## P061 — src/ah/formalizer/predicate_functions.py:76

Владелец: `ah.formalizer.predicate_functions.head`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_predication.py:50 (ah.formalizer.component_predication.compose_alternatives).

```python
choose(state,release,selector,region,cfg,'predicate_function',options,
        'Which source occurrence predicates something of participants in this target? Any grammatical form can have predicative use. '
        'Select a nominal description only if there is no separate predication.')
```

## P062 — src/ah/formalizer/predicate_functions.py:99

Владелец: `ah.formalizer.predicate_functions.binding`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_candidates.py:57 (ah.formalizer.component_candidates.enumerate_candidates).

```python
choose(state,release,selector,region,cfg,'predicate_argument_role',[
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
```

## P063 — src/ah/formalizer/predicate_functions.py:123

Владелец: `ah.formalizer.predicate_functions.binding`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose_domain`.

Статические вызывающие: src/ah/formalizer/component_candidates.py:57 (ah.formalizer.component_candidates.enumerate_candidates).

```python
choose_domain(state,release,selector,region,cfg,'predicate_argument_reading',[
                {'candidate_id':cid,'reading':clean(v),'token_ref':token.token_id,'predicate_ref':predicate.token_id,
                 'role':role,'label':reading_text(_morph(v))} for cid,v in unique.items()],
                'Predicate «'+predicate.span+'»: which whole reading of «'+token.span+'» fits its selected role '+role_text(role)+'? Preserve unknown features.')
```

## P064 — src/ah/formalizer/provider_adapter.py:163

Владелец: `ah.formalizer.provider_adapter.ProviderAdapter._exchange`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.provider_adapter.ProviderAdapter.transport`.

Статические вызывающие: src/ah/formalizer/provider_adapter.py:179 (ah.formalizer.provider_adapter.ProviderAdapter.select); src/ah/formalizer/provider_adapter.py:186 (ah.formalizer.provider_adapter.ProviderAdapter.propose_local); src/ah/formalizer/provider_adapter.py:199 (ah.formalizer.provider_adapter.ProviderAdapter.propose_lexical).

```python
self.transport(prompt)
```

## P065 — src/ah/formalizer/qualitative_quantity.py:52

Владелец: `ah.formalizer.qualitative_quantity.resolve`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_predication.py:66 (ah.formalizer.component_predication.compose_alternatives).

```python
_probe(state,selector,release,key,'nominal_attachment',choices,
                      state.text[slice(*region.source_range)],region.source_range,
                      question='Select the full quantity child of this nominal group, including a qualifier ONLY if it qualifies the quantity, not the event. '
                      'This is phrase attachment, not numerical calculation or identification of individual members.')
```

## P066 — src/ah/formalizer/quantifier_composition.py:117

Владелец: `ah.formalizer.quantifier_composition._bind`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/quantifier_composition.py:62 (ah.formalizer.quantifier_composition.bind).

```python
_probe(state,selector,release,key,'nominal_attachment',options,
                state.text[slice(*region.source_range)],region.source_range,
                question='The bound nominal is already selected when supplied. Select only its remaining compatible whole reading. '
                         'Do not introduce a named entity, an existential witness or an implicit lexical restriction.')
```

## P067 — src/ah/formalizer/real_backend.py:92

Владелец: `ah.formalizer.real_backend.RealBackendSelector._transport`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.real_backend.RealBackendSelector.backend.generate`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
self.backend.generate(prompt, system=system, role=self.role, override=settings)
```

## P068 — src/ah/formalizer/real_backend.py:115

Владелец: `ah.formalizer.real_backend.RealBackendSelector.propose_local`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.real_backend.RealBackendSelector._adapter.propose_local`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
self._adapter.propose_local(prompt,self.run_id)
```

## P069 — src/ah/formalizer/real_backend.py:118

Владелец: `ah.formalizer.real_backend.RealBackendSelector.select`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `ah.formalizer.real_backend.RealBackendSelector._adapter.select`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
self._adapter.select(prompt, self.run_id)
```

## P070 — src/ah/formalizer/refinement_boundaries.py:9

Владелец: `ah.formalizer.refinement_boundaries.general_boundary`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.source_set`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:251 (ah.formalizer.relation_composition.compose).

```python
source_set(state,release,selector,region,tokens,cfg,'structural_description',
        'Select the dependent description of a nominal. Keep the parent clause outside it.')
```

## P071 — src/ah/formalizer/refinement_boundaries.py:14

Владелец: `ah.formalizer.refinement_boundaries.general_boundary`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:251 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'structural_description_binding',[
        {'candidate_id':'RELATIVE_PRONOUN','label':'An explicit relative expression fills a participant role inside this description'},
        {'candidate_id':'RELATIVE','label':'An explicit connector relates this description to its nominal host'},
        {'candidate_id':'BOUND_DESCRIPTION','label':'The nominal host fills an unexpressed participant role in this description'}],
        'How does «'+' '.join(t.span for t in body)+'» refer to its host? Choose the grammatical relation, independent of wording or punctuation.')
```

## P072 — src/ah/formalizer/refinement_boundaries.py:23

Владелец: `ah.formalizer.refinement_boundaries.general_boundary`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:251 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'structural_description_marker',[
            {'candidate_id':t.token_id,'label':'«'+t.span+'» @'+str(t.start)} for t in body],
            'Which occurrence links the description to its host?')
```

## P073 — src/ah/formalizer/refinement_boundaries.py:30

Владелец: `ah.formalizer.refinement_boundaries.general_boundary`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.extend_source_set`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:251 (ah.formalizer.relation_composition.compose).

```python
extend_source_set(state,release,selector,region,body,cfg,'structural_description_link',
                'Select every piece of the linking expression; keep the described proposition outside it.',
                [next(t for t in body if t.token_id==marker)],[result[1]])
```

## P074 — src/ah/formalizer/refinement_boundaries.py:74

Владелец: `ah.formalizer.refinement_boundaries.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:278 (ah.formalizer.component_refinement._compose_lexical_area).

```python
choose(state,release,selector,region,cfg,'structural_refinement',candidates(),
            'Select the whole nominal description. Its host may precede OR follow it. '
            'All morphologically eligible starts and token ends remain available in later pages.')
```

## P075 — src/ah/formalizer/refinement_boundaries.py:105

Владелец: `ah.formalizer.refinement_boundaries.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:278 (ah.formalizer.component_refinement._compose_lexical_area).

```python
_probe(state, selector, release, key, 'component_attachment', choices, raw,
        region.source_range, question='Which span is a postnominal description attached to a noun in the remaining parent? '
        'The description may contain further descriptions. Do not use punctuation as proof; '
        'keep all complements belonging to this area. If none of these boundaries fits, answer 0; use ? when evidence is insufficient.')
```

## P076 — src/ah/formalizer/region_probes.py:45

Владелец: `ah.formalizer.region_probes.select_generated`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
_probe(state,selector,release,row['decision_ref'],'structural_attachment',choices,
            state.text[region.source_range[0]:region.source_range[1]],(start,end))
```

## P077 — src/ah/formalizer/relation_composition.py:119

Владелец: `ah.formalizer.relation_composition.confirm_partition`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/partition_domain.py:135 (ah.formalizer.partition_domain.PartitionDomain.resolve.compute).

```python
choose(state,release,selector,region,cfg,'structural_partition',[option],
        'Check ONE relation application: '+RELATIONS[kind]+'. '
        'Does the original source connect the quoted content parts by this relation, in the roles shown? '
        'The selected OUTER meaning applies to the parts; its own wording is outside them. '
        'Preserve their participants and any ADDITIONAL clauses, negation or modality nested inside a part. '
        'Do not require the selected outer operator to appear inside its own content as another operator. '
        'The parts are not independently asserted by this choice. '
        +('The parent has an intentionally open content slot filled by the other part; '
          'it need not be a standalone sentence and may contain other clauses. '
          'The established slot owner is «'+owner.span+'» @'+str(owner.start)+'. '
          'Check this content at that owner; other parent predicates keep their own clauses and scopes. ' if owner else '')+
        ('The marked quantifier occurrence also serves as the bound mention; preserve both functions. ' if shared_refs else '')+
        'Outer relation words may be separated in the source; they are not a new sentence. '
        'Choose the proposed application if it connects the right contents. '
        'Answer 0 if the relation or the assignment of its contents is wrong, or ? if the source does not decide. '
        'This choice does not resolve dictionary meanings or validate the internal parse of each part.')
```

## P078 — src/ah/formalizer/relation_composition.py:168

Владелец: `ah.formalizer.relation_composition.function_ownership`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_partitions.py:54 (ah.formalizer.relation_partitions.binary); src/ah/formalizer/relation_partitions.py:92 (ah.formalizer.relation_partitions.content).

```python
choose(state,release,selector,region,cfg,'structural_function_owner',options,
            kind+' ('+RELATIONS[kind]+'). Current parts: '+
            '; '.join(str(i+1)+': «'+' '.join(t.span for t in group)+'»' for i,group in enumerate(groups))+'. '+
            'Which is the FIRST remaining occurrence in source order expressing this OUTER relation? '
            'Select that occurrence to move it out of its part. '
            +('Words introducing the condition or consequence belong to this outer conditional relation. '
              if kind in {'IMPLIES','IF_ELSE','COUNTERFACTUAL'} else '')+
            ('Part 1 is the parent, part 2 is its selected content. Parent predicate «'+(owner.span if owner else '')+'» is content and must remain. Select only grammatical connective wording introducing «'+
             ' '.join(t.span for t in groups[1])+'». Move only an introducer of THIS content; '
             'a conjunction introducing a different clause still inside the parent must stay there. ' if kind=='CONTENT' else '')+
            'Predicates and participants remain content. Negation, modality and quantification of an inner proposition stay inside it.',
            empty={'candidate_id':'KEEP_ALL','label':'keep all listed words in their parts'})
```

## P079 — src/ah/formalizer/relation_composition.py:195

Владелец: `ah.formalizer.relation_composition.child`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:266 (ah.formalizer.relation_composition.compose); src/ah/formalizer/relation_composition.py:285 (ah.formalizer.relation_composition.compose); src/ah/formalizer/relation_composition.py:339 (ah.formalizer.relation_composition.compose); src/ah/formalizer/relation_composition.py:425 (ah.formalizer.relation_composition.content).

```python
choose(state,release,selector,region,cfg,'structural_event_head',opts,
                contract+'. Target words: «'+' '.join(t.span for t in tokens)+'». '
                'Is this a complete clause, or a noun phrase naming an event/state? '
                'For a complete clause choose the complete-clause option; its predicate will be selected next. '
                'For an event noun phrase choose its head. A person or object name alone is not an event. '
                'If none fits, answer 0.')
```

## P080 — src/ah/formalizer/relation_composition.py:235

Владелец: `ah.formalizer.relation_composition.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:104 (ah.formalizer.component_refinement._compose_area).

```python
choose(state,release,selector,region,cfg,'structural_relation',options,supplied+
        'Classify ONLY the target words. Context explains their meaning but is not part of this choice. '
        'Choose the outermost relation expressed inside the target; inner relations are handled later. '
        'Choose one lexical predication only when TARGET itself contains no further outer relation; '
        'an outer relation already supplied by CONTEXT must not be selected again. '
        'The full content option requires both the parent predicate and dependent content to be present in this text. '
        'A reference to content or an omitted but understood content uses the content-reference option; an omitted participant alone does not. '
        'Numeric quantification is deferred.')
```

## P081 — src/ah/formalizer/relation_composition.py:320

Владелец: `ah.formalizer.relation_composition.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:104 (ah.formalizer.component_refinement._compose_area).

```python
choose(state,release,selector,region,cfg,'structural_governor',
                [{'candidate_id':'INDEPENDENT','label':'No agreement governor: the child has independent predication'},
                 *governor_options],
                'Modal words: «'+' '.join(t.span for t in markers)+'». Content: «'+' '.join(t.span for t in owned)+'». '
                'Does a modal word supply person, number or gender agreement for a dependent infinitive? '
                'If the content already has its own conjugated predicate, choose no governor. '
                'Impersonal necessity or permission has no subject agreement: choose no governor. '
                'A passive predicate agrees with its patient, not its performer. '
                'A dictionary reading alone does not establish this connection.')
```

## P082 — src/ah/formalizer/relation_composition.py:357

Владелец: `ah.formalizer.relation_composition.content_owner`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:33 (ah.formalizer.content_reference_functions.compose); src/ah/formalizer/relation_partitions.py:63 (ah.formalizer.relation_partitions.content).

```python
choose(state,release,selector,region,cfg,'structural_owner',
            [{'candidate_id':t.token_id,'owner_ref':t.token_id,
              'label':'Content belongs to predicate «'+t.span+'» @'+str(t.start)}
             for t in parent if any(c.isalnum() for c in t.span)],
            'Choose the predicate INSIDE TARGET whose dependent proposition or action description is also INSIDE TARGET. '
            'This selects the owner before selecting its content boundaries. '
            'A predicate outside TARGET, including the ancestor whose slot this target fills, is not this owner. '
            'Content already supplied separately by the parent requirements does not count as content inside TARGET. '
            'If several predicates have their own dependent contents here, select the FIRST such predicate in source order; '
            'the other constructions remain for recursive analysis. This is traversal order, not a claim that they lack content. '
            'Several numbers mean alternative owners at this first position, not all content-taking predicates. '
            'Do not select a participant or infer an unknown word’s lexical meaning.')
```

## P083 — src/ah/formalizer/relation_composition.py:372

Владелец: `ah.formalizer.relation_composition.content_owner`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:33 (ah.formalizer.content_reference_functions.compose); src/ah/formalizer/relation_partitions.py:63 (ah.formalizer.relation_partitions.content).

```python
choose(state,release,selector,region,cfg,'structural_owner',
        [{'candidate_id':t.token_id,'owner_ref':t.token_id,**source_parts,
          'label':'Content belongs to predicate «'+t.span+'» @'+str(t.start)} for t in owners],
        'Selected dependent content: «'+body_text+'». Remaining parent: «'+' '.join(t.span for t in parent)+'». '
        'Which predicate takes THIS content as what is said, thought, intended or otherwise described? '
        'Other parent predicates may own a different clause. Position alone is not evidence.')
```

## P084 — src/ah/formalizer/relation_composition.py:411

Владелец: `ah.formalizer.relation_composition.content`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:260 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'structural_control',
            [{'candidate_id':'INDEPENDENT_CONTENT','independent_content':True,**source_parts,
              'label':'Independent content: no participant of «'+owner.span+'» is supplied as its infinitive subject'},
             *[{'candidate_id':'controller:'+digest(alias),'controller':alias,**source_parts,'label':'Same '+label+' of «'+owner.span+'»'}
               for alias,label in controllers(target)]],
            'Parent: «'+' '.join(t.span for t in parent)+'». Content: «'+body_text+'». '
            'Which participant, if any, is understood as the grammatical subject of THIS infinitive content? '
            'A passive subject receives the action; it need not perform it. '
            'A quoted or impersonal statement can have its own subject interpretation. '
            'Choose independent content if this connection is absent; the child will determine its own participants. '
            'Select a shared participant only when the source establishes that identity. Use ? if undecidable.')
```

## P085 — src/ah/formalizer/relation_composition.py:457

Владелец: `ah.formalizer.relation_composition.content_role`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/content_reference_functions.py:58 (ah.formalizer.content_reference_functions.compose); src/ah/formalizer/relation_composition.py:391 (ah.formalizer.relation_composition.content).

```python
choose(state,release,selector,region,cfg,'structural_content_role',choices,
        'Selected owner: «'+owner.span+'» @'+str(owner.start)+'. Selected dependent content: «'+body_text+'». '
        'Remaining parent: «'+' '.join(t.span for t in parent)+'». '
        +('Already assigned slots of THIS owner: '+', '.join(reserved)+'. Select a different slot; the assigned content is not being reconsidered. ' if reserved else '')+
        'Choose the role and status of THIS content for THIS predicate. '
        'QUOTED=reported; EMBEDDED=mental content; HYPOTHETICAL=intended/possible; UNKNOWN=unspecified. '
        'None asserts the child. No canonical lexical identity is inferred.')
```

## P086 — src/ah/formalizer/relation_markers.py:43

Владелец: `ah.formalizer.relation_markers.confirm`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:82 (ah.formalizer.relation_composition.confirm_partition).

```python
choose(state,release,selector,region,cfg,'relation_marker_role',options,
            'Outer relation: '+kind+' ('+RELATIONS[kind]+'). Words assigned to it: «'+
            ' '.join(t.span for t in links)+'». Content parts: '+('none retained' if empty else content)+'. '
            +('The selected content owner is «'+owner.span+'» @'+str(owner.start)+'. '
              'The first part is the PARENT, including its other clauses; the second is THIS owner\'s DEPENDENT CONTENT. '
              'A link between clauses of the parent is internal to the parent, not an introducer of this dependent content. ' if owner else '')+
            'Question about ONE source word: «'+token.span+'» @'+str(token.start)+'. '
            'Is it part of this outer wording, or does it belong to the content, including a nested negation, modality or quantifier? '
            'The current split removes this word from the content. Judge its meaning in the original source. '
            'An action remains content even when it is negated or has not happened. '
            'Choose only this occurrence\'s function. The other assigned words may still be misplaced; '
            'this choice does not approve the whole split or the completeness of the remaining content.')
```

## P087 — src/ah/formalizer/relation_partitions.py:14

Владелец: `ah.formalizer.relation_partitions.unary`. Класс: SEMANTIC_CALL. Разрешённое имя: `domain.span`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
domain.span(tokens,'structural_introducer',
        kind+' ('+RELATIONS[kind]+'): select only the complete words expressing this outer relation. '
        'Include the full linking expression and any conjunction introducing its content. '
        'Exclude words belonging to a different nested relation, even when adjacent to the outer marker. '
        'Exclude the content proposition, its subject and predicate. Separating commas may be included; '
        'do not end early just because the first word already signals the relation.',record_remainder=True,marker=True)
```

## P088 — src/ah/formalizer/relation_partitions.py:43

Владелец: `ah.formalizer.relation_partitions.binary.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `domain.span`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
domain.span(tokens,'structural_operand_'+str(i+1),
            kind+' ('+RELATIONS[kind]+'): select the complete '+contract+'. '+
            ('Include only what is being checked, not what happens as a result. ' if contract=='condition being checked' else
             'Include only this outcome, not the condition or the alternative outcome. ' if contract.startswith('outcome') else '')+
            'Exclude words linking the two outer parts. Keep any relations nested inside this part.'+
            (' Already selected: '+'; '.join(contracts[j]+': «'+' '.join(t.span for t in group)+'»' for j,group in enumerate(groups))+'.' if groups else ''),
            exclude=[t.token_id for g in groups for t in g],
            covered=[t.token_id for g in groups for t in g],remaining_parts=len(contracts)-i-1)
```

## P089 — src/ah/formalizer/relation_partitions.py:73

Владелец: `ah.formalizer.relation_partitions.content.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `domain.span`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
domain.span(tokens,'structural_content',
                'Select the complete dependent content: a proposition or an infinitive action description '
                'that is said, thought, requested, intended or otherwise taken as content. '
                'Exclude the parent predicate and its participants, the introducing conjunction, colon, and enclosing '
                'quotation marks. IF the content is quoted, start inside its quotes. '
                'Unquoted content needs no quotation marks. Retain any operators inside that content.'+owner_note,
                exclude=[owner_ref] if owner_ref else (),remaining_parts=1,remaining_contiguous=False)
```

## P090 — src/ah/formalizer/relation_partitions.py:82

Владелец: `ah.formalizer.relation_partitions.content.select`. Класс: SEMANTIC_CALL. Разрешённое имя: `domain.span`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
domain.span(rest,'structural_parent',
            'Selected dependent content: «'+' '.join(t.span for t in body)+'». It has been removed from the choices below. '
            'Select the remaining parent text: the predicate that takes this content, its participants and other attached clauses. '
            'Boundary punctuation may stay; punctuation and connecting words are checked separately.'+owner_note,
            covered=body_ids,must_include=[owner_ref] if owner_ref else ())
```

## P091 — src/ah/formalizer/relation_partitions.py:104

Владелец: `ah.formalizer.relation_partitions.group`. Класс: SEMANTIC_CALL. Разрешённое имя: `domain.span`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
domain.span(tokens,'structural_group',
        'Select the complete parenthesized proposition, excluding the outer delimiters.')
```

## P092 — src/ah/formalizer/relation_quantifiers.py:12

Владелец: `ah.formalizer.relation_quantifiers.compose.propose`. Класс: SEMANTIC_CALL. Разрешённое имя: `domain.span`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
domain.span(tokens,'structural_quantifier',
            operator+': select the nonnumeric quantifier expression only, excluding its nominal restriction.',marker=True)
```

## P093 — src/ah/formalizer/relation_quantifiers.py:19

Владелец: `ah.formalizer.relation_quantifiers.compose.propose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
choose(state,release,selector,region,cfg,'quantifier_source_functions',[
            {'candidate_id':'SEPARATE','shared':False,'label':'The quantified mention is separate from these quantifier words'},
            *[{'candidate_id':t.token_id,'head_ref':t.token_id,'shared':True,
               'label':'«'+t.span+'» simultaneously expresses quantification and the bound participant'} for t in anchors]],
            'Does this quantifier contain its own participant mention? The same occurrence can have both functions.')
```

## P094 — src/ah/formalizer/relation_quantifiers.py:35

Владелец: `ah.formalizer.relation_quantifiers.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/relation_composition.py:275 (ah.formalizer.relation_composition.compose).

```python
choose(state,release,selector,region,cfg,'structural_binder_head',
        [{'candidate_id':t.token_id,'head_ref':t.token_id,'label':'Bind the nominal «'+t.span+'» @'+str(t.start)} for t in heads],
        operator+': select the restricted variable mention. Its complete body remains indivisible; do not create a witness.')
```

## P095 — src/ah/formalizer/relative_composition.py:40

Владелец: `ah.formalizer.relative_composition.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: не найдены; это не доказательство недостижимости.

```python
_probe(state,selector,release,key,'temporal_boundary',choices,
                    state.text[slice(*region.source_range)],region.source_range,
                    question='Choose the complete nominal description governed by the temporal relation. '
                    'Include its adjectives and nominal dependents; do not absorb the subject of the following clause. '
                    'This chooses a child boundary, not an absolute date or the truth of the anchor event.')
```

## P096 — src/ah/formalizer/relative_pronoun.py:21

Владелец: `ah.formalizer.relative_pronoun.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:263 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:398 (ah.formalizer.component_refinement._compose_lexical_area).

```python
choose(state,release,selector,region,cfg,'relative_argument_role',[
            {'candidate_id':r['role_id'],'label':r['role_id']+': '+role_text(r['role_id'])} for r in release.entries('RoleRegistry')],
            'Which semantic role does «'+marker.span+'» fill inside the description? Its antecedent is «'+host.span+'». '
            'Account for passive voice; neither the antecedent case nor the pronoun case alone decides the role.')
```

## P097 — src/ah/formalizer/relative_pronoun.py:27

Владелец: `ah.formalizer.relative_pronoun.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:263 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:398 (ah.formalizer.component_refinement._compose_lexical_area).

```python
choose(state,release,selector,region,cfg,'relative_marker_reading',[
            {'candidate_id':cid,'label':describe(_morph(m))} for cid,m in variants.items()],
            'Which whole reading of «'+marker.span+'» fits this use? Do not copy the antecedent case.')
```

## P098 — src/ah/formalizer/relative_pronoun.py:42

Владелец: `ah.formalizer.relative_pronoun.compose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/component_refinement.py:263 (ah.formalizer.component_refinement._compose_lexical_area); src/ah/formalizer/component_refinement.py:398 (ah.formalizer.component_refinement._compose_lexical_area).

```python
_probe(state,selector,release,key,'relative_pronoun_role',choices,
        state.text[slice(*region.source_range)],region.source_range,
        question='Select the relative pronoun grammatical role inside the description. Its antecedent is already selected. '
        'The antecedent case in the parent does not determine its role here. Do not create another person or assert the description independently.')
```

## P099 — src/ah/formalizer/scope_assignment.py:190

Владелец: `ah.formalizer.scope_assignment._assign`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/scope_assignment.py:72 (ah.formalizer.scope_assignment.assign).

```python
_probe(state,selector,release,key,'modifier_scope',options,
                        state.text[slice(*region.source_range)],region.source_range,question=question)
```

## P100 — src/ah/formalizer/selection_exchange.py:16

Владелец: `ah.formalizer.selection_exchange.exchange`. Класс: TRANSPORT_OR_WRAPPER. Разрешённое имя: `selector.select`.

Статические вызывающие: src/ah/formalizer/component_probe.py:68 (ah.formalizer.component_probe._live_probe).

```python
selector.select(prompt)
```

## P101 — src/ah/formalizer/soft_clause_boundaries.py:34

Владелец: `ah.formalizer.soft_clause_boundaries.areas`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/components.py:64 (ah.formalizer.components._compose).

```python
_probe(state,selector,release,key,'clause_boundary',[
            {'candidate_id':'SPLIT','label':'Independent clauses at this boundary: LEFT «'+state.text[tokens[0].start:t.start]+'» / RIGHT «'+state.text[t.start:tokens[-1].end]+'»; the right clause is outside preceding descriptions'},
            {'candidate_id':'KEEP','label':'This predicate remains in the existing clause/scope; do not split here'}],
            state.text[slice(*region.source_range)],region.source_range,
            question='Check grammar and scope on BOTH sides. Separate finite verbs with a compatible subject, punctuation and capitalization are only weak clues. '
            'A name, heading, coordinated predicate or quoted content is not automatically a new clause. '
            'Select SPLIT only when the context supports an independent clause; otherwise KEEP or ?.')
```

## P102 — src/ah/formalizer/source_areas.py:41

Владелец: `ah.formalizer.source_areas.areas`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/components.py:50 (ah.formalizer.components._compose).

```python
choose(state,release,selector,combined,cfg,'structural_source_boundary',[
            {'candidate_id':'SEPARATE','label':'Independent composition areas; neither side supplies an unfinished construction or scope of the other'},
            {'candidate_id':'JOIN','label':'One composition area: a clause, quotation, operator or other construction spans this boundary'}],
            'Boundary at source offset '+str(current.source_range[1])+'. '
            'Does the next text complete a construction or scope begun here? Ordinary reference to an earlier entity alone does not require joining.')
```

## P103 — src/ah/formalizer/source_assertions.py:58

Владелец: `ah.formalizer.source_assertions.resolve.walk`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/source_assertions.py:34 (ah.formalizer.source_assertions.resolve.walk); src/ah/formalizer/source_assertions.py:67 (ah.formalizer.source_assertions.resolve.walk); src/ah/formalizer/source_assertions.py:72 (ah.formalizer.source_assertions.resolve); src/ah/formalizer/source_assertions.py:77 (ah.formalizer.source_assertions.resolve).

```python
_probe(state,selector,release,key,'source_assertion',[
                {'candidate_id':'SOURCE_ASSERTED','label':'The source itself asserts '+label(target)+' as occurring/holding, independently of the descriptive modifier.'},
                {'candidate_id':'EMBEDDED','label':'The content is only possible, intended, reported, questioned, denied or otherwise not asserted by the source.'}],
                context,(lo,hi),question='Determine assertion scope, not world truth or lexical identity. Parent modifier: '+label(tree)+'. Target content: '+label(target)+'. '
                'Read the whole supplied utterance. A descriptive companion/location/manner may preserve assertion; possibility, intention and quotation do not. '
                'Select SOURCE_ASSERTED only with positive wording evidence. Otherwise select EMBEDDED or ?; never infer occurrence merely from a typed argument.')
```

## P104 — src/ah/formalizer/spatial_references.py:27

Владелец: `ah.formalizer.spatial_references.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:778 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,key,'spatial_function',[
                {'candidate_id':'NONE','label':'No separate contextual place slot is expressed by this lexical occurrence'},
                {'candidate_id':'LOCATION','label':'An unspecified relative location is introduced'},
                {'candidate_id':'DESTINATION','label':'An unspecified relative destination is introduced'},
                {'candidate_id':'ORIGIN','label':'An unspecified relative origin is introduced'},
                {'candidate_id':'REFERENCE','label':'The occurrence refers to a place supplied by context'}],
                state.text[slice(*frame.source_range)],frame.source_range,
                question='What spatial function, if any, does «'+ev.span+'» have? Preserve its surrounding scope, including quotation. No coordinates can be inferred.')
```

## P105 — src/ah/formalizer/spatial_references.py:42

Владелец: `ah.formalizer.spatial_references.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:778 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,key+'|role','spatial_role',[
                    {'candidate_id':r['role_id'],'label':r['role_id']+': '+role_text(r['role_id'])} for r in release.entries('RoleRegistry')],
                    state.text[slice(*frame.source_range)],frame.source_range,
                    question='Which role does this '+choice+' place fill in «'+ev.span+'»?')
```

## P106 — src/ah/formalizer/spatial_references.py:126

Владелец: `ah.formalizer.spatial_references.resolve`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/native_frontend.py:1096 (ah.formalizer.native_frontend._interpret_state).

```python
_probe(state,selector,release,slot['decision_ref'],'spatial_reference',options,
                          state.text[lo:hi],slot['target_range'],
                          question='What place does «'+frame.anchor_span+'» refer to in the TARGET clause: '+
                          state.text[slice(*slot['target_range'])]+
                          '? Select only a source-supported antecedent. Direction and location are not synonyms; '
                          'a directed movement can introduce its relative destination. No coordinates are required. '
                          'If none of the supplied antecedents fits, answer 0; use ? when evidence is insufficient to assess them. This is a bounded context read, not a global search.')
```

## P107 — src/ah/formalizer/structural_tasks.py:103

Владелец: `ah.formalizer.structural_tasks._choose`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.component_probe._probe`.

Статические вызывающие: src/ah/formalizer/structural_tasks.py:18 (ah.formalizer.structural_tasks.choose); src/ah/formalizer/structural_tasks.py:24 (ah.formalizer.structural_tasks.choose_domain).

```python
_probe(state,selector,release,key,slot,choices,context,region.source_range,
            offer_clarification=False,
            question=question+' Evaluate the stated choice on this page. Multiple numbers mean alternative readings of that choice, not different tasks.' )
```

## P108 — src/ah/formalizer/structural_tasks.py:225

Владелец: `ah.formalizer.structural_tasks.span`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/structural_tasks.py:260 (ah.formalizer.structural_tasks.source_set).

```python
choose(state,release,selector,region,cfg,slot+'_start',starts,question+' Select the FIRST token.'+
            (' No offered endpoint was accepted for these earlier starts under the current restrictions: '+
             ', '.join('«'+tokens[i].span+'» @'+str(tokens[i].start) for i in sorted(rejected))+
             '. This does not reject the remaining starts.' if rejected else ''))
```

## P109 — src/ah/formalizer/structural_tasks.py:243

Владелец: `ah.formalizer.structural_tasks.span`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/structural_tasks.py:260 (ah.formalizer.structural_tasks.source_set).

```python
choose(state,release,selector,region,cfg,slot+'_end',ends(),
            question+' The start is «'+tokens[a].span+'» @'+str(tokens[a].start)+'. Select the LAST token.')
```

## P110 — src/ah/formalizer/structural_tasks.py:260

Владелец: `ah.formalizer.structural_tasks.source_set`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.span`.

Статические вызывающие: src/ah/formalizer/component_infinitives.py:27 (ah.formalizer.component_infinitives.compose); src/ah/formalizer/content_reference_functions.py:26 (ah.formalizer.content_reference_functions.compose); src/ah/formalizer/nominal_functions.py:52 (ah.formalizer.nominal_functions.prepare); src/ah/formalizer/partition_domain.py:108 (ah.formalizer.partition_domain.PartitionDomain.span); src/ah/formalizer/refinement_boundaries.py:9 (ah.formalizer.refinement_boundaries.general_boundary); src/ah/formalizer/temporal_functions.py:35 (ah.formalizer.temporal_functions.prepare).

```python
span(state,release,selector,region,tokens,cfg,slot,
        question+' Select the first continuous piece; other pieces can be added next.',exclude=exclude,
        record_remainder=record_remainder,initial=initial,admissible=partial_admissible)
```

## P111 — src/ah/formalizer/structural_tasks.py:264

Владелец: `ah.formalizer.structural_tasks.source_set`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.extend_source_set`.

Статические вызывающие: src/ah/formalizer/component_infinitives.py:27 (ah.formalizer.component_infinitives.compose); src/ah/formalizer/content_reference_functions.py:26 (ah.formalizer.content_reference_functions.compose); src/ah/formalizer/nominal_functions.py:52 (ah.formalizer.nominal_functions.prepare); src/ah/formalizer/partition_domain.py:108 (ah.formalizer.partition_domain.PartitionDomain.span); src/ah/formalizer/refinement_boundaries.py:9 (ah.formalizer.refinement_boundaries.general_boundary); src/ah/formalizer/temporal_functions.py:35 (ah.formalizer.temporal_functions.prepare).

```python
extend_source_set(state,release,selector,region,tokens,cfg,slot,question,
                             chosen[0],chosen[1],exclude=exclude,admissible=admissible,partial_admissible=partial_admissible)
```

## P112 — src/ah/formalizer/structural_tasks.py:283

Владелец: `ah.formalizer.structural_tasks.extend_source_set`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/refinement_boundaries.py:30 (ah.formalizer.refinement_boundaries.general_boundary); src/ah/formalizer/structural_tasks.py:264 (ah.formalizer.structural_tasks.source_set).

```python
choose(state,release,selector,region,cfg,slot+'_continue',[
            *[{'candidate_id':t.token_id,'token_ref':t.token_id,
               'label':'Another piece starts at «'+t.span+'» @'+str(t.start)} for t in remaining if t.token_id in reachable]],
            question+' Already included: «'+' '.join(t.span for t in selected)+'». '
            'Are any words OF THIS SAME PART still missing? If the part is complete, answer 0. '
            'Otherwise select where its FIRST missing piece begins. Words of another part are not a continuation of this part. '
            'Do not select the next clause just because it comes next, or select already included words again.',
            empty={'candidate_id':'DONE','label':'no further source words belong to this part'} if can_finish else None)
```

## P113 — src/ah/formalizer/structural_tasks.py:299

Владелец: `ah.formalizer.structural_tasks.extend_source_set`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/refinement_boundaries.py:30 (ah.formalizer.refinement_boundaries.general_boundary); src/ah/formalizer/structural_tasks.py:264 (ah.formalizer.structural_tasks.source_set).

```python
choose(state,release,selector,region,cfg,slot+'_piece_end',choices,
            'Expression being collected: '+question+' Already included: «'+' '.join(t.span for t in selected)+'». Next piece starts at «'+tokens[a].span+'». Select ONLY its last word.')
```

## P114 — src/ah/formalizer/tag_source.py:91

Владелец: `ah.formalizer.tag_source.TagSource.label`. Класс: INJECTED_CALLBACK. Разрешённое имя: `ah.formalizer.tag_source.TagSource._probe`.

Статические вызывающие: src/ah/formalizer/tag_source.py:110 (ah.formalizer.tag_source.TagSource.tag).

```python
self._probe(word, context=context, occurrence=occurrence, resource_version=resource_version)
```

## P115 — src/ah/formalizer/temporal_functions.py:17

Владелец: `ah.formalizer.temporal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.choose`.

Статические вызывающие: src/ah/formalizer/component_predication.py:46 (ah.formalizer.component_predication.compose_alternatives).

```python
choose(state, release, selector, region, cfg, 'temporal_function', [
            *[{'candidate_id':'time:'+t.token_id,'index':i,'token_ref':t.token_id,
               'label':'A time expression starts at «'+t.span+'» @'+str(t.start)}
              for i,t in enumerate(remaining)]],
            'Find separate words that answer WHEN, FOR HOW LONG or HOW OFTEN the target event/state holds. '
            'Select the first word of the FIRST such expression. Verb tense alone is not a separate time expression. '
            'If the target only names participants and an action, with no time wording, answer 0. '
            'The actual date need not be known to recognize relative time wording. '
            'Use ? only if you cannot decide the function of words actually present; missing event date is not a reason for ?. '
            'A word mentioned as a name/title is not a time use. '
            'Target words: «' +
            ' '.join(t.span for t in remaining) + '».',
            empty={'candidate_id':'NONE','label':'no remaining time expression'})
```

## P116 — src/ah/formalizer/temporal_functions.py:35

Владелец: `ah.formalizer.temporal_functions.prepare`. Класс: SEMANTIC_CALL. Разрешённое имя: `ah.formalizer.structural_tasks.source_set`.

Статические вызывающие: src/ah/formalizer/component_predication.py:46 (ah.formalizer.component_predication.compose_alternatives).

```python
source_set(state, release, selector, region, remaining, cfg, 'temporal_source',
                              'Select one whole temporal expression, including its qualifiers.',initial=result)
```
