"""Temporal, correlated-witness and path-retraction stimuli on the real store.

Input payloads specify fixtures and schedules only. All outputs are read from
canonical records, the immutable WAL, or actual rule validation; no gold checks
are received by this module.
"""
from copy import deepcopy
from dataclasses import replace
from tools import formalizer_v7_runtime_adapter as base
from tools.formalizer_v7_test_support import journal_plan, sign_test_release
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.store_interface import StoreOp
from ah.formalizer.goal_channel import execute, validate_goal
from ah.formalizer.goal_executor import GoalRequest

TEMPORAL_ACTIONS = {
    'retract_time_path', 'correlated_inference', 'change_conflict_evidence',
    'time_constraints', 'commit_dated_conjunction', 'replace_not_observation',
    'multi_premise_inference', 'derive_operator_conclusion', 'proof_independence',
    'open_or_cross_source', 'seed_without_incompatibility', 'seed_temporal_or',
}

ATOM = {'predicate': 'LOCATIVE', 'roles': {'THEME': {'entity': 'book'}, 'LOCATION': {'entity': 'table'}}}
OTHER = {'predicate': 'LOCATIVE', 'roles': {'THEME': {'entity': 'book'}, 'LOCATION': {'entity': 'shelf'}}}
ARRIVE = {'predicate': 'ARRIVE', 'roles': {'AGENT': {'entity': 'ivan'}}}
TEMPORAL_FIXTURES = [ATOM, OTHER, ARRIVE,
                     {'predicate': 'STUDENT', 'roles': {'AGENT': {'entity': 'ivan'}}}]


def _commit_ops(s, source, ops, fragments):
    tag = ['oracle:' + source, 1]
    ops = tuple(ops)
    decision = journal_plan(s.store, ops, run_id='run:' + source,
                            observation_id=tag[0], version=1,
                            batch_hash=source, fragments=fragments)
    s.batches[source] = (ops, decision, tag)
    s.commit(source)
    s.sources[source] = tag
    return tag


def observation(s, source, formula, window=None, *, and_elimination=False,
                witness_ref=None, binding_premise=None, support_metadata=None,
                only_conclusion=None):
    """One typed observation, including T6's commit-time AND paths if requested."""
    tag = ['oracle:' + source, 1]
    fragment = source + ':F'
    ops = []
    uid, key, prop, polarity = s.tree(formula, fragment, ops)
    binding_refs = []
    if binding_premise is not None:
        entity = next(op.payload['uid'] for op in ops if op.op_type == 'ENSURE_ENTITY')
        bid = 'fixture:binding:' + digest([source, entity, binding_premise])
        ops.append(StoreOp('SET_IDENTITY_BINDING', {
            'binding_id': bid, 'mention_ref': source + ':mention',
            'target_ref': entity, 'source_tag': tag,
            'premise_support_refs': [binding_premise],
        }, (fragment,)))
        binding_refs = [bid]
        s.aliases['B'] = bid
    sid = 'fixture:root:' + digest([source, uid])
    support = {'record_id': sid, 'conclusion_ref': uid, 'kind': 'ROOT',
               'ground_type': 'O', 'source_tag': tag, 'binding_refs': binding_refs,
               **(support_metadata or {})}
    ops.append(StoreOp('ADD_ROOT_SUPPORT', support, (fragment,)))
    reg = base.witness(window) if window else None
    assertions = []

    def assertion(target, path, kind):
        if reg is None:
            return None
        aid = 'fixture:time:' + digest([source, path, reg])
        prov_support = {'kind': kind}
        if kind == 'DERIVED':
            prov_support.update(rule_id='AND_ELIMINATION', premise_support_refs=[sid])
        ops.append(StoreOp('ADD_TIME_ASSERTION', {
            'assertion_id': aid, 'target_ref': target, 'support_record_id': path,
            'region': reg, 'anchor': None, 'witness_ref': witness_ref,
            'provenance': {'source': {'kind': 'OBSERVATION', 'source_tag': tag},
                           'support': prov_support},
        }, (fragment,)))
        assertions.append(aid)
        return aid

    aid = assertion(uid, sid, 'ROOT')
    paths = [sid]
    if and_elimination:
        if formula.get('operator') != 'AND':
            raise ValueError('AND_ROOT_REQUIRED')
        for child in formula['operands']:
            if only_conclusion is not None and child != only_conclusion:
                continue
            child_ref = s.formulas[digest(child)]
            dsid = 'fixture:and:' + digest([source, child_ref])
            ops.append(StoreOp('ADD_DERIVED_SUPPORT', {
                'record_id': dsid, 'conclusion_ref': child_ref, 'formula_ref': child_ref,
                'kind': 'DERIVED', 'rule_id': 'AND_ELIMINATION',
                'premise_support_refs': [sid], 'source_tag': tag,
            }, (fragment,)))
            assertion(child_ref, dsid, 'DERIVED')
            paths.append(dsid)
    ops.append(StoreOp('DECLARE_FRAGMENT', {
        'fragment_id': fragment, 'node_ref': uid, 'content_key': key,
        'proposition': prop, 'polarity': polarity, 'region': reg,
        'source_tag': tag,
    }, (fragment,)))
    _commit_ops(s, source, ops, [fragment])
    s.api.add('AHStoreAdapter.commit_transaction / typed ROOT and AND_ELIMINATION paths')
    return uid, paths, assertions, aid


