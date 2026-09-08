"""Run parse(), including all graph rewrite passes and actual actant extraction.

Only bounded model answers are fixtures. No parser/recovery/extraction method is
patched. Expected predicate/role frames are specified independently below.
"""
from pathlib import Path

import pytest

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import Pymorphy3Morphology

ROOT = Path(__file__).resolve().parents[1]


class SemanticFixture:
    """Explicit answers for these texts; unexpected semantic tasks fail the test."""
    subjects = {'Иван', 'Мария', 'Пётр', 'Ольга', 'Анна', 'Сергей', 'Слава', 'тетрадь', 'Книга'}
    objects = {'книгу', 'журнал', 'газету', 'отчёт', 'письмо', 'дверь', 'окно', 'ворота',
               'хлеб', 'молоко', 'чай', 'кофе', 'калитку'}
    places = {'в Москве', 'в Казани', 'в Париже', 'дома', 'в офисе', 'в школе',
              'на столе', 'на полке', 'в ящике', 'на стол', 'на полку', 'в ящик'}

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, system='', override=None, role='generic'):
        self.calls.append((role, prompt))
        if role == 'perception_role_cue':
            target = prompt.split('TARGET:\n', 1)[1].split('\n', 1)[0]
            predicate = prompt.split('PREDICATE:\n', 1)[1].split('\n', 1)[0]
            answer = ('ACTOR_OR_EXPERIENCER' if target in self.subjects or (predicate == 'лежит' and target == 'журнал')
                      else 'AFFECTED_OR_CONTENT' if target in self.objects
                      else 'PLACE' if target in self.places else None)
            if answer is not None:
                assert answer in prompt.split('CHOICES:\n')[1].split('\n\nTASK:')[0].splitlines()
                return LLMResponse(answer, {})
        if role == 'perception_lexeme_comparison' and 'TARGET:\nполку\n' in prompt:
            for label in ('A', 'B'):
                if f'{label} LEMMA:\nполка\n' in prompt:
                    return LLMResponse(label, {})
        if role == 'perception_modifier_attachment':
            modifier = prompt.split('MODIFIER:\n', 1)[1].split('\n', 1)[0]
            if modifier in self.places:
                return LLMResponse('EVENT', {})
        raise AssertionError(f'Unspecified bounded fixture: {role}\n{prompt[:600]}')


@pytest.fixture(scope='module')
def morph():
    return Pymorphy3Morphology()


def make_parser(morph, backend=None):
    return AdaptivePerceptionParser(backend or SemanticFixture(), AdaptiveSettings(
        prompt_dir=ROOT/'prompts/perception',
        generation=LLMRoleSettings(max_new_tokens=24, temperature=0),
        retry_attempts=0, morphology_backend='none'), morphology=morph)


def frame(predicate, subject, obj=None, location=None):
    roles = {'SUBJECT': subject}
    if obj is not None:
        roles['OBJECT'] = obj
    if location is not None:
        roles['LOCATION'] = location
    return predicate, roles


CASES = [
 ('Иван прочитал книгу, а Мария — журнал.', [frame('прочитать','Иван','книга'), frame('прочитать','Мария','журнал')]),
 ('Иван купил книгу, Мария — журнал, Пётр — газету.', [frame('купить','Иван','книга'),frame('купить','Мария','журнал'),frame('купить','Пётр','газета')]),
 ('Анна прочитала книгу, Ольга — журнал, Мария — отчёт, а Пётр — письмо.', [frame('прочитать','Анна','книга'),frame('прочитать','Ольга','журнал'),frame('прочитать','Мария','отчёт'),frame('прочитать','Пётр','письмо')]),
 ('Пётр открыл дверь, Иван — окно, Сергей — ворота.', [frame('открыть','Пётр','дверь'),frame('открыть','Иван','окно'),frame('открыть','Сергей','ворота')]),
 ('Иван работает в Москве, а Мария — в Казани.', [frame('работать','Иван',location='Москва'),frame('работать','Мария',location='Казань')]),
 ('Иван работает дома, Мария — в офисе, Пётр — в школе.', [frame('работать','Иван',location='дом'),frame('работать','Мария',location='офис'),frame('работать','Пётр',location='школа')]),
 ('Книга лежит на столе, а журнал — на полке.', [frame('лежать','книга',location='стол'),frame('лежать','журнал',location='полка')]),
 ('Иван купил книгу, Мария — журнал, а Пётр прочитал газету.', [frame('купить','Иван','книга'),frame('купить','Мария','журнал'),frame('прочитать','Пётр','газета')]),
 ('Иван купил книгу, а Мария прочитала журнал, Пётр — газету.', [frame('купить','Иван','книга'),frame('прочитать','Мария','журнал'),frame('прочитать','Пётр','газета')]),
 ('Иван живёт в Москве, Мария — в Казани, Пётр — в Париже, а Слава — бродяга.', [frame('жить','Иван',location='Москва'),frame('жить','Мария',location='Казань'),frame('жить','Пётр',location='Париж'),frame('бродяга','Слава')]),
 ('Ольга положила книгу на стол, Анна — журнал на полку, Мария — письмо в ящик.', [frame('положить','Ольга','книга','стол'),frame('положить','Анна','журнал','полка'),frame('положить','Мария','письмо','ящик')]),
]


def normalized_frames(perception):
    return sorted((a.predicate.lookup_form.casefold(), tuple(sorted(
        (x.role.value, (x.lookup_text or '').casefold()) for x in a.actants)))
        for a in perception.assertions)


