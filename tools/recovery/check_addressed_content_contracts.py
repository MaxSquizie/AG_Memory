"""Focused selection contracts; controlled replies, not model evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from pytest import MonkeyPatch
from test_structural_relation_tasks import run, relation, bounds
from ah.formalizer.pipeline import t0
from ah.formalizer.relation_composition import content_role
from ah.formalizer.selection_labels import PROTOCOL_VERSION


# Rejected endpoints constrain only their addressed start. A remaining start
# remains selectable and the resulting negation can still be written.
with TemporaryDirectory() as tmp, MonkeyPatch.context() as patch:
    result, script = run(Path(tmp), patch, 'Иван не пришёл.', relation('NOT') + [
        ('structural_introducer_start', 'Start at «Иван»'),
        ('structural_introducer_end', '0'),
    ] + bounds('structural_introducer', 'не', 'не') + [
        ('structural_partition', 'PARTITION'),
    ] + relation('LEXICAL'))
assert result['assertions']['ah'] == [
    {'operator': 'NOT', 'operands': [{'predicate': 'ARRIVE', 'roles': {'AGENT': {'entity': 'ivan'}}}]}]
starts = [p for slot, p in script.calls if slot == 'structural_introducer_start']
assert '«Иван» @0' in starts[-1] and 'endpoint' in starts[-1] and '[0]' not in starts[-1]
assert 'Start at «не»' in starts[-1]
markers = [p for slot, p in script.calls if slot == 'relation_marker_role']
assert markers and all('already names what this relation applies to' not in p for p in markers)

# A fully rejected owner selection is an implemented unresolved outcome.
with TemporaryDirectory() as tmp, MonkeyPatch.context() as patch:
    result, _ = run(Path(tmp), patch, 'Иван сказал это.', relation('CONTENT_REFERENCE') + [
        ('content_reference_presence', 'Some target words explicitly'),
    ] + bounds('content_pointer', 'это', 'это') + [('structural_owner', '0')])
assert not result['assertions']['ah']
assert 'STRUCTURAL_SELECTION_UNRESOLVED' in result['diagnostics']['codes']
assert 'STRUCTURAL_IMPLEMENTATION_GAP' not in result['diagnostics']['codes']

# The role producer excludes only explicitly assigned slots. Even a sole
# remaining slot needs selection; no remaining slot means no provider call.
state = t0('сказал содержание')
owner, body = state.evidence
region = SimpleNamespace(region_id='addressed-role', source_range=(0, len(state.text)),
    token_refs=tuple(t.token_id for t in state.evidence), grounds=())
entries = {'RoleRegistry': [{'role_id': r, 'allowed_argument_kinds': ['PROPOSITION']}
                           for r in ('OBJECT', 'TOPIC')], 'R-S': [], 'AttitudeMap': [], 'ProposalPolicy': [{}]}
release = SimpleNamespace(sha256='addressed-contract', entries=lambda kind: entries[kind])
cfg = {'context_chars': 1000, 'max_candidates': 20}
seen = []
selector = SimpleNamespace(selection_reply_format=PROTOCOL_VERSION,
    select=lambda prompt: seen.append(str(prompt)) or '1')
parts = {'content_refs': [body.token_id], 'parent_refs': [owner.token_id]}
selected = content_role(state, release, selector, region, cfg, owner, [owner], body.span, parts,
    reserved_roles={'OBJECT'})
assert selected[0]['role'] == 'TOPIC' and selected[0]['reserved_roles'] == ['OBJECT']
role_pages = [r for r in state.syntax_trace if r.get('kind') == 'STRUCTURAL_TASK'
              and r.get('slot') == 'structural_content_role' and r.get('alternatives')]
assert {v['role'] for r in role_pages for v in r['alternatives']} == {'TOPIC'}
assert 'TOPIC of «сказал»' in seen[-1] and 'OBJECT of «сказал»' not in seen[-1]
count = len(seen)
assert content_role(state, release, selector, region, cfg, owner, [owner], body.span, parts,
    reserved_roles={'OBJECT', 'TOPIC'}) is None
assert len(seen) == count
assert state.syntax_trace[-1]['status'] == 'EXHAUSTED' and state.syntax_trace[-1]['enumeration_complete']
selected = content_role(state, release, selector, region, cfg, owner, [owner], body.span, parts)
assert selected[0]['role'] == 'OBJECT'
selector.select = lambda prompt: '?'
assert content_role(state, release, selector, region, cfg, owner, [owner], body.span,
    {**parts, 'attempt': 'unknown'}, reserved_roles={'OBJECT'}) is None
# A selected single-predication route plus an addressed content owner entails
# the head. Without both premises, head selection remains a model task.
from ah.formalizer.structural_tasks import choose
from ah.formalizer.composition_contracts import LexicalRoute
from ah.formalizer.composition_tree import InputSlot
from ah.formalizer.predicate_functions import head
state = t0('он сказал')
subject, owner = state.evidence
region = SimpleNamespace(region_id='owner-head', source_range=(0, len(state.text)),
    token_refs=tuple(t.token_id for t in state.evidence), grounds=())
seen = []
selector.select = lambda prompt: seen.append(str(prompt)) or '1'
value, proof = choose(state, release, selector, region, cfg, 'structural_relation', [{
    'candidate_id': 'LEXICAL', 'label': 'One lexical predication', 'relation': 'LEXICAL',
    'region_ref': region.region_id, 'token_refs': list(region.token_refs),
    'source_uid': state.source_uid, 'input_scope': None}], 'Select the relation.')
route = LexicalRoute(region.region_id, region.token_refs, proof, state.interpretation_version)
request = InputSlot(pending_propositions={owner.token_id: frozenset({'OBJECT'})})
count = len(seen)
selected, basis = head(state, release, selector, region, state.evidence, [subject],
    {**cfg, '_lexical_route': route}, request=request)
assert selected.token_id == owner.token_id and basis['kind'] == 'CONTENT_OWNER_HEAD'
assert len(seen) == count and state.syntax_trace[-1]['kind'] == 'PREDICATE_HEAD_DERIVED'
assert head(state, release, selector, region, state.evidence, [], {**cfg, '_lexical_route': route},
    request=InputSlot(pending_propositions={t.token_id: {'OBJECT'} for t in state.evidence})) is None
assert len(seen) == count and state.syntax_trace[-1]['category'] == 'HYPOTHESIS_CONFLICT'
head(state, release, selector, region, state.evidence, [], cfg, request=request)
assert len(seen) == count + 1  # no established lexical route: no deduction
print('PASS: addressed boundaries, marker function, rejected owner, reserved content roles, abstention and owner-derived head')