def _new_conclusion(s, formula):
    existing = s.formulas.get(digest(formula))
    if existing in s.store.ledger.data['nodes']:
        return existing, ()
    ops = []
    target, *_ = s.tree(formula, 'goal-conclusion', ops)
    ledger = s.store.ledger
    retained = []
    for op in ops:
        if op.op_type == 'ENSURE_ENTITY':
            if not s.store.has_uid(op.payload['uid']):
                raise ValueError('GOAL_FIXTURE_ENTITY_NOT_MATERIALIZED')
            continue
        if op.op_type in {'ENSURE_NODE', 'ENSURE_FUNCTION'} and op.payload['uid'] in ledger.data['nodes']:
            continue
        if op.op_type == 'MATERIALIZE_USAGE_LINK' and op.payload['link_id'] in ledger.data['usage_links']:
            continue
        p = dict(op.payload)
        if op.op_type == 'ENSURE_NODE':
            origin = next((n['uid'] for n in ledger.data['nodes'].values()
                           if n.get('template_ref') == p['template_ref']), None)
            if origin:
                p['origin_ref'] = origin
        retained.append(replace(op, payload=p, fragment_refs=()))
    def rewrite(value):
        if isinstance(value, str): return '@conclusion' if value == target else value
        if isinstance(value, dict): return {k: rewrite(v) for k, v in value.items()}
        if isinstance(value, list): return [rewrite(v) for v in value]
        return value
    rewritten = []
    for op in retained:
        p = rewrite(op.payload)
        if op.op_type == 'MATERIALIZE_USAGE_LINK':
            p['link_id'] = 'usage:' + digest([p['node_ref'], p['parent_ref'], p['position'], 'OPERATOR'])
        rewritten.append(replace(op, payload=p))
    return '@conclusion', tuple(rewritten)


def request_from_records(s, rule, root_formula, other_formulas, supports, assertions,
                         conclusion, run_id='GR1'):
    target, ops = _new_conclusion(s, conclusion)
    specs = {**s.store.ledger.data['nodes'],
             **{op.payload['uid']: op.payload for op in ops if op.op_type in {'ENSURE_NODE', 'ENSURE_FUNCTION'}}}
    from ah.formalizer.goal_forms import formula, canonical
    signature = digest(canonical(formula(s.store.ledger, target, [8192], specs=specs)))
    return GoalRequest(run_id, rule, tuple(supports), signature,
                       temporal_premise_assertion_refs=tuple(assertions),
                       conclusion_ref=target if not ops else None,
                       conclusion_ops=ops), target