@pytest.mark.parametrize('text,expected', CASES)
@pytest.mark.parametrize('dash', ['—', '–', '-'])
def test_full_parse_preserves_ellipsis_after_nominal_rewrite(morph, text, expected, dash):
    p = make_parser(morph)
    result = p.parse(text.replace('—', dash))
    wanted = sorted((pred, tuple(sorted((role, value.casefold()) for role,value in roles.items())))
                    for pred,roles in expected)
    assert normalized_frames(result.perception) == wanted
    assert len({a.local_id for a in result.perception.assertions}) == len(expected)
    assert any(t.stage == 'ellipsis_recovery' for t in result.traces)
    assert any(t.stage == 'predicate_ownership' and t.normalized_answer == 'ELLIPSIS:preserved'
               for t in result.traces)


@pytest.mark.parametrize('text,predicate,subject', [
    ('Слава — бродяга.', 'бродяга', 'слава'),
    ('Мария — врач.', 'врач', 'мария'),
    ('Пётр — инженер.', 'инженер', 'пётр'),
])
def test_full_parse_keeps_true_nominal_predication(morph, text, predicate, subject):
    result = make_parser(morph).parse(text)
    assert normalized_frames(result.perception) == [(predicate, (('SUBJECT', subject),))]


@pytest.mark.parametrize('text,polarity,subjects', [
    ('Иван купил книгу, Мария — журнал, а Пётр — нет.', [False,False,True], ['Иван','Мария','Пётр']),
    ('Иван купил книгу, а Мария — нет, Пётр — тоже нет.', [False,True,True], ['Иван','Мария','Пётр']),
    ('Иван купил книгу, а Мария тоже, Пётр — нет.', [False,False,True], ['Иван','Мария','Пётр']),
    ('Иван купил книгу, Мария — журнал, Пётр — тоже.', [False,False,False], ['Иван','Мария','Пётр']),
])
@pytest.mark.parametrize('dash', ['—','–','-'])
def test_full_parse_polarity_chain(morph, text, polarity, subjects, dash):
    result = make_parser(morph).parse(text.replace('—',dash))
    assertions = result.perception.assertions
    assert len(assertions) == len(subjects)
    assert [a.negated for a in assertions] == polarity
    assert all(a.predicate.lookup_form == 'купить' for a in assertions)
    for a, subject in zip(assertions,subjects):
        assert next(x.lookup_text for x in a.actants if x.role.value == 'SUBJECT') == subject
    # The last peer inherits the immediate source object's identity.
    assert next(x.lookup_text for x in assertions[-1].actants if x.role.value=='OBJECT') == next(
        x.lookup_text for x in assertions[-2].actants if x.role.value=='OBJECT')


def test_bare_existential_negation_is_not_peer_recovery(morph):
    from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
    graph=LinguisticCandidateBuilder(morph).build('Иван купил книгу, денег нет.')
    assert all(c.ellipsis_kind is None for c in graph.clauses)
    assert any('нет' in p.lemma_candidates for p in graph.predicates)


def production_perception():
    from ah.perception import LLMPerceptionService, LLMPerceptionSettings
    return LLMPerceptionService(SemanticFixture(), LLMPerceptionSettings(
        protocol='adaptive_v3', probe_prompt_dir=ROOT/'prompts/perception',
        probe_retry_attempts=0, morphology_backend='pymorphy3'))


@pytest.mark.parametrize('text,expected', CASES)
def test_text_to_template_completion_to_canonical_ah(text, expected):
    from ah.integration.template_completion import TemplateCompletionService
    from test_ellipsis_canonical_02513 import runtime
    core, context, integration = runtime()
    perception = production_perception()
    parsed = perception.parse(text, context)
    completed = TemplateCompletionService(integration, perception).complete(parsed)
    commit = integration.integrate_external(completed, context)
    actual = []
    for item in commit.assertions:
        node = core.store.get_hypernode(item.ref.uid)
        template = core.store.get_template(node.template.uid)
        symbol = core.store.get_symbol(template.predicate.uid)
        roles = tuple(sorted((role.value, core.store.get_element_any_domain(ref.uid)
                              .properties['name'].value.casefold()) for role, ref in node.actants.items()))
        actual.append((symbol, roles))
    assert len(actual) == len(expected)
    for predicate, expected_roles in expected:
        roles = tuple(sorted((key,value.casefold()) for key,value in expected_roles.items()))
        assert any(predicate in symbol.forms and values == roles for symbol, values in actual)


def test_full_conditional_ellipsis_requires_actual_premise_before_proof():
    from ah.config import InferenceSettings
    from ah.inference import FormulaGoal, InferenceEngine, LogicalStatus
    from ah.integration.template_completion import TemplateCompletionService
    from test_ellipsis_canonical_02513 import runtime
    core, context, integration = runtime()
    perception = production_perception()
    completion = TemplateCompletionService(integration, perception)
    conditional = completion.complete(perception.parse(
        'Если Иван купил книгу, а Мария — журнал.', context))
    commit = integration.integrate_external(conditional, context)
    assert not commit.assertions
    assert len(commit.conditionals) == 1
    consequent = commit.conditionals[0].consequent
    engine = InferenceEngine(core, InferenceSettings())
    assert engine.solve(FormulaGoal(consequent)).status is not LogicalStatus.PROVED
    premise = completion.complete(perception.parse('Иван купил книгу.', context))
    integration.integrate_external(premise, context)
    outcome = engine.solve(FormulaGoal(consequent))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support, 'the recovered consequence needs formal proof support'


def test_explicit_copula_after_verbal_frame_remains_nominal(morph):
    result = make_parser(morph).parse('Иван работает в Москве, а Слава — это бродяга.')
    assert normalized_frames(result.perception) == [
        ('бродяга', (('SUBJECT','слава'),)),
        ('работать', (('LOCATION','москва'),('SUBJECT','иван'))),
    ]
