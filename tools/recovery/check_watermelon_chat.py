"""Exercise the GUI chat entry with the TEST_ONLY composition release and real morphology.

Run from the repository root: PYTHONPATH=src:. python -m tools.recovery.check_watermelon_chat
Only the external language-model transport is scripted.
"""
from collections import Counter
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.formalizer.diagnostic_graph import capture
from tools.prepare_formalizer_v7_gui import prepare


TEXT = 'на столе стоит арбуз'
ROOT = Path(__file__).resolve().parents[2]
# Match the language sent to the selector so that menu reordering cannot
# accidentally select a different host, subject or lemma.
CHOICES = {
    'structural_relation': 'One lexical predication',
    'nominal_coordination_discovery': '0',
    'nominal_function': ['An adposition', '0'],
    'nominal_function_source_start': 'Start at «на»',
    'nominal_function_source_end': ['End after «столе»', 'End after «на»'],
    'nominal_function_source_continue': '0',
    'nominal_function_head': ['0', 'Nominal head «столе»'],
    'structural_ownership_revision': 'Reconsider the source words',
    'temporal_function': '0',
    'predicate_function': 'Predicate occurrence «стоит»',
    'predicate_argument_role': 'core subject:',
    'predicate_argument_reading': 'cases: nominative;',
    'nominal_attachment': ['Whole phrase readings:', 'Predicate subtree «стоит арбуз»'],
    'modifier_scope': 'applies to «стоит арбуз»',
    'component_attachment': 'стоять [conjugated verb]',
    'spatial_function': 'No separate contextual place slot',
    'speech_act': 'The speaker asserts the WHOLE statement',
    'source_assertion': '?',
}


class Answers:
    def __init__(self, choices):
        self.choices = choices
        self.calls = Counter()
        self.errors = []

    def generate(self, prompt, **kwargs):
        slot = prompt.selection_audit['slot']
        index = self.calls[slot]
        self.calls[slot] += 1
        choice = self.choices.get(slot)
        if isinstance(choice, list):
            choice = choice[index] if index < len(choice) else None
        if choice in ('0', '?'):
            return choice
        options = re.findall(r'^(\d+)\. (.+)$', prompt, re.MULTILINE)
        hits = [number for number, label in options if choice and choice in label]
        if len(hits) != 1:
            self.errors.append((slot, choice, options))
            return '?'
        return hits[0]


def run_case(accept_revision):
    answers = Answers(CHOICES if accept_revision else {**CHOICES, 'structural_ownership_revision': '?'})
    with TemporaryDirectory() as tmp, patch('ah.bootstrap.build_llm_backend', return_value=answers):
        config = load_config(prepare(ROOT / 'config/lmstudio.toml', Path(tmp) / 'session', profile='composition'))
        runtime = RuntimeServices.build(config)
        turn = runtime.create_orchestrator().handle_user_text(TEXT, generate_response=False)
        receipt = turn.perception.native_receipt
        assert not answers.errors, answers.errors
        assert answers.calls['structural_ownership_revision'] == 1
        # Reload the seed snapshot and replay the real journal after the turn.
        restored = RuntimeServices.build(config).core._formalizer_adapter
        ledger = restored.ledger
        supported = {row['conclusion_ref'] for row in ledger.data['supports'].values()}
        if not accept_revision:
            assert receipt.terminal == 'RESOLUTION_ONLY'
            assert not receipt.committed_fragments and not supported and not ledger.data['nodes']
        else:
            assert answers.calls['component_attachment'] == 1
            assert answers.calls['nominal_function_head'] == 2
            assert receipt.applied and receipt.terminal == 'APPLIED' and not receipt.diagnostics
            root_ref, = receipt.node_refs
            assert len(receipt.committed_fragments) == 1 and supported == {root_ref}
            graph = capture(restored, [root_ref])
            root = graph['nodes'][root_ref]
            assert root['lexical_anchor'] == 'на' and root['source_ref'] == 'tok:0:2'
            assert graph['entities'][root['actants']['SURFACE_ARG']] == {'name': 'столе', 'mention_ref': 'tok:3:8'}
            event = graph['nodes'][root['actants']['OBJECT']]
            assert event['lexical_lemma'] == 'стоять' and event['source_ref'] == 'tok:9:14'
            assert graph['entities'][event['actants']['SUBJECT']] == {'name': 'арбуз', 'mention_ref': 'tok:15:20'}
            assert set(ledger.data['nodes']) == {root_ref, event['uid']}
        print(f'ownership revision {"accepted" if accept_revision else "unresolved"}: '
              f'{receipt.terminal}, {sum(answers.calls.values())} calls, supported roots={len(supported)}')


if __name__ == '__main__':
    run_case(False)
    run_case(True)