def _goal_view(s, req, target, decision):
    result = s.derived_snapshot(req, target, decision,
                                [decision['reason']] if decision.get('reason') else [])
    paths = [v for v in s.store.ledger.data['supports'].values() if v['kind'] == 'DERIVED'
             and v.get('rule_id') == req.rule_id]
    times = [a for a in s.store.ledger.data['assertions'].values()
             if a['support_record_id'] in {v['record_id'] for v in paths}]
    result['derived'].update(witness_ref=times[-1].get('witness_ref') if times else None,
                             is_continuous=bool(times and times[-1]['region']['kind'] == 'CONTINUOUS'))
    if decision.get('conclusion_ref'):
        actual_target = decision['conclusion_ref']
        source_formula = s.decode(actual_target)
        s.formulas[digest(source_formula)] = actual_target
        if times:
            s.aliases['A_derived'] = times[-1]['assertion_id']
    return result


def _preflight_view(s, req, target, reason):
    """Read-only licensing rejection; no invented durable goal decision."""
    L = s.store.ledger
    paths = [v for v in L.data['supports'].values() if v['kind'] == 'DERIVED'
             and v.get('rule_id') == req.rule_id]
    times = [a for a in L.data['assertions'].values()
             if a['support_record_id'] in {v['record_id'] for v in paths}]
    answer = L.query_proposition(target, **s.query_args(req.request_window))['answer'] if target in L.data['nodes'] else 'UNKNOWN'
    result = s.snapshot()
    result.update(
        license={'valid': False, 'stage': 'PREFLIGHT', 'reason': reason},
        goal={'started': False, 'goal_run_id': req.goal_run_id},
        derived={'support_count': len(paths),
                 'premise_count': len(paths[0]['premise_support_refs']) if paths else 0,
                 'time': base.symbolic_time(times[0]['region']) if times else None},
        answer={'status': answer}, diagnostics={'codes': [reason]},
        commit={'instances_before_goal': 0},
    )
    s.api.add('goal_channel.validate_goal read-only preflight; no GOAL_PENDING/GOAL_DECISION')
    return result


