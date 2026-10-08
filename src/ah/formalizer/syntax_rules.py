"""Bounded interpreter for released SyntaxRules; no executable resource callbacks.

Rules join whole R1 variants, apply declared constraints and emit local structural
candidates. Priority orders the search, never chooses a winning interpretation.
Exhaustion discards the incomplete enumeration and asks TP to cover the region.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re

from .canonical_ledger import digest
from .state import BoundaryCandidate, ClauseCandidate, EllipsisCandidate, ResourceProvenance, TokenHypothesis
from .tp_proposer import Hypothesis, TNode, TEdge, StructureProposalRequest, _validate_hypothesis
from .selection_protocol import ProtocolError

FEATURES = {'lemma', 'POS', 'cases', 'number', 'gender', 'person', 'tense', 'mood', 'features', 'surface', 'oov'}
RELATIONS = {'BEFORE', 'AFTER', 'ADJACENT', 'OVERLAPS', 'CONTAINS', 'AGREES'}
OUTPUTS = {'CANDIDATE_GRAPH', 'CLAUSE_BOUNDARY', 'ELLIPSIS', 'TOKEN_HYPOTHESIS'}
NODE_KINDS = {'PREDICATE', 'ENTITY', 'BOUND_VAR', 'NOT', 'AND', 'OR', 'XOR', 'IMPLIES', 'FORALL', 'EXISTS', 'POSSIBLE', 'NECESSARY', 'COUNTERFACTUAL', 'BEFORE', 'AFTER', 'DURING', 'ASSOCIATION'}


class SyntaxRuleError(ValueError):
    pass


class SearchLimit(SyntaxRuleError):
    pass


def _check_field(field, captures):
    if not isinstance(field, str) or field.count('.') != 1:
        raise SyntaxRuleError('feature field must be capture.feature')
    name, feature = field.split('.')
    if name not in captures or feature not in FEATURES:
        raise SyntaxRuleError('unknown capture/feature field')


def _ast_schema(expr, captures, reads, depth=0):
    if not isinstance(expr, dict) or depth > 16 or 'op' not in expr:
        raise SyntaxRuleError('invalid predicate_AST')
    op = expr['op']
    if op in {'AND', 'OR'}:
        if set(expr) != {'op', 'args'} or not isinstance(expr['args'], list) or not 1 <= len(expr['args']) <= 64:
            raise SyntaxRuleError('invalid AST junction')
        for child in expr['args']: _ast_schema(child, captures, reads, depth + 1)
    elif op == 'NOT':
        if set(expr) != {'op', 'arg'}: raise SyntaxRuleError('invalid AST negation')
        _ast_schema(expr['arg'], captures, reads, depth + 1)
    elif op in {'feature_eq', 'feature_in'}:
        key = 'value' if op == 'feature_eq' else 'values'
        if set(expr) != {'op', 'field', key}: raise SyntaxRuleError('invalid feature check')
        _check_field(expr['field'], captures)
        values = [expr[key]] if op == 'feature_eq' else expr[key]
        if not isinstance(values, list) or not values or any(type(v) not in {str, bool, int, float} for v in values):
            raise SyntaxRuleError('invalid feature-check values')
    elif op == 'span_relation':
        if set(expr) != {'op', 'left', 'right', 'relation'} or expr['left'] not in captures or expr['right'] not in captures or expr['relation'] not in RELATIONS - {'AGREES'}:
            raise SyntaxRuleError('invalid span relation')
    elif op == 'agreement':
        if not {'op', 'left', 'right'} <= set(expr) or not set(expr) <= {'op', 'left', 'right', 'features'} or expr['left'] not in captures or expr['right'] not in captures or not expr.get('features', ['gender','number']) or not set(expr.get('features', ['gender','number'])) <= {'number', 'gender', 'person', 'cases'}:
            raise SyntaxRuleError('invalid AST agreement')
    elif op == 'window_has':
        if set(expr) != {'op', 'source', 'expr'} or expr['source'] not in {'TOKEN', 'R1'}:
            raise SyntaxRuleError('window_has reads only the bounded R1 token window')
        _ast_schema(expr['expr'], captures | {'item'}, reads, depth + 1)
    elif op == 'schema_lookup':
        if set(expr) != {'op', 'resource', 'key'} or expr['resource'] not in reads or not isinstance(expr['key'], dict) or not expr['key']:
            raise SyntaxRuleError('undeclared schema lookup')
        for key, value in expr['key'].items():
            if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)*', key):
                raise SyntaxRuleError('invalid lookup path')
            if isinstance(value, dict):
                if set(value) != {'field'}: raise SyntaxRuleError('invalid lookup binding')
                _check_field(value['field'], captures)
            elif type(value) not in {str, bool, int, float}: raise SyntaxRuleError('invalid lookup value')
    else:
        raise SyntaxRuleError('unknown Rule DSL v1 operator: ' + str(op))


def _junction(values, kind):
    if kind == 'AND': return False if False in values else None if None in values else True
    return True if True in values else None if None in values else False


def _ast_value(field, assignment, state):
    capture, feature = field.split('.')
    if capture not in assignment: return None
    i, variant = assignment[capture]
    return _feature_value(variant, state.evidence[i], feature)


def evaluate_ast(expr, assignment, state, release, window, spend):
    spend()
    op = expr['op']
    if op in {'AND', 'OR'}:
        return _junction([evaluate_ast(child, assignment, state, release, window, spend) for child in expr['args']], op)
    if op == 'NOT':
        value = evaluate_ast(expr['arg'], assignment, state, release, window, spend)
        return None if value is None else not value
    if op in {'feature_eq', 'feature_in'}:
        actual = _ast_value(expr['field'], assignment, state)
        if actual is None or actual == frozenset(): return None
        values = [expr['value']] if op == 'feature_eq' else expr['values']
        return bool(set(actual) & set(values)) if isinstance(actual, (set, frozenset)) else actual in values
    if op == 'span_relation':
        if expr['left'] not in assignment or expr['right'] not in assignment: return None
        a, b = (state.evidence[assignment[name][0]] for name in (expr['left'], expr['right']))
        relation = expr['relation']
        if relation == 'BEFORE': return a.end <= b.start
        if relation == 'AFTER': return b.end <= a.start
        if relation == 'ADJACENT': return assignment[expr['right']][0] == assignment[expr['left']][0] + 1
        if relation == 'OVERLAPS': return max(a.start,b.start) < min(a.end,b.end)
        return a.start <= b.start and b.end <= a.end
    if op == 'agreement':
        if expr['left'] not in assignment or expr['right'] not in assignment: return None
        a, b = (assignment[name][1] for name in (expr['left'], expr['right']))
        values = []
        for feature in expr.get('features', ['gender','number']):
            x, y = getattr(a, feature, None), getattr(b, feature, None)
            values.append(None if x is None or y is None or x == frozenset() or y == frozenset() else bool(x & y) if isinstance(x, frozenset) else x == y)
        return _junction(values, 'AND')
    if op == 'window_has':
        lo, hi = window
        values = [evaluate_ast(expr['expr'], {**assignment,'item':(i,v)}, state, release, window, spend)
                  for i in range(lo,hi) for v in state.evidence[i].variants or (None,)]
        return _junction(values, 'OR') if values else None
    expected = {path: _ast_value(value['field'], assignment, state) if isinstance(value, dict) else value for path, value in expr['key'].items()}
    if any(v is None or v == frozenset() for v in expected.values()): return None
    def get(row, path):
        for name in path.split('.'):
            if not isinstance(row, dict) or name not in row: return None
            row = row[name]
        return row
    for row in release.entries(expr['resource']):
        spend()
        found=True
        for path,value in expected.items():
            spend()
            if get(row,path) != value:
                found=False; break
        if found: return True
    return None  # LOOKUP NOT_FOUND is absence, never a false semantic assertion.


def _feature_schema(pattern, depth=0):
    if not isinstance(pattern, dict) or not pattern or depth > 16:
        raise SyntaxRuleError('invalid feature AST')
    if set(pattern) in ({'all'}, {'any'}):
        values = next(iter(pattern.values()))
        if not isinstance(values, list) or not 1 <= len(values) <= 64:
            raise SyntaxRuleError('empty feature junction')
        for value in values:
            _feature_schema(value, depth + 1)
    elif set(pattern) == {'not'}:
        _feature_schema(pattern['not'], depth + 1)
    else:
        if not set(pattern) <= FEATURES:
            raise SyntaxRuleError('unknown feature field')
        for key, values in pattern.items():
            if key == 'oov':
                if type(values) is not bool:
                    raise SyntaxRuleError('oov must be boolean')
            elif not isinstance(values, list) or not values or any(not isinstance(v, str) or not v for v in values):
                raise SyntaxRuleError('feature values must be nonempty strings')
            elif key in {'surface', 'lemma'} and any(any(c.isspace() for c in v) for v in values):
                raise SyntaxRuleError('lexical captures cannot contain a full sentence')


def validate_rules(rules, roles, declared_reads=()):
    seen = set()
    for rule in rules:
        required = {'rule_id', 'input_feature_pattern', 'output_kind', 'output', 'constraints', 'priority', 'min_evidence', 'coverage_tag'}
        if not required <= set(rule) or not set(rule) <= required | {'stage'}:
            raise SyntaxRuleError('incomplete/unknown SyntaxRules fields')
        rid = rule['rule_id']
        if not isinstance(rid, str) or not rid or rid in seen:
            raise SyntaxRuleError('duplicate/empty rule_id')
        seen.add(rid)
        pattern = rule['input_feature_pattern']
        if not isinstance(pattern, dict) or not {'captures'} <= set(pattern) or not set(pattern) <= {'captures', 'window', 'distinct', 'where'}:
            raise SyntaxRuleError('invalid capture pattern')
        captures = pattern['captures']
        if not isinstance(captures, dict) or not 1 <= len(captures) <= 16 or 'item' in captures or any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', k) for k in captures):
            raise SyntaxRuleError('invalid capture names/count')
        for features in captures.values():
            _feature_schema(features)
        if 'where' in pattern:
            _ast_schema(pattern['where'], set(captures), set(declared_reads))
        if pattern.get('window', 'SENTENCE') not in {'SENTENCE', 'CLAUSE'} or type(pattern.get('distinct', True)) is not bool:
            raise SyntaxRuleError('invalid window/distinct flag')
        if type(rule['priority']) is not int or type(rule['min_evidence']) is not int or not 1 <= rule['min_evidence'] <= len(captures) or not rule['coverage_tag']:
            raise SyntaxRuleError('invalid priority/evidence/coverage')
        if rule['output_kind'] not in OUTPUTS or rule.get('stage', 'T2' if rule['output_kind'] == 'CANDIDATE_GRAPH' else 'SRL') != ('T2' if rule['output_kind'] == 'CANDIDATE_GRAPH' else 'SRL'):
            raise SyntaxRuleError('invalid output stage/kind')
        if not isinstance(rule['constraints'], list):
            raise SyntaxRuleError('constraints must be a list')
        for constraint in rule['constraints']:
            if not isinstance(constraint, dict) or not {'kind', 'left', 'right'} <= set(constraint) or not set(constraint) <= {'kind', 'left', 'right', 'features'}:
                raise SyntaxRuleError('invalid constraint')
            if constraint['kind'] not in RELATIONS or constraint['left'] not in captures or constraint['right'] not in captures:
                raise SyntaxRuleError('unknown relation/capture')
            if constraint['kind'] == 'AGREES' and (not constraint.get('features') or not set(constraint['features']) <= {'number', 'gender', 'person', 'cases'}):
                raise SyntaxRuleError('invalid agreement features')
        output = rule['output']
        if not isinstance(output, dict):
            raise SyntaxRuleError('output must be an object')
        if rule['output_kind'] == 'CANDIDATE_GRAPH':
            if set(output) != {'nodes', 'edges'} or not isinstance(output['nodes'], list) or not isinstance(output['edges'], list):
                raise SyntaxRuleError('invalid graph output')
            names = set()
            for node in output['nodes']:
                if not {'id', 'kind', 'anchors'} <= set(node) or not set(node) <= {'id', 'kind', 'anchors'} or node['id'] in names or node['kind'] not in NODE_KINDS or not node['anchors'] or not set(node['anchors']) <= set(captures):
                    raise SyntaxRuleError('invalid output node')
                names.add(node['id'])
            for edge in output['edges']:
                if not {'kind', 'from', 'to'} <= set(edge) or not set(edge) <= {'kind', 'from', 'to', 'role_id', 'scope'} or edge['from'] not in names or edge['to'] not in names or edge['kind'] not in {'ARGUMENT', 'ATTITUDE', 'OPERAND', 'BIND'} or edge.get('role_id') is not None and edge['role_id'] not in roles or type(edge.get('scope', False)) is not bool:
                    raise SyntaxRuleError('invalid output edge')
            indices = {n['id']: i for i, n in enumerate(output['nodes'])}
            graph = Hypothesis(rid, tuple(TNode(n['kind'], tuple(n['anchors'])) for n in output['nodes']),
                               tuple(TEdge(e['kind'], indices[e['from']], indices[e['to']], e.get('role_id'), e.get('scope', False)) for e in output['edges']),
                               alignment=tuple(captures))
            try:
                _validate_hypothesis(StructureProposalRequest(rid, '', tuple(captures), allowed_node_kinds=frozenset(NODE_KINDS),
                                                             allowed_edge_kinds=frozenset({'ARGUMENT','ATTITUDE','OPERAND','BIND'}), allowed_role_ids=frozenset(roles)), graph)
            except ProtocolError as exc:
                raise SyntaxRuleError('invalid typed graph: '+str(exc)) from exc
        else:
            allowed = {'capture', 'side'} if rule['output_kind'] == 'CLAUSE_BOUNDARY' else {'capture', 'gap_kind', 'antecedent'} if rule['output_kind'] == 'ELLIPSIS' else {'capture', 'variants'}
            if not set(output) <= allowed or output.get('capture') not in captures:
                raise SyntaxRuleError('invalid structural output')
            if rule['output_kind'] == 'CLAUSE_BOUNDARY' and output.get('side', 'BEFORE') not in {'BEFORE', 'AFTER'}:
                raise SyntaxRuleError('invalid boundary side')
            if rule['output_kind'] == 'ELLIPSIS' and (output.get('gap_kind') not in {'PREDICATE_GAP', 'ARGUMENT_GAP', 'SUBORDINATOR_GAP'} or output.get('antecedent') is not None and output['antecedent'] not in captures):
                raise SyntaxRuleError('invalid ellipsis output')
            if rule['output_kind'] == 'TOKEN_HYPOTHESIS' and (not isinstance(output.get('variants'), list) or 'keep_as_is' not in output['variants'] or any(not isinstance(v, str) or not v for v in output['variants'])):
                raise SyntaxRuleError('KEEP_AS_IS missing')


def _feature_value(variant, token, key):
    if key == 'surface':
        return token.span.casefold()
    if key == 'oov':
        return variant is None or variant.lemma is None
    return getattr(variant, 'pos' if key == 'POS' else key, None) if variant is not None else None


def matches(pattern, token, variant, spend):
    """Three-valued predicates: missing features cannot prove a negated guard."""
    spend()
    if set(pattern) == {'not'}:
        value = matches(pattern['not'], token, variant, spend)
        return None if value is None else not value
    if set(pattern) in ({'all'}, {'any'}):
        kind = next(iter(pattern))
        values = [matches(p, token, variant, spend) for p in pattern[kind]]
        if kind == 'all':
            return False if False in values else None if None in values else True
        return True if True in values else None if None in values else False
    values = []
    for key, allowed in pattern.items():
        spend()
        actual = _feature_value(variant, token, key)
        if actual is None or actual == frozenset():
            values.append(None)
        elif key == 'oov':
            values.append(actual == allowed)
        elif isinstance(actual, (set, frozenset)):
            values.append(bool(set(actual) & set(allowed)))
        else:
            values.append(actual in (set(v.casefold() for v in allowed) if key == 'surface' else allowed))
    return False if False in values else None if None in values else True


def _constraint(c, assignment):
    if c['left'] not in assignment or c['right'] not in assignment:
        return True
    (i, a), (j, b) = assignment[c['left']], assignment[c['right']]
    kind = c['kind']
    if kind == 'BEFORE': return i < j
    if kind == 'AFTER': return i > j
    if kind == 'ADJACENT': return j == i + 1
    if kind in {'OVERLAPS', 'CONTAINS'}: return i == j
    for feature in c['features']:
        x, y = getattr(a, feature, None), getattr(b, feature, None)
        if x is None or y is None or x == frozenset() or y == frozenset(): return None
        if isinstance(x, frozenset):
            if not (x & y): return False
        elif x != y: return False
    return True


@dataclass(frozen=True)
class RuleMatch:
    rule: dict
    assignment: dict
    window: tuple[int, int]


def _windows(state, kind):
    n = len(state.evidence)
    if kind == 'CLAUSE' and state.clause_candidates:
        return sorted({(a, b + 1) for c in state.clause_candidates for a, b in c.segmentation if a <= b})
    windows = []
    start = 0
    for i, token in enumerate(state.evidence):
        if token.span in {'.', '!', '?', ';'}:
            if start < i: windows.append((start, i + 1))
            start = i + 1
    if start < n: windows.append((start, n))
    return windows


def enumerate_matches(state, rules, stage, policy, release):
    limit = policy.get('max_rule_steps', 20000)
    max_matches = policy.get('max_rule_matches', 256)
    steps = 0
    out = []
    def spend():
        nonlocal steps
        steps += 1
        if steps > limit:
            state.syntax_trace.append({'stage':stage,'event':'LIMIT','step':steps,'result':'COMPUTATION_LIMIT'})
            raise SearchLimit('COMPUTATION_LIMIT: SyntaxRules matching/joins/AST')
    def trace(rule, event, result, assignment=None, **details):
        state.syntax_trace.append({'rule_id':rule['rule_id'],'stage':stage,'event':event,'step':steps,
                                   'result':result,'captures':{name:state.evidence[i].token_id for name,(i,v) in (assignment or {}).items()},**details})
    for rule in sorted(rules, key=lambda r: (-r['priority'], r['rule_id'])):
        if rule.get('stage', 'T2' if rule['output_kind'] == 'CANDIDATE_GRAPH' else 'SRL') != stage: continue
        pattern = rule['input_feature_pattern']
        captures = sorted(pattern['captures'])
        for lo, hi in _windows(state, pattern.get('window', 'SENTENCE')):
            if hi-lo > policy['max_source_tokens']:
                trace(rule,'LIMIT','COMPUTATION_LIMIT',window=[lo,hi])
                raise SearchLimit('COMPUTATION_LIMIT: SyntaxRules source window')
            options = {}
            for capture in captures:
                options[capture] = []
                for i in range(lo, hi):
                    token = state.evidence[i]
                    for variant_index,variant in enumerate(token.variants or (None,)):
                        spend()
                        truth = matches(pattern['captures'][capture], token, variant, spend)
                        trace(rule,'FEATURE_CHECK',truth,capture=capture,token_ref=token.token_id,variant_index=variant_index)
                        if truth is True:
                            options[capture].append((i, variant))
            def walk(k, assignment):
                if k == len(captures):
                    truth = evaluate_ast(pattern['where'], assignment, state, release, (lo,hi), spend) if 'where' in pattern else True
                    trace(rule,'PREDICATE_CHECK',truth,assignment)
                    if truth is True and len({i for i, v in assignment.values()}) >= rule['min_evidence']:
                        out.append(RuleMatch(rule, dict(assignment), (lo, hi)))
                        if len(out) > max_matches:
                            trace(rule,'LIMIT','COMPUTATION_LIMIT',assignment)
                            raise SearchLimit('COMPUTATION_LIMIT: SyntaxRules matches')
                    return
                name = captures[k]
                for choice in options[name]:
                    spend()
                    reused = [(i,v) for i,v in assignment.values() if i == choice[0]]
                    if reused and (pattern.get('distinct', True) or any(v != choice[1] for i,v in reused)):
                        trace(rule,'CAPTURE_COHERENCE',False,assignment,capture=name,token_ref=state.evidence[choice[0]].token_id)
                        continue
                    assignment[name] = choice
                    guards=[]
                    for c in rule['constraints']:
                        spend()
                        guards.append(_constraint(c, assignment))
                    compatible = _junction(guards, 'AND') if guards else True
                    trace(rule,'CONSTRAINT_CHECK',compatible,assignment)
                    if compatible is True: walk(k + 1, assignment)
                    del assignment[name]
            walk(0, {})
    return out


def _plain_variant(variant):
    from dataclasses import asdict
    return {k:sorted(v) if isinstance(v,(set,frozenset)) else v for k,v in asdict(variant).items()} if variant else None


def _identity(match, state):
    return 'syntax:' + digest([match.rule['rule_id'], match.window, {name: [state.evidence[i].token_id, _plain_variant(v)] for name, (i, v) in match.assignment.items()}])


def run_srl(state, release, morph):
    from .pipeline import MorphProvider
    provider = morph or MorphProvider()
    for token in state.evidence:
        token.variants = tuple(provider.analyze(token.span))
    try:
        found = enumerate_matches(state, release.entries('SyntaxRules'), 'SRL', release.entries('ProposalPolicy')[0], release)
    except SearchLimit as exc:
        state.grammar_search_incomplete=True
        state.diag('COMPUTATION_LIMIT', str(exc)); found = []
    for match in found:
        output = match.rule['output']; i, v = match.assignment[output['capture']]
        token = state.evidence[i]; rid = _identity(match, state)
        prov = ResourceProvenance((match.rule['rule_id'],), {'SyntaxRules': release.version('SyntaxRules'), 'release': release.sha256})
        kind = match.rule['output_kind']
        if kind == 'CLAUSE_BOUNDARY':
            state.boundary_candidates.append(BoundaryCandidate(rid, i + (output.get('side', 'BEFORE') == 'AFTER'), provenance=prov))
        elif kind == 'ELLIPSIS':
            antecedent = output.get('antecedent')
            state.ellipsis_candidates.append(EllipsisCandidate(rid, token.span, output['gap_kind'], state.evidence[match.assignment[antecedent][0]].span if antecedent else None, provenance=prov))
        elif kind == 'TOKEN_HYPOTHESIS':
            state.token_hypotheses.append(TokenHypothesis(rid, token.span, tuple(output['variants']), prov))
    n = len(state.evidence)
    if n:
        state.clause_candidates.append(ClauseCandidate('syntax:unsegmented', ((0, n - 1),), ResourceProvenance(('UNSEGMENTED_INPUT',), {'release': release.sha256})))
        for boundary in state.boundary_candidates:
            i = boundary.position
            if 0 < i < n:
                state.clause_candidates.append(ClauseCandidate('syntax:clause:' + boundary.candidate_id, ((0, i - 1), (i, n - 1)), boundary.provenance))


def propose_graphs(state, release, request):
    from dataclasses import asdict
    found = enumerate_matches(state, release.entries('SyntaxRules'), 'T2', release.entries('ProposalPolicy')[0], release)
    hypotheses = []
    provenance = {}
    morph_bindings = {}
    for match in found:
        output = match.rule['output']
        names = {n['id']: i for i, n in enumerate(output['nodes'])}
        anchors = lambda node: tuple(state.evidence[match.assignment[c][0]].token_id for c in node['anchors'])
        nodes = tuple(TNode(n['kind'], anchors(n)) for n in output['nodes'])
        edges = tuple(TEdge(e['kind'], names[e['from']], names[e['to']], e.get('role_id'), e.get('scope', False)) for e in output['edges'])
        lo, hi = match.window
        binding = {state.evidence[i].token_id: _plain_variant(v) for i,v in match.assignment.values()}
        alignment=tuple(t.token_id for t in state.evidence[lo:hi])
        hid='syntax:graph:'+digest([[asdict(n) for n in nodes],[asdict(e) for e in edges],alignment,binding])
        h = Hypothesis(hid, nodes, edges, alignment=alignment)
        local_required = tuple((operator, spans) for operator, spans in request.required_operators if set(spans) & set(h.alignment))
        _validate_hypothesis(replace(request, required_operators=local_required), h)
        if hid not in provenance:
            hypotheses.append(h)
            morph_bindings[hid] = binding
        rules=set(provenance[hid].pattern_ids) if hid in provenance else set()
        rules.add(match.rule['rule_id'])
        provenance[hid] = ResourceProvenance(tuple(sorted(rules)), {'SyntaxRules': release.version('SyntaxRules'), 'release': release.sha256})
    return hypotheses, provenance, morph_bindings
