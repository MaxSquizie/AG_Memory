"""Exercise the nominal producer with the real selection codec and controlled replies."""
import unittest
from types import SimpleNamespace

from ah.formalizer.nominal_functions import prepare, rows
from ah.formalizer.pipeline import t0
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import licensed_in_scope


class NominalSourceRevisionTest(unittest.TestCase):
    def run_case(self, text, function, initial_head_reply, *, revision_reply='1', replay=None,
                 repeat_material=False):
        state = t0(text)
        state.budget.llm_limit = 64
        if replay is not None:
            state.source_uid = replay.source_uid
            state.observation['clarification_generation'] = {
                'rebuild_components': True, 'component_probe_records': replay.component_probe_records}
        tokens = state.evidence
        region = TextRegion('test', 'SENTENCE', (0, len(text)),
                            tuple(t.token_id for t in tokens), None)
        slots = []
        head_domains = []
        errors = []

        def select(prompt):
            audit = prompt.selection_audit
            slot = audit['slot']
            ids = audit['candidates']
            slots.append(slot)
            if slot == 'nominal_function':
                if slots.count(slot) > 1:
                    return '0'
                candidate = function
            elif slot == 'nominal_function_source_start':
                candidate = 'start:' + tokens[0].token_id
            elif slot == 'nominal_function_source_end':
                revising = 'structural_ownership_revision' in slots
                last = tokens[0] if revising and not repeat_material else tokens[1]
                candidate = 'end:' + last.token_id
            elif slot == 'nominal_function_source_continue':
                return '0'
            elif slot == 'nominal_function_head':
                head_domains.append(tuple(ids))
                if 'structural_ownership_revision' not in slots:
                    return initial_head_reply if isinstance(initial_head_reply, str) else next(initial_head_reply)
                candidate = tokens[1].token_id
            elif slot == 'structural_ownership_revision':
                return revision_reply
            elif slot == 'nominal_external_case':
                candidate = 'nom'
            else:
                errors.append(('unexpected slot', slot))
                return '?'
            if candidate not in ids:
                return '0'  # The requested occurrence can be on the next page.
            return str(ids.index(candidate) + 1)

        selector = SimpleNamespace(selection_reply_format='SELECT_LABELS_V1', select=select)
        release = SimpleNamespace(sha256='test', entries=lambda _: [{'max_rule_steps': 100}])
        result = prepare(state, release, selector, region, tokens,
                         {'max_candidates': 8, 'context_chars': 4000})
        self.assertEqual(errors, [])
        return state, result, slots, head_domains

    def test_exhausted_heads_reopen_only_the_dependent_source(self):
        for text, function in [('на столе стоит арбуз', 'RELATION'),
                               ('два дома стоят рядом', 'QUANTITY')]:
            with self.subTest(function=function):
                state, complete, slots, domains = self.run_case(text, function, '0')
                self.assertTrue(complete)
                modifier, head = state.evidence[:2]
                if function == 'RELATION':
                    self.assertNotIn(head.token_id, domains[0])
                self.assertIn(head.token_id, domains[-1])
                self.assertEqual(slots.count('nominal_function'), 2)
                row, = rows(state, state.evidence)
                self.assertEqual((row['function'], row['function_refs'], row['head_ref']),
                                 (function, [modifier.token_id], head.token_id))

    def test_retiring_the_exhausted_head_page_invalidates_repaired_choice(self):
        state, complete, _, _ = self.run_case('на столе стоит арбуз', 'RELATION', '0')
        self.assertTrue(complete)
        row, = rows(state, state.evidence)
        rejected_page = next(event['decision_ref'] for event in state.syntax_trace
                             if event.get('slot') == 'nominal_function_head'
                             and event.get('status') == 'REJECTED_PAGE')
        self.assertTrue(licensed_in_scope(state, row['head_proof']))
        state.syntax_trace.append({'kind': 'DEPENDENCY_REJECTED', 'decision_ref': rejected_page})
        self.assertFalse(licensed_in_scope(state, row['head_proof']))
        self.assertEqual(rows(state, state.evidence), [])

    def test_frozen_replay_rebuilds_the_same_revision_without_new_calls(self):
        text = 'на столе стоит арбуз'
        first, complete, _, _ = self.run_case(text, 'RELATION', '0')
        self.assertTrue(complete)
        repeated, complete, slots, _ = self.run_case(text, 'RELATION', '0', replay=first)
        self.assertTrue(complete)
        self.assertEqual(slots, [])
        self.assertEqual(rows(first, first.evidence), rows(repeated, repeated.evidence))

    def test_unknown_and_multiple_heads_leave_the_boundary_open(self):
        for reply in ['?', '1,2']:
            with self.subTest(reply=reply):
                state, complete, slots, _ = self.run_case('на столе стоит арбуз', 'RELATION', reply)
                self.assertFalse(complete)
                self.assertNotIn('structural_ownership_revision', slots)
                self.assertEqual(rows(state, state.evidence), [])

    def test_revision_requires_a_supported_choice(self):
        for reply in ['?', '0']:
            with self.subTest(reply=reply):
                state, complete, slots, _ = self.run_case(
                    'на столе стоит арбуз', 'RELATION', '0', revision_reply=reply)
                self.assertFalse(complete)
                self.assertIn('structural_ownership_revision', slots)
                self.assertEqual(slots.count('nominal_function_source_start'), 1)
                self.assertEqual(rows(state, state.evidence), [])

    def test_repeated_material_stops_before_asking_the_same_head_question(self):
        state, complete, slots, _ = self.run_case(
            'на столе стоит арбуз', 'RELATION', '0', repeat_material=True)
        self.assertFalse(complete)
        self.assertEqual(slots.count('nominal_function_head'), 1)
        self.assertEqual(slots.count('structural_ownership_revision'), 1)
        self.assertIn('STRUCTURAL_REVISION_NO_PROGRESS', [d.code for d in state.diagnostics])
        self.assertEqual(rows(state, state.evidence), [])

    def test_unknown_on_later_head_page_preserves_the_current_source(self):
        state, complete, slots, domains = self.run_case(
            'на столе лежат красный карандаш старый блокнот тетрадь и несколько больших конвертов',
            'RELATION', iter(('0', '?')))
        self.assertFalse(complete)
        self.assertEqual(len(domains), 2)
        self.assertTrue(set(domains[0]).isdisjoint(domains[1]))
        self.assertNotIn('structural_ownership_revision', slots)
        self.assertEqual(rows(state, state.evidence), [])
