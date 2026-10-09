"""Reference, lexical and bounded-selection stimuli over project APIs.

The input of this module is a stimulus payload, never an OracleCase or its
checks. Reference candidates are declared input records; bindings and outcomes
are read back from TD/T4 and, for the versioned trace, native C/T5/T6.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import json

from ah.formalizer.canonical_ledger import digest
from ah.formalizer.coreference import prepare_references, resolve_references, freeze_context
from ah.formalizer.pipeline import t0, t1, srl, t4, MorphProvider, OscillationDetector, bounded_search
from ah.formalizer.state import Decision, Ground, FrameCandidate, Budget, FormalizationState
from ah.formalizer.seal import structural_seal
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.store_interface import StoreOp, TerminalOutcome
from tools.formalizer_v7_test_support import test_release, role, sign_test_release, journal_plan

REFERENCE_ACTIONS = {
    'resolve_reference_window', 'resolve_reference', 'resolve_deictic_reference',
    'formalize_reference_with_context', 'declare_context_version',
    'lexical_candidates', 'context_candidate_reads', 'repeat_selector_cycle',
    'resolve_structure', 'solve_cluster', 'candidate_id_collision',
    'completed_t4_state',
}


class KeepAllSelector:
    """Deterministic fixture selector: exercises the actual closed-set validator."""
    def select(self, prompt):
        section = prompt.split('closed set):\n', 1)[1].split('\nTask:', 1)[0]
        ids = [line.split('. ', 1)[0] for line in section.splitlines() if '. ' in line]
        return json.dumps({'outcome': 'ONE_SELECTED' if len(ids) == 1 else
                          'MULTIPLE_ADMISSIBLE' if ids else 'NONE_FIT',
                          'selected': ids, 'note': 'fixture keeps every candidate'})


def _release(s, window=128):
    """One explicit language fixture for reference-only component operations."""
    if not hasattr(s, 'reference_release'):
        base = test_release(s.core, [('REFERENCE_FLY', 'взлететь', 'VERB',
                                     [role('SUBJECT')], 'EVENT')])
        m = deepcopy(base.manifest)
        m['entries'].append({'kind': 'CorefPolicy', 'version': 'test-v1',
                            'schema_version': 'v7', 'entries': [{
                                'window_size': window,
                                'hard_features': ['gender', 'number'],
                                'ranking_criteria': ['EXPLICIT_REF', 'SAME_SOURCE', 'RECENCY'],
                                'tie_policy': 'KEEP_ALL', 'event_anaphora_rules': []}],
                            'dependency_versions': {}})
        m['dependency_versions']['CorefPolicy'] = 'test-v1'
        content = {k: m[k] for k in ('kind', 'version', 'schema_version', 'entries', 'dependency_versions')}
        m['coverage_report']['resource_content_sha256'] = digest(content)
        m['coverage_report']['units_by_kind']['CorefPolicy'] = 1
        s.reference_release, _ = sign_test_release(m)
        s.release = s.reference_release
        s.templates[('REFERENCE_FLY', ('AGENT',))] = {
            'sense_id': 'REFERENCE_FLY', 'uid': 'fixture:T:REFERENCE_FLY',
            'roles': {'AGENT': 'SUBJECT'}}
        s.bootstrap = s.store._codec.export(s.core)
    return s.reference_release


def _state(s, text, *, candidates=(), context=None, window=128, source='reference:component', version=1):
    release = _release(s, window)
    state = t1(t0(text), MorphProvider())
    state.source_uid = source
    state.interpretation_version = version
    pronoun = next(e for e in state.evidence if any(v.pos == 'NPRO' for v in e.variants))
    predicate = next((e for e in state.evidence if any(v.pos == 'VERB' for v in e.variants)), state.evidence[-1])
    state.frames = [FrameCandidate('reference:F', 'FLAT', predicate.span,
        (pronoun.span, predicate.span), (pronoun.span,), predicate_token_ref=predicate.token_id,
        argument_token_refs=(pronoun.token_id,), source_range=(0, len(text)),
        semantic={'proposed_roles': {pronoun.token_id: 'SUBJECT'}})]
    state.observation = {'text': text, 'observation_id': source,
        'interpretation_version': version, 'request_kind': 'ASSERTION',
        'coreference_context': deepcopy(list(candidates)), 'context_snapshot': deepcopy(context or {})}
    return state, pronoun, release


def _candidate(s, alias, *, gender='masc', supports=(), source='declared:antecedent'):
    uid = 'fixture:reference:M:' + alias
    from ah.formalizer.graph_ops import ensure_entity
    if not s.store.has_uid(uid): ensure_entity(s.core, {'uid': uid, 'name': alias})
    s.entities[uid] = alias
    return {'entity_ref': uid, 'binding_ref': 'fixture:reference:binding:' + alias,
            'source_tag': [source, 1], 'premise_support_refs': list(supports),
            'features': [{'gender': gender, 'number': 'sing', 'person': '3rd'}], 'label': alias}


def _resolve(s, state, pronoun, release):
    slots = prepare_references(state, release)
    resolve_references(state, slots, KeepAllSelector(), release)
    t4(state, None)
    s.api.update({'coreference.prepare_references', 'coreference.resolve_references',
                  'selection_protocol.validate_selection_response', 'pipeline.t4'})
    d = state.decisions[pronoun.token_id + '|reference']
    rejected = [r['entity_ref'] for row in state.syntax_trace
                for r in row.get('rejected_reference_candidates', ())]
    return d, {
        'decision': {'outcome': d.outcome},
        'binding': {'target': s.entities.get(state.observation.get('entity_bindings', {}).get(pronoun.token_id)),
                    'created': pronoun.token_id in state.observation.get('entity_bindings', {})},
        'alternatives': {'entities': [s.entities.get(uid, uid) for uid in d.candidates]},
        'rejections': {'entities': [s.entities.get(uid, uid) for uid in rejected]},
        'diagnostics': {'codes': [x.code for x in state.diagnostics]},
        'runtime': {'reference_decision': asdict(d), 'reference_candidates': [asdict(x) for x in state.reference_candidates]},
    }


def _version_commit(s, state, pronoun, release):
    """Finish a prepared TD state through the real native planner and T6."""
    f = state.frames[0]
    spec = {'candidate_id': 'REFERENCE_FLY', 'sense_id': 'REFERENCE_FLY',
            'sense_kind': 'KNOWN', 'label': 'взлететь', 'roles': {pronoun.token_id: 'SUBJECT'},
            'state_class': 'EVENT'}
    f.semantic.update(candidate_specs={'REFERENCE_FLY': spec}, proposition_args={},
                      structural_unresolved=False)
    state.decisions[f.frame_id + '|predicate_value'] = Decision(
        'predicate_value', f.frame_id, ('REFERENCE_FLY',), selected=('REFERENCE_FLY',),
        lifecycle='PROVISIONAL', outcome='RESOLVED', grounds=[Ground('R', 'fixture reviewed sense', 'REFERENCE_FLY')])
    state.resource_snapshot = {'snapshot_id': release.sha256, 'release_version': release.manifest['version']}
    structural_seal(state)
    from ah.formalizer.v7_pipeline import run_from_state
    report = run_from_state(state, s.store, InterpretationRunBinding(s.store._journal),
        release=release, run_id='reference:run:' + str(state.interpretation_version),
        version=state.interpretation_version, observation_id=state.source_uid)
    s.api.update({'native_plan.build_plan', 'v7_pipeline.run_from_state', 'commit_stage.commit'})
    s.reference_state = state
    s.reference_nodes = tuple(report.node_refs)
    s.reference_source = state.source_uid
    s.sources['O_cur'] = [state.source_uid, state.interpretation_version]
    s.reference_report = asdict(report)
    return report


def reference_snapshot(s):
    """Read current binding visibility after a separate retraction action."""
    if not hasattr(s, 'reference_source'): return {}
    L = s.store.ledger
    rows = [b for b in L.data['bindings'].values() if b.get('source_tag', [None])[0] == s.reference_source]
    current = [b for b in rows if b.get('source_tag', [None, None])[1] == s.reference_state.interpretation_version]
    chosen = next((b for b in current if b.get('mention_ref') in s.reference_state.observation.get('unresolved_references', [])), None)
    if chosen is None: chosen = current[-1] if current else None
    observations = [r for r in L.data['observations'].values() if r['source_tag'][0] == s.reference_source]
    return {'binding': {'target': s.entities.get(chosen['target_ref']) if chosen else None,
                        'status': chosen.get('status') if chosen else None},
            'facts': {'current_visible': any(n in L.f_visible() for n in s.reference_nodes)},
            'observations': {'O_cur': {'retracted': any(r['status'] == 'RETRACTED' for r in observations)}},
            'identity': {'interpretation_version': s.reference_state.interpretation_version}}


def reference_action(s, a, p):
    if a == 'lexical_candidates':
        state = t0(p['text']); srl(state)
        if p.get('nearest_dictionary_form'):
            from ah.formalizer.state import TokenHypothesis, ResourceProvenance
            state.token_hypotheses.append(TokenHypothesis('fixture:distance-prior', p['surface'],
                ('keep_as_is', p['nearest_dictionary_form']),
                ResourceProvenance(('DECLARED_DISTANCE_PRIOR',), {'fixture': 'test-v1'})))
        t1(state, MorphProvider())
        retained = [e.span for e in state.evidence]
        chosen = {d.frame_id: d.selected for d in state.decisions.values() if d.slot_id == 'lex'}
        replacements = [span for span, ids in chosen.items() if ids and ids != ('keep_as_is',)]
        s.api.update({'pipeline.t0', 'pipeline.srl', 'pipeline.t1 / OOV_KEEP_AS_IS'})
        return {**s.snapshot(), 'lexical': {'retained_surfaces': retained, 'auto_replacements': replacements},
                'runtime': {'token_hypotheses': [asdict(h) for h in state.token_hypotheses]},
                'diagnostics': {'codes': [d.code for d in state.diagnostics]}}

    if a == 'resolve_reference':
        candidates = []
        for row in p['antecedents']:
            alias = row if isinstance(row, str) else row['entity']
            candidates.append(_candidate(s, alias, gender='masc' if isinstance(row, str) else row.get('gender'),
                                         supports=p.get('value_grounds', {}).get(alias, ())))
        state, pronoun, release = _state(s, p['text'], candidates=candidates)
        _, result = _resolve(s, state, pronoun, release)
        return {**s.snapshot(), **result}

    if a == 'resolve_reference_window':
        distance = p['distance_tokens']
        # Exactly distance evidence tokens separate the antecedent anchor from
        # the pronoun. Fillers are real raw tokens, not an after-the-fact filter.
        text = 'Иван' + ' .' * (distance - 1) + ' ' + p['text']
        state, pronoun, release = _state(s, text, window=p['max_window'])
        antecedent = state.evidence[0]
        state.frames.append(FrameCandidate('antecedent:F', 'FLAT', antecedent.span,
            (antecedent.span,), (antecedent.span,), predicate_token_ref=antecedent.token_id,
            argument_token_refs=(antecedent.token_id,), source_range=(0, antecedent.end),
            semantic={'proposed_roles': {antecedent.token_id: 'SUBJECT'}}))
        _, result = _resolve(s, state, pronoun, release)
        result['reference'] = {'candidate_in_window': bool(state.reference_candidates[0].candidates),
                               'distance_tokens': sum(antecedent.start <= e.start < pronoun.start for e in state.evidence)}
        return {**s.snapshot(), **result}

    if a == 'resolve_deictic_reference':
        context = {}
        if p['speaker_addressee_context_present']:
            row = _candidate(s, 'speaker' if p['pronoun'] == 'я' else 'addressee')
            context['user_ref' if p['pronoun'] == 'я' else 'self_ref'] = row['entity_ref']
        state, pronoun, release = _state(s, p['pronoun'] + ' пришёл.', context=context)
        d, result = _resolve(s, state, pronoun, release)
        result['reference'] = {'resolved': d.outcome == 'RESOLVED'}
        result['store'] = {'fictitious_entity_count': len(s.store.ledger.data['nodes'])}
        return {**s.snapshot(), **result}

    if a == 'context_candidate_reads':
        entity = next(iter(p['context_fact']['roles'].values()))['entity']
        row = _candidate(s, entity)
        state, pronoun, release = _state(s, 'Он пришёл.',
            candidates=[row] if p['context_kind'] == 'GenerationContext' else ())
        if p['context_kind'] == 'ResolutionContext': state.context_facts = (json.dumps(p['context_fact']),)
        prepare_references(state, release)
        s.api.add('coreference.prepare_references / declared generation context')
        return {**s.snapshot(), 'generation': {'new_antecedent_candidate_count':
                sum(len(c.candidates) for c in state.reference_candidates)},
                'store': {'context_fact_materialized': bool(s.store.ledger.f_visible())}}

    if a == 'resolve_structure':
        state = FormalizationState.new(p['text'])
        values = tuple(p['scope_alternatives'])
        d = Decision('reference', 'scope', values, selected=values, lifecycle='PROVISIONAL')
        if p['grounds_per_value']: d.grounds = [Ground('D', 'declared scope evidence', v) for v in values]
        state.decisions['scope'] = d; t4(state, None)
        s.api.add('pipeline.t4 / value-specific structural alternative validation')
        return {**s.snapshot(), 'decision': {'outcome': d.outcome},
                'alternatives': {'operators': list(d.candidates)},
                'diagnostics': {'codes': [d.code for d in state.diagnostics]}}

    if a == 'solve_cluster':
        ids = tuple(tuple(x) for x in p['compatible_tuples'])
        budget = Budget(search_step_limit=p['limit_branches'])
        found, complete, position = bounded_search({'cluster': ids}, [], budget)
        from ah.formalizer.selection_protocol import DecisionSchema, Relation
        state = FormalizationState.new('bounded cluster fixture')
        values = tuple('tuple:' + str(i) for i in range(len(ids)))
        d = Decision('predicate_value', 'cluster', values,
            selected=values[:len(found)], selector_outcome='ONE_SELECTED' if len(found) == 1 else None,
            lifecycle='PROVISIONAL', search_complete=complete)
        d.grounds = [Ground('D', 'declared compatible tuple', v) for v in values]
        state.decisions['cluster'] = d
        t4(state, DecisionSchema('fixture', {v: Relation(v, v, 2, ('SUBJECT', 'OBJECT'), v) for v in values}))
        s.api.update({'pipeline.bounded_search / resumable deterministic step budget', 'pipeline.t4 / search_complete'})
        return {**s.snapshot(), 'decision': {'outcome': d.outcome,
                'search_complete': complete, 'machine_state': d.machine_state},
                'runtime': {'compatible_tuples': found, 'position': position,
                            'search_steps': budget.search_steps, 'budget': budget.search_step_limit},
                'diagnostics': {'codes': [d.code for d in state.diagnostics]}}

    if a == 'repeat_selector_cycle':
        detector = OscillationDetector(); base = [Ground('R', 'fixed fixture declared ground')]
        events = [detector.record('slot', value, base) for value in p['choices']]
        new = [Ground(g.split(':', 1)[0], g) for g in p['new_grounds']]
        verdict = detector.record('slot', p['choices'][-1], base + new)
        binding = InterpretationRunBinding(s.store._journal)
        binding.acquire('selector:v1', 'selector:observation', 1, snapshot_hash=digest(base.__str__()))
        if verdict == 'rearmed':
            binding.acquire('selector:v2', 'selector:observation', 2, snapshot_hash=digest([asdict(g) for g in base + new]))
        s.api.update({'pipeline.OscillationDetector.record', 'InterpretationRunBinding.acquire'})
        return {**s.snapshot(), 'decision': {'machine_state': 'FROZEN' if 'slot' in detector.frozen else None,
                'rearmed': verdict == 'rearmed'}, 'identity': {'version_increment':
                max(binding.versions('selector:observation')) - 1}, 'runtime': {'cycle_verdicts': events, 'new_ground_verdict': verdict}}

    if a == 'candidate_id_collision':
        # Force two *different* structural records to the same local identifier
        # at the actual seal boundary. The current validator's response is the
        # observation; acceptance is a real integrity defect, not binder PASS.
        state = t0('а б'); state.frames = [FrameCandidate(p['forced_digest'], 'FLAT', row['surface'],
            (row['surface'],), (row['surface'],)) for row in p['payloads']]
        codes = []
        try: structural_seal(state)
        except Exception as exc: codes = ['INTEGRITY_ERROR' if state.has_diag('INTEGRITY_ERROR') else type(exc).__name__]
        s.api.add('seal.structural_seal / duplicate-ID collision stimulus')
        return {**s.snapshot(), 'diagnostics': {'codes': codes}, 'commit': {'materialized': False},
                'runtime': {'sealed': state.structural_closed, 'records': [asdict(f) for f in state.frames]}}

    if a == 'completed_t4_state':
        # Here payload.outcome is the recorded T4 outcome presented to the
        # state-machine boundary; it is not an expected answer. C then derives
        # the actual plan from that state, including the mixed-fragment case.
        release = _release(s)
        outcomes = p.get('outcomes', [p.get('outcome')])
        state = t1(t0(' '.join('Иван взлетел.' for _ in outcomes)), MorphProvider())
        state.source_uid = 'oracle:completed-t4'
        state.observation = {'observation_id': state.source_uid, 'interpretation_version': 1,
                             'text': state.text, 'request_kind': 'ASSERTION'}
        state.resource_snapshot = {'snapshot_id': release.sha256, 'release_version': release.manifest['version']}
        for i, outcome in enumerate(outcomes):
            argument, predicate = state.evidence[i * 3:i * 3 + 2]
            fid = 'completed:F' + str(i)
            spec = {'candidate_id': 'REFERENCE_FLY', 'sense_id': 'REFERENCE_FLY',
                'sense_kind': 'KNOWN', 'label': 'взлететь', 'roles': {argument.token_id: 'SUBJECT'},
                'state_class': 'EVENT'}
            state.frames.append(FrameCandidate(fid, 'FLAT', predicate.span,
                (argument.span, predicate.span), (argument.span,), predicate_token_ref=predicate.token_id,
                argument_token_refs=(argument.token_id,), source_range=(argument.start, predicate.end),
                semantic={'candidate_specs': {'REFERENCE_FLY': spec}, 'proposition_args': {},
                          'structural_unresolved': False}))
            values = ('A', 'B') if outcome == 'AMBIGUOUS' else ('A',) if outcome == 'RESOLVED' else ()
            if outcome == 'RESOLVED': values = ('REFERENCE_FLY',)
            d = Decision('predicate_value', fid, values, selected=values,
                         lifecycle='PROVISIONAL', outcome=outcome)
            state.decisions[fid + '|predicate_value'] = d
        structural_seal(state); state.complete_t4()
        from ah.formalizer.native_plan import build_plan
        ops, fragments, diagnostics, _ = build_plan(state, release, s.store)
        s.api.update({'seal.structural_seal', 'FormalizationState.complete_t4', 'native_plan.build_plan'})
        return {**s.snapshot(), 'version': {'state': state.machine_state},
                'decision': {'machine_state': next(iter(state.decisions.values())).machine_state},
                'decisions': {'machine_states': [d.machine_state for d in state.decisions.values()]},
                'plan': {'fragment_count': len(fragments), 'operation_count': len(ops)},
                'store': {'new_marker_count': len(s.store.ledger.data['markers'])},
                'diagnostics': {'codes': list(diagnostics)},
                'runtime': {'structural_closed': state.structural_closed, 'outcomes': [d.outcome for d in state.decisions.values()]}}

    if a == 'formalize_reference_with_context':
        raw = p['raw_input']; s.reference_text = raw['text']
        source = 'oracle:O_cur'
        state, pronoun, release = _state(s, raw['text'], source=source, version=p['context_version'])
        state.observation.update(deepcopy(raw), observation_id=source,
                                 interpretation_version=p['context_version'])
        d, result = _resolve(s, state, pronoun, release)
        _version_commit(s, state, pronoun, release)
        return {**s.snapshot(), **result, 'identity': {'interpretation_version': state.interpretation_version}}

    if a == 'declare_context_version':
        release = _release(s); source = getattr(s, 'reference_source', 'oracle:O_cur')
        if 'antecedent' in p:
            # Create the predecessor observation with actual mention bindings,
            # rather than passing fake SupportRecord IDs as P grounds.
            formula = {'predicate': 'LOCATIVE', 'roles': {'THEME': {'entity': p['antecedent']},
                       'LOCATION': {'entity': 'runway'}}}
            batch = p['antecedent_observation']; roots, supports, _ = s.prepare(batch, [formula])
            ops, decision, tag = s.batches[batch]; extra = []
            for alias, gender in p['morphology'].items():
                uid = 'fixture:M:' + digest(alias)
                extra.append(StoreOp('SET_IDENTITY_BINDING', {'binding_id': 'reference:antecedent:' + alias,
                    'mention_ref': alias, 'target_ref': uid, 'source_tag': tag,
                    'premise_support_refs': [], 'mention_features': [{'gender': gender, 'number': 'sing'}]}, decision.committed))
            binding_ids = [o.payload['binding_id'] for o in extra]
            ops = tuple(replace(o, payload={**o.payload, 'binding_refs': binding_ids}) if o.op_type == 'ADD_ROOT_SUPPORT' else o for o in ops) + tuple(extra)
            s.store.append_terminal('batch:' + batch, TerminalOutcome.STALE_SUPERSEDED, 'fixture adds explicit antecedent bindings')
            decision = journal_plan(s.store, ops, run_id=decision.run_id, observation_id=tag[0], version=tag[1], batch_hash=batch + ':bindings', fragments=decision.committed)
            s.batches[batch] = (ops, decision, tag); s.commit(batch); s.sources[batch] = tag
            s.reference_context = freeze_context(s.store, release, [tag])
        state, pronoun, release = _state(s, s.reference_text, candidates=s.reference_context,
                                         source=source, version=p['context_version'])
        state.observation['supersedes_version'] = s.reference_state.interpretation_version
        state.observation['trigger_ref'] = 'oracle:declared-context:' + str(p['context_version'])
        _, result = _resolve(s, state, pronoun, release)
        _version_commit(s, state, pronoun, release)
        result['execution'] = {'recomputed': True, 'structural_hash': state.structural_hash}
        result['supports'] = {'root_ground_types': sorted({r['ground_type'] for r in s.store.ledger.data['supports'].values() if r['kind'] == 'ROOT' and r['source_tag'][0] == source})}
        return {**s.snapshot(), **result, 'identity': {'interpretation_version': state.interpretation_version}}

    raise ValueError('UNBOUND_REFERENCE_ACTION:' + a)