def temporal_action(s, action, p):
    if action == 'time_constraints':
        from ah.formalizer.temporal_constraints import validate_order_constraints
        code = None
        try:
            order = validate_order_constraints(p['edges'])
        except ValueError as exc:
            code = str(exc); order = ()
        s.api.add('temporal_constraints.validate_order_constraints')
        return {**s.snapshot(), 'decision': {'outcome': 'UNRESOLVED' if code else 'RESOLVED'},
                'time': {'invented_dates': [], 'symbolic_order': list(order)},
                'diagnostics': {'codes': [code] if code else []}}
    if action == 'commit_dated_conjunction':
        observation(s, p['source'], p['root'], p.get('window'),
                    and_elimination=True, witness_ref=p.get('witness_ref'))
        return s.snapshot()
    if action == 'correlated_inference':
        from tools.formalizer_v7_extended_binding import OR, NOT
        rule = p['rule']
        if rule == 'OR_ELIMINATION':
            root, other, conclusion = OR, NOT, OR['operands'][0]
        else:
            rx = {'predicate': 'STUDENT', 'roles': {'AGENT': {'bound_var': 'x'}}}
            bx = {'predicate': 'ARRIVE', 'roles': {'AGENT': {'bound_var': 'x'}}}
            root = {'operator': 'FORALL', 'operands': [{'bound_var': 'x'}, {'operator': 'IMPLIES', 'operands': [rx, bx]}]}
            other = {'predicate': 'STUDENT', 'roles': {'AGENT': {'entity': 'ivan'}}}
            conclusion = ARRIVE
        if p.get('shared_witness_proof'):
            combined = {'operator': 'AND', 'operands': [root, other]}
            _, paths, aids, _ = observation(s, 'correlation', combined, p['witnesses'][0],
                                           and_elimination=True, witness_ref=p['shared_witness_ref'])
            by_target = {s.store.ledger.data['supports'][sid]['conclusion_ref']: sid for sid in paths}
            supports = [by_target[s.formulas[digest(root)]], by_target[s.formulas[digest(other)]]]
            assertions = [next(aid for aid in aids if s.store.ledger.data['assertions'][aid]['support_record_id'] == sid) for sid in supports]
        elif p.get('same_source_tag'):
            roots, supports, assertions = s.prepare('unshared', [root, other], [base.witness(w) for w in p['witnesses']])
            s.commit('unshared')
        else:
            _, paths1, assertions1, _ = observation(s, 'uncorrelated-root', root, p['witnesses'][0])
            _, paths2, assertions2, _ = observation(s, 'uncorrelated-other', other, p['witnesses'][1])
            supports, assertions = paths1 + paths2, assertions1 + assertions2
        req, target = request_from_records(s, rule, root, [other], supports, assertions, conclusion)
        decision = execute(s.store, req)
        result = _goal_view(s, req, target, decision)
        # AND supplied two proof paths; this action reports the on-demand rule's
        # newly recorded conclusions, rather than counting its premise paths.
        result['derived']['support_count'] = sum(v['kind'] == 'DERIVED' and v.get('rule_id') == rule for v in s.store.ledger.data['supports'].values())
        return result
    if action == 'retract_time_path':
        variant, scope = p['source_support_variant'], p['trigger_scope']
        ground = None
        if scope in {'BINDING', 'PREMISE'}:
            _, ground_paths, _, _ = observation(s, 'binding-ground', OTHER)
            ground = ground_paths[0]
        if variant == 'OBSERVATION_ROOT':
            _, paths, aids, _ = observation(s, 'time-source', ATOM, {'kind': 'POINT', 't': 5}, binding_premise=ground)
            original, aid = paths[0], aids[0]
        elif variant == 'OBSERVATION_AND_DERIVED':
            _, paths, aids, _ = observation(s, 'time-source', {'operator': 'AND', 'operands': [ATOM, OTHER]},
                                           {'kind': 'POINT', 't': 5}, and_elimination=True, binding_premise=ground)
            original = next(sid for sid in paths if s.store.ledger.data['supports'][sid]['conclusion_ref'] == s.formulas[digest(ATOM)])
            aid = next(a for a in aids if s.store.ledger.data['assertions'][a]['support_record_id'] == original)
        else:
            from tools.formalizer_v7_extended_binding import OR, NOT
            _, roots, ra, _ = observation(s, 'time-source', OR, {'kind': 'POINT', 't': 5}, binding_premise=ground)
            _, nots, na, _ = observation(s, 'negative-source', NOT, {'kind': 'POINT', 't': 5})
            req, target = request_from_records(s, 'OR_ELIMINATION', OR, [NOT], roots + nots, ra + na, ATOM)
            d = execute(s.store, req)
            original, aid = d['support_record_id'], d['assertion_refs'][0]
        s.aliases[p['assertion_id']] = aid
        before = len(s.store._journal.scan_unprocessed(0))
        if scope == 'OBSERVATION':
            s.store.retract_observation(*s.sources['time-source'], trigger_ref='oracle:whole-observation')
        elif scope == 'ASSERTION':
            s.store.retract(aid, reason='oracle:exact-assertion')
        elif scope == 'BINDING':
            s.store.retract(s.aliases['B'], reason='oracle:binding-invalid')
        elif scope == 'PREMISE':
            s.store.retract(ground, reason='oracle:binding-premise-dead')
        else:
            raise ValueError('UNKNOWN_RETRACTION_SCOPE')
        rows = s.store._journal.scan_unprocessed(0)[before:]
        actual = s.store.ledger.data['assertions'][aid]
        result = s.snapshot()
        result['time_assertions'][p['assertion_id']] = {'status': actual['status'], 'effective': s.store.ledger.evidence_live({'record_id': aid})}
        # Count durable status transitions of this assertion, including the
        # source-level atomic retraction unit that contains that transition.
        result['journal']['time_retraction_count'] = sum(
            r['payload'].get('kind') == 'canonical_unit'
            and (r['payload'].get('extra') or {}).get('kind') == 'RETRACTION'
            and actual['status'] == 'RETRACTED' for r in rows)
        result['supports']['original_alive'] = original in s.store.ledger.paths()
        s.api.add('AHStoreAdapter.retract / retract_observation / canonical proof-path cascade')
        return result
    if action == 'seed_without_incompatibility':
        for index, (formula, window) in enumerate(zip(p['formulas'], p['windows'])):
            observation(s, 'late-conflict-O' + str(index + 1), formula, window)
        s.temporal_conflict_seed = True
        result = s.snapshot(); result['reports']['count'] = len(s.store.ledger.data['reports'])
        return result
    if action == 'change_declared_resource' and getattr(s, 'temporal_conflict_seed', False):
        manifest = deepcopy(s.release.manifest)
        sense = s.templates[('LOCATIVE', ('LOCATION', 'THEME'))]['sense_id']
        for row in manifest['entries']:
            if row['kind'] == 'IncompatibilityRules':
                row['entries'] = [{'kind': 'ROLE_EXCLUSIVE', 'rule_id': p['rule'], 'sense_id': sense,
                                   'role_id': 'LOCATION', 'key_roles': ['OBJECT']}]
                row['version'] = 'test-late-v' + str(p['version'])
                manifest['dependency_versions'][row['kind']] = row['version']
        manifest.pop('signed_review_id', None)
        manifest.pop('coverage_report', None)
        manifest['coverage_report'] = {
            'corpus_id': 'isolated-late-conflict-release', 'corpus_sha256': digest([]),
            'units_by_kind': {row['kind']: len(row['entries']) for row in manifest['entries']},
            'categories': {kind: 0 for kind in ('COVERED', 'NOT_COVERED', 'KNOWLEDGE_ABSENT', 'OOV_KEEP_AS_IS')},
            'resource_content_sha256': digest(manifest),
            'measurement_kind': 'RESOURCE_LEXICAL_AVAILABILITY', 'measured_units': [],
            'execution_coverage': None,
        }
        release, _ = sign_test_release(manifest)
        before = sum(v['status'] != 'LIVE' for v in s.store.ledger.data['supports'].values())
        s.store.rescan_conflicts(release, trigger_ref='oracle:declared-resource-change')
        s.release = release
        result = s.snapshot()
        result['store']['auto_retraction_count'] = sum(v['status'] != 'LIVE' for v in s.store.ledger.data['supports'].values()) - before
        s.api.add('AHStoreAdapter.rescan_conflicts / independently reviewed IncompatibilityRules')
        return result
    if action == 'proof_independence':
        from ah.formalizer.proof_closure import independent, source_premise_closure
        paths = []
        for source in p['observation_sources']:
            shared = p['shared_ground']
            metadata = ({'rule_refs': [{'kind': shared, 'record_id': 'shared'}]} if shared == 'R'
                        else {'factual_ground_refs': [{'kind': shared, 'source': {'record_id': 'shared', 'version': 1}}]})
            _, own, _, _ = observation(s, source, ATOM, support_metadata=metadata)
            paths.extend(own)
        value = independent(s.store.ledger, *paths)
        closures = [source_premise_closure(s.store.ledger, sid) for sid in paths]
        s.store.retract_observation(*s.sources[p['observation_sources'][0]], trigger_ref='oracle:independence')
        s.api.add('proof_closure.source_premise_closure / independent / path-local observation retraction')
        return {**s.snapshot(), 'proof': {'independent': value, 'closures': closures,
                                        'retract_O1_keeps_s2': paths[1] in s.store.ledger.paths()}}
    if action == 'derive_operator_conclusion':
        conclusion, rule = p['conclusion'], p['rule_id']
        if rule == 'AND_ELIMINATION':
            root = {'operator': 'AND', 'operands': [conclusion, ATOM]}
            observation(s, 'operator-and', root, and_elimination=True, only_conclusion=conclusion)
            target = s.formulas[digest(conclusion)]
        elif rule == 'OR_ELIMINATION':
            root = {'operator': 'OR', 'operands': [conclusion, ATOM]}
            negative = {'operator': 'NOT', 'operands': [ATOM]}
            _, rpaths, ra, _ = observation(s, 'operator-or', root)
            _, npaths, na, _ = observation(s, 'operator-not', negative)
            req, target = request_from_records(s, rule, root, [negative], rpaths + npaths, ra + na, conclusion)
            d = execute(s.store, req); target = d.get('conclusion_ref', target)
        else:
            def variable(x):
                if x == {'entity': 'ivan'}: return {'bound_var': 'x'}
                if isinstance(x, dict): return {k: variable(v) for k, v in x.items()}
                if isinstance(x, list): return [variable(v) for v in x]
                return x
            restriction = {'predicate': 'STUDENT', 'roles': {'AGENT': {'bound_var': 'x'}}}
            member = {'predicate': 'STUDENT', 'roles': {'AGENT': {'entity': 'ivan'}}}
            root = {'operator': 'FORALL', 'operands': [{'bound_var': 'x'}, {'operator': 'IMPLIES', 'operands': [restriction, variable(conclusion)]}]}
            _, roots, ra, _ = observation(s, 'operator-forall', root)
            _, members, ma, _ = observation(s, 'operator-member', member)
            req, target = request_from_records(s, rule, root, [member], roots + members, ra + ma, conclusion)
            d = execute(s.store, req); target = d.get('conclusion_ref', target)
        L = s.store.ledger
        supports = [v for v in L.data['supports'].values() if v['conclusion_ref'] == target]
        node = L.data['nodes'].get(target, {})
        result = s.snapshot()
        result['derived'].update(conclusion_type=s.store._store.kind_of(target).value if s.store.has_uid(target) else None,
                                 root_support_count=sum(v['kind'] == 'ROOT' for v in supports),
                                 support_count=sum(v['kind'] == 'DERIVED' for v in supports))
        result['operands'] = {'independent_truth_count': sum(v in L.f_visible() for v in node.get('operands', ()) if isinstance(v, str))}
        return result
    if action == 'multi_premise_inference':
        from ah.formalizer.inference_engine import InferenceEngine, InferenceRule
        from ah.formalizer.temporal_constraints import derive_declared_region
        engine = InferenceEngine()
        # A declared extension is an independent test fixture, not an implicit
        # new entry in the production goal rule table or a claim about truth.
        engine.rules[p['rule']] = InferenceRule(p['rule'], 'CUSTOM', 'DECLARED')
        codes = []
        try:
            rule = engine.rule(p['rule'])
            region = base.region(base.witness(p['declared_result_region'])) if p.get('declared_result_region') else None
            result_region = derive_declared_region(rule, [base.region(base.witness(w)) for w in p['premises']], region)
        except KeyError:
            result_region = None; codes = ['GOAL_RULE_UNKNOWN']
        except ValueError as exc:
            result_region = None; codes = [str(exc)]
        if result_region is None and not codes:
            codes = ['INFERENCE_TEMPORAL_MISMATCH']
        s.api.add('InferenceEngine.rule / derive_interval registered rule validation')
        return {**s.snapshot(), 'answer': {'status': 'UNKNOWN'},
                'derived': {'support_count': 0, 'declared_result_region': p.get('declared_result_region')},
                'diagnostics': {'codes': codes}}
    if action == 'open_or_cross_source':
        # Explicit occurrence-local open T identities are authored fixture
        # inputs. Their spelling is not a TemplateMap or identity assertion.
        source1, source2 = p['or_operand_observation'], p['not_operand_observation']
        from ah.formalizer.resources.registry import (OpenPredicateCandidate, Role, RoleBinding,
            RoleRegistry, OpenTemplatePolicy, ensure_open_template)
        candidates = []
        for source in (source1, source2):
            candidate = OpenPredicateCandidate(source, 1, ('span',), p['same_surface'], 'VERB',
                                              (RoleBinding('SUBJECT', 'ENTITY'),))
            candidates.append(ensure_open_template(candidate, RoleRegistry(frozenset({Role('SUBJECT'), Role('EXPERIENCER'), Role('SURFACE_ARG')})),
                                                   OpenTemplatePolicy(released=True)))
        first = {'predicate': 'OPEN:' + source1, 'roles': {'AGENT': {'entity': 'ivan'}}}
        second = {'predicate': 'OPEN:' + source2, 'roles': {'AGENT': {'entity': 'ivan'}}}
        forms = [{'operator': 'OR', 'operands': [first, ATOM]}, {'operator': 'NOT', 'operands': [second]}]
        supports, assertions = [], []
        for source, candidate, atom, form in zip((source1, source2), candidates, (first, second), forms):
            tid = 'fixture:T:open:' + candidate.open_template_key
            sense = 'OPEN:' + candidate.open_template_key
            s.templates[(atom['predicate'], ('AGENT',))] = {'uid': tid, 'sense_id': sense, 'roles': {'AGENT': 'SUBJECT'}}
            fragment = source + ':F'; tag = ['oracle:' + source, 1]
            ops = [StoreOp('ENSURE_TEMPLATE', {'uid': tid, 'semantic_status': 'UNLINKED',
                         'predicate_form': p['same_surface'], 'roles': ['SUBJECT']}, (fragment,))]
            uid, key, prop, polarity = s.tree(form, fragment, ops)
            ops = [replace(op, payload={**op.payload, 'semantic_status': 'UNLINKED'})
                   if op.op_type == 'ENSURE_NODE' and op.payload.get('template_ref') == tid else op for op in ops]
            sid = 'fixture:open-root:' + source
            ops.append(StoreOp('ADD_ROOT_SUPPORT', {'record_id': sid, 'conclusion_ref': uid,
                       'kind': 'ROOT', 'ground_type': 'O', 'source_tag': tag}, (fragment,)))
            if p.get('same_time'):
                aid = 'fixture:open-time:' + source
                ops.append(StoreOp('ADD_TIME_ASSERTION', {'assertion_id': aid, 'target_ref': uid,
                    'support_record_id': sid, 'region': {'kind': 'POINT', 'point': 5}, 'anchor': None,
                    'provenance': {'source': {'kind': 'OBSERVATION', 'source_tag': tag}, 'support': {'kind': 'ROOT'}}}, (fragment,)))
                assertions.append(aid)
            ops.append(StoreOp('DECLARE_FRAGMENT', {'fragment_id': fragment, 'node_ref': uid,
                       'content_key': key, 'proposition': prop, 'polarity': polarity, 'source_tag': tag}, (fragment,)))
            _commit_ops(s, source, ops, [fragment]); supports.append(sid)
        target = s.formulas[digest(first)]
        req = GoalRequest('GR-open', 'OR_ELIMINATION', tuple(supports),
                          digest(s.store.ledger.data['nodes'][target]['proposition']),
                          temporal_premise_assertion_refs=tuple(assertions), conclusion_ref=target)
        decision = execute(s.store, req)
        s.api.add('registry.ensure_open_template / AHStoreAdapter typed open roots / goal_channel.validate_goal')
        result = _goal_view(s, req, target, decision)
        result['aliases'] = list(s.store.ledger.data['open_template_links'])
        result['open'] = {'identity_keys': [v.open_template_key for v in candidates]}
        return result
    if action == 'change_conflict_evidence':
        if p['retract_before_recovery']:
            reports = list(s.store.ledger.data['decisions'].values())
            refs = [e['record_id'] for D in reports for item in D.get('excluded_evidence', ())
                    for e in item.get('evidence_refs', ()) if e['kind'] == 'COMMITTED']
            if not refs:
                raise ValueError('FIXTURE_HAS_NO_CONFLICT_EVIDENCE')
            for ref in sorted(set(refs)):
                s.store.retract(ref, reason='oracle:conflict-evidence-change-before-recovery')
        s.api.add('AHStoreAdapter.retract concrete conflict evidence before decision recovery')
        return s.snapshot()
    if action == 'seed_temporal_or':
        root, negative = p['or_formula'], p['not_formula']
        _, roots, ra, _ = observation(s, 'O_or', root, p['or_window'])
        _, nots, na, _ = observation(s, 'O_not_old', negative, p['not_window'])
        s.temporal_or = {'root': root, 'negative': negative, 'root_paths': roots,
                         'root_assertions': ra, 'not_paths': nots, 'not_assertions': na,
                         'not_source': 'O_not_old', 'run': 0}
        return s.snapshot()
    if action == 'replace_not_observation':
        state = s.temporal_or
        s.store.retract_observation(*s.sources[p['old_source']], trigger_ref='oracle:replace-negative-observation')
        _, paths, assertions, _ = observation(s, p['new_source'], state['negative'], p['not_window'])
        state.update(not_paths=paths, not_assertions=assertions, not_source=p['new_source'])
        return s.snapshot()
    if action == 'derive_or' and hasattr(s, 'temporal_or'):
        state = s.temporal_or; state['run'] += 1
        conclusion = next(form for form in state['root']['operands'] if form != state['negative']['operands'][0])
        req, target = request_from_records(s, 'OR_ELIMINATION', state['root'], [state['negative']],
                                           state['root_paths'] + state['not_paths'],
                                           state['root_assertions'] + state['not_assertions'],
                                           conclusion, 'GR' + str(state['run']))
        reason, _, _ = validate_goal(s.store.ledger, req, s.store._core)
        if reason:
            result = _preflight_view(s, req, target, reason)
            if reason == 'GOAL_LICENSE_FAILED':
                result['diagnostics']['codes'] = ['OR_ELIMINATION_TEMPORAL_MISMATCH']
        else:
            req = replace(req, request_window=tuple(p['root_witness']['bounds']) if p['root_witness']['kind'] == 'INTERVAL' else None)
            decision = execute(s.store, req)
            result = _goal_view(s, req, target, decision)
        return result
    if action == 'derive_forall':
        root, member = p['quantified_root'], p['restriction']
        def existing(formula):
            ref = s.formulas.get(digest(formula))
            live = s.store.ledger.paths()
            return next((sid for sid, support in s.store.ledger.data['supports'].items()
                         if sid in live and support['conclusion_ref'] == ref), None)
        supports, assertions = [], []
        for form, source, window in ((root, 'O_quantifier', p.get('root_witness')),
                                     (member, 'O_membership', p.get('restriction_witness'))):
            sid = existing(form)
            if sid is None:
                _, own, aids, _ = observation(s, source, form, window)
                sid = own[0]
            else:
                record = s.store.ledger.data['supports'][sid]
                if record.get('source_tag'): s.sources[source] = record['source_tag']
                aids = [aid for aid, a in s.store.ledger.data['assertions'].items() if a['support_record_id'] == sid]
            supports.append(sid); assertions.extend(aids)
        variable = root['operands'][0]['bound_var']
        replacement = next(iter(member['roles'].values()))
        def substitute(value):
            if value == {'bound_var': variable}: return replacement
            if isinstance(value, dict): return {key: substitute(item) for key, item in value.items()}
            if isinstance(value, list): return [substitute(item) for item in value]
            return value
        conclusion = substitute(root['operands'][1]['operands'][1])
        req, target = request_from_records(s, 'FORALL_INST', root, [member], supports, assertions, conclusion)
        before_markers = len(s.store.ledger.data['markers'])
        before_versions = sum(r['payload'].get('kind') == 'run_bind' for r in s.store._journal.scan_unprocessed(0))
        before_instances = sum(record['kind'] == 'DERIVED' and record.get('rule_id') == 'FORALL_INST'
                               for record in s.store.ledger.data['supports'].values())
        reason, _, _ = validate_goal(s.store.ledger, req, s.store._core)
        if reason:
            result = _preflight_view(s, req, target, reason)
        else:
            decision = execute(s.store, req)
            result = _goal_view(s, req, target, decision)
        if reason == 'GOAL_LICENSE_FAILED':
            from ah.formalizer.temporal_license import forall_inst_license
            lic = forall_inst_license(base.region(base.witness(p.get('root_witness'))),
                                      base.region(base.witness(p.get('restriction_witness'))))
            result['diagnostics']['codes'] = ['FORALL_INST_TEMPORAL_MISMATCH']
            if lic.diagnostic: result['diagnostics']['codes'].append(lic.diagnostic)
        result.setdefault('goal', {}).update(new_marker_count=len(s.store.ledger.data['markers']) - before_markers,
                                            new_interpretation_version_count=sum(r['payload'].get('kind') == 'run_bind'
                                                for r in s.store._journal.scan_unprocessed(0)) - before_versions)
        result['commit']['instances_before_goal'] = before_instances
        s.aliases['quantified_root'] = s.formulas[digest(root)]
        return result
    if action in {'derive_or', 'change_declared_resource'}:
        return NotImplemented
    raise ValueError('UNBOUND_TEMPORAL_ACTION:' + action)
