"""Structural invariants across vocabulary, roles, order and ambiguous readings."""
from dataclasses import replace
import pytest

from ah.integration.formalization import SemanticConsolidator
from ah.integration.errors import UnresolvedDiscourseReferenceError
from ah.integration.template_completion import TemplateCompletionService
from ah.model import ActantRole, Domain, Property
from ah.perception import (ActantCandidate, AssertionCandidate, EvidenceSpan,
    NominalRelationCandidate, NominalRelationKind, PerceptionResult,
    PredicateCandidate, TemplateCandidate, LLMPerceptionService, LLMPerceptionSettings)
from ah.llm.process_backend import LLMResponse
from test_ellipsis_canonical_02513 import runtime
from test_full_ellipsis_pipeline_02514 import SemanticFixture, ROOT, make_parser
from ah.perception.morphology import Pymorphy3Morphology
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder


def nominal(head, pronoun, kind=NominalRelationKind.POSSESSOR):
    return ActantCandidate(ActantRole.SUBJECT, mention=f'{head} {pronoun}', normalized_hint=head,
        nominal_relations=(NominalRelationCandidate(kind, head_mention=head,
            head_normalized_hint=head, dependent_mention=pronoun),))


def assertion(actant, local_id='A1'):
    return AssertionCandidate(local_id, PredicateCandidate('существует', 'существовать',
        template_candidate=TemplateCandidate((ActantRole.SUBJECT,))), (actant,))


@pytest.mark.parametrize('head,gender', [('дверь','femn'), ('дом','masc'), ('торжество','neut')])
@pytest.mark.parametrize('pronoun', ['его', 'её', 'их'])
def test_head_grammar_is_independent_of_dependent_pronoun(head, gender, pronoun):
    consolidator = SemanticConsolidator()
    candidate = nominal(head, pronoun)
    assert consolidator._third_person_signature(candidate) is None
    assert consolidator._referent_signature(candidate) == ('sing', gender)


@pytest.mark.parametrize('head', ['дверь', 'дом', 'торжество'])
@pytest.mark.parametrize('pronoun,anchor', [('его','он'), ('её','она'), ('их','они')])
def test_known_possessor_is_resolved_separately_from_head(head, pronoun, anchor):
    core, context, integration = runtime()
    owner = core.add_entity(Domain.C, {'name': Property('name','Владелец','str')})
    context.pronoun_refs[anchor] = core.ref(owner.uid)
    result = PerceptionResult(f'{head} {pronoun}', assertions=(assertion(nominal(head,pronoun)),))
    commit = integration.integrate_external(result, context)
    main = core.store.get_hypernode(commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    assert main.uid != owner.uid
    assert core.store.get_element_any_domain(main.uid).properties['name'].value == head
    assert core.store.find_link('POSSESSOR', main.uid, owner.uid) is not None


@pytest.mark.parametrize('kind', list(NominalRelationKind))
@pytest.mark.parametrize('head,pronoun', [('дверь','его'), ('дом','её'), ('торжество','их')])
def test_unresolved_dependent_blocks_entire_commit_without_confusing_head(kind, head, pronoun):
    core, context, integration = runtime()
    result = PerceptionResult(f'{head} {pronoun}', assertions=(assertion(nominal(head,pronoun,kind)),))
    before = set(core.store.all_uids())
    plan = integration.prepare_external_plan(result, context)
    assert len(plan.candidate_ir.discourse_refs) == 1
    pending = plan.candidate_ir.discourse_refs[0]
    assert pending.mention == pronoun
    assert pending.nominal_relation_index == 0
    with pytest.raises(UnresolvedDiscourseReferenceError):
        integration.integrate_plan(plan, context)
    assert set(core.store.all_uids()) == before


def test_binding_dependent_reuses_local_owner_without_rebinding_nominal_head():
    core, context, integration = runtime()
    owner = ActantCandidate(ActantRole.SUBJECT, mention='Анна', normalized_hint='Анна', entity_ref='E1')
    parent = nominal('дом', 'её')
    result = PerceptionResult('Анна существует. Дом её существует.',
        assertions=(assertion(owner,'A0'), assertion(parent)))
    plan = integration.prepare_external_plan(result, context)
    pending = plan.candidate_ir.discourse_refs[0]
    assert pending.candidate_entity_refs == ('E1',)
    bound = integration.bind_discourse_ref(plan, pending.local_id, 'E1', context=context)
    assert bound.candidate_ir.discourse_refs == ()
    dependent = bound.perception.assertions[1].actants[0]
    assert dependent.entity_ref is None
    assert dependent.nominal_relations[0].dependent_entity_ref == 'E1'
    commit = integration.integrate_plan(bound, context)
    owner_ref = core.store.get_hypernode(commit.assertions[0].ref.uid).actants[ActantRole.SUBJECT]
    head_ref = core.store.get_hypernode(commit.assertions[1].ref.uid).actants[ActantRole.SUBJECT]
    assert owner_ref != head_ref
    assert core.store.find_link('POSSESSOR', head_ref.uid, owner_ref.uid) is not None


class FrameFixture(SemanticFixture):
    subjects = SemanticFixture.subjects | {'Мастер', 'ученик', 'Рабочий', 'плотник', 'тетрадь', 'Тетрадь'}
    objects = SemanticFixture.objects | {'стол', 'стул', 'ящик', 'шкаф'}

    def generate(self, prompt, *, system='', override=None, role='generic'):
        # Deliberately adversarial target-PP answer: a licensed, unique parallel
        # slot must have been consumed before an attachment vote can overwrite it.
        if role == 'perception_modifier_attachment':
            modifier = prompt.split('MODIFIER:\n')[1].split('\n')[0]
            self.calls.append((role,prompt))
            return LLMResponse('NOMINAL_1' if modifier in {'на полке','из металла'} else 'EVENT', {})
        if role == 'perception_role_cue':
            target = prompt.split('TARGET:\n')[1].split('\n')[0]
            if target in {'из дерева','из металла'}:
                self.calls.append((role,prompt))
                return LLMResponse('CONSTITUENT_MATERIAL', {})
        return super().generate(prompt, system=system, override=override, role=role)


@pytest.mark.parametrize('dash', ['—', '–', '-'])
@pytest.mark.parametrize('text,expected_role,expected', [
    ('Книга лежит на столе, а журнал — на полке.', ActantRole.LOCATION, 'полка'),
    ('Тетрадь лежит на столе, а журнал — на полке.', ActantRole.LOCATION, 'полка'),
    ('Мастер сделал стол из дерева, а ученик — стул из металла.', ActantRole.MATERIAL, 'металл'),
    ('Рабочий сделал ящик из дерева, а плотник — шкаф из металла.', ActantRole.MATERIAL, 'металл'),
])
def test_parallel_event_slot_survives_adversarial_nominal_attachment(text, expected_role, expected, dash):
    core, context, integration = runtime()
    backend = FrameFixture()
    service = LLMPerceptionService(backend, LLMPerceptionSettings(protocol='adaptive_v3',
        probe_prompt_dir=ROOT/'prompts/perception', probe_retry_attempts=0, morphology_backend='pymorphy3'))
    parsed = service.parse(text.replace('—',dash), context)
    assert len(parsed.assertions) == 2
    assert next(a.lookup_text for a in parsed.assertions[1].actants if a.role is expected_role).casefold() == expected
    target_modifier = 'на полке' if expected_role is ActantRole.LOCATION else 'из металла'
    assert not any(role == 'perception_modifier_attachment' and f'MODIFIER:\n{target_modifier}\n' in prompt
                   for role,prompt in backend.calls)
    commit = integration.integrate_external(TemplateCompletionService(integration,service).complete(parsed), context)
    assert len(commit.assertions) == 2
    node = core.store.get_hypernode(commit.assertions[1].ref.uid)
    assert core.store.get_element_any_domain(node.actants[expected_role].uid).properties['name'].value.casefold() == expected


from itertools import permutations
from ah.perception.morphology import MorphInfo
from test_semantic_reliability_v082 import Morphology


@pytest.mark.parametrize('roles', list(permutations([ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT])))
@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_parallel_matching_is_invariant_to_lexical_renaming_role_labels_and_order(roles, order):
    # Invented symbols receive morphology only in this fixture. Production cannot
    # know their spelling, nor can case alone imply any of these permuted roles.
    names = [f'lexeme{len(roles)}_{i}' for i in range(6)]
    cases = ['nomn', 'accs', 'datv']
    morph = Morphology({name: (MorphInfo(name, 'NOUN', case=cases[i % 3], score=1.0),)
                        for i,name in enumerate(names)})
    parser = make_parser(morph)
    text = ' '.join(names)
    tokens = parser._source_tokens(text)
    spans = [EvidenceSpan(t.text,t.start,t.end) for t in tokens]
    source = [ActantCandidate(role,mention=names[i],evidence=spans[i]) for i,role in enumerate(roles)]
    targets = [spans[3+i] for i in order]
    matched = parser._unique_realization_roles(source,targets,tokens)
    assert matched == {j: roles[i] for j,i in enumerate(order)}


@pytest.mark.parametrize('target_cases', [('nomn','nomn'), ('datv','datv'), (None,None)])
def test_colliding_or_absent_grammatical_evidence_never_selects_first_target(target_cases):
    names = ['source', 'targeta', 'targetb']
    morph = Morphology({name: (MorphInfo(name,'NOUN',case=case,score=1.0),)
        for name,case in zip(names,[target_cases[0],*target_cases])})
    parser = make_parser(morph)
    text = ' '.join(names)
    tokens = parser._source_tokens(text)
    spans = [EvidenceSpan(t.text,t.start,t.end) for t in tokens]
    source = [ActantCandidate(ActantRole.RECIPIENT,mention=names[0],evidence=spans[0])]
    assert parser._unique_realization_roles(source,spans[1:],tokens) == {}
    assert parser._unique_realization_roles(source,list(reversed(spans[1:])),tokens) == {}


@pytest.mark.parametrize('text', ['Письмо в городе обсуждали.', 'Посылку в порту осматривали.', 'Книгу в школе читали.'])
@pytest.mark.parametrize('answer', ['EVENT','NOMINAL_1','UNCLEAR'])
def test_preverbal_locative_does_not_entail_event_location(text, answer):
    from ah.perception.adaptive_parser import AdaptiveStructuralClarificationRequired
    from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
    class Backend:
        def __init__(self): self.calls=[]
        def generate(self, prompt, *, system='', override=None, role='generic'):
            self.calls.append((role,prompt))
            assert role == 'perception_modifier_attachment'
            return LLMResponse(answer,{})
    backend = Backend()
    morph = Pymorphy3Morphology()
    parser = make_parser(morph,backend)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    predicate = parser._resolve_span(text,tokens,4,4)
    modifier = parser._resolve_span(text,tokens,2,3)
    def resolve():
        return parser._resolve_modifier_attachment(text,tokens,predicate,PredicateCandidate(predicate.text),modifier)
    if answer == 'UNCLEAR':
        with pytest.raises(AdaptiveStructuralClarificationRequired): resolve()
    else:
        assert resolve().kind.value == ('PREDICATE' if answer=='EVENT' else 'NOMINAL')
    assert len(backend.calls) == 1


def test_incompatible_local_owner_cannot_be_bound_when_candidate_set_is_empty():
    core, context, integration = runtime()
    owner = ActantCandidate(ActantRole.SUBJECT,mention='Анна',entity_ref='E1')
    result = PerceptionResult('Анна существует. Дом их существует.',
        assertions=(assertion(owner,'A0'),assertion(nominal('дом','их'))))
    plan = integration.prepare_external_plan(result,context)
    pending = plan.candidate_ir.discourse_refs[0]
    assert pending.candidate_entity_refs == ()
    before = set(core.store.all_uids())
    with pytest.raises(ValueError,match='grammatical constraints'):
        integration.bind_discourse_ref(plan,pending.local_id,'E1',context=context)
    assert set(core.store.all_uids()) == before


def test_clarification_labels_hide_morphosyntactic_identity_guards():
    core, _context, integration = runtime()
    entity = core.add_entity(
        Domain.C,
        {
            'name': Property('name', 'Астра', 'str'),
            'grammatical_number': Property('grammatical_number', 'sing', 'str'),
            'semantic_kind': Property('semantic_kind', 'device', 'str'),
        },
    )
    assert integration._clarification_member_label(core.ref(entity.uid)) == (
        'Астра (semantic_kind=device)'
    )


@pytest.mark.parametrize('surface', ['днём', 'ночью'])
def test_time_value_identity_preserves_the_complete_source_expression(surface):
    morph = Pymorphy3Morphology()
    text = f'Система активна {surface}.'
    parser = make_parser(morph)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    token = next(item for item in tokens if item.text == surface)
    span = parser._resolve_span(text, tokens, token.index, token.index)
    actant = parser._make_actant(ActantRole.TIME, span)
    assert actant.mention == surface
    assert actant.lookup_text == surface
    assert actant.nominal_relations == ()


class GenitiveBoundaryBackend:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def generate(self, prompt, *, system='', override=None, role='generic'):
        self.calls.append((role, prompt))
        assert role == 'perception_nominal_genitive_attachment'
        return LLMResponse(self.answer, {})


@pytest.mark.parametrize('text,head,phrase', [
    ('Оператор работал в ангаре два месяца.', 'ангаре', 'два месяца'),
    ('Датчик находился в отсеке три недели.', 'отсеке', 'три недели'),
])
def test_posthead_quantified_phrase_gets_a_real_np_boundary_decision(text, head, phrase):
    morph = Pymorphy3Morphology()
    backend = GenitiveBoundaryBackend('SEPARATE')
    parser = make_parser(morph, backend)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    head_token = next(item for item in tokens if item.text == head)
    end = parser._nominal_phrase_end(tokens, head_token.index, len(tokens) - 1, set())
    assert end == head_token.index
    assert len(backend.calls) == 1
    assert f'FOLLOWING PHRASE:\n{phrase}\n' in backend.calls[0][1]


@pytest.mark.parametrize('text,head,phrase', [
    ('Команда двух специалистов собралась.', 'Команда', 'двух специалистов'),
    ('Группа трёх инженеров прибыла.', 'Группа', 'трёх инженеров'),
])
def test_quantified_phrase_can_remain_a_genitive_np_constituent(text, head, phrase):
    morph = Pymorphy3Morphology()
    backend = GenitiveBoundaryBackend('GENITIVE_DEP')
    parser = make_parser(morph, backend)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    head_token = next(item for item in tokens if item.text == head)
    phrase_end = next(item.index for item in tokens if item.text == phrase.split()[-1])
    end = parser._nominal_phrase_end(tokens, head_token.index, len(tokens) - 1, set())
    assert end == phrase_end
    assert len(backend.calls) == 1
    assert f'FOLLOWING PHRASE:\n{phrase}\n' in backend.calls[0][1]


def test_modifier_attachment_probe_asks_for_event_semantics_not_surface_adjacency():
    class Backend:
        def __init__(self):
            self.prompt = None

        def generate(self, prompt, *, system='', override=None, role='generic'):
            assert role == 'perception_modifier_attachment'
            self.prompt = prompt
            return LLMResponse('EVENT', {})

    text = 'Механик обработал панель из сплава.'
    morph = Pymorphy3Morphology()
    backend = Backend()
    parser = make_parser(morph, backend)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    predicate_token = next(item for item in tokens if item.text == 'обработал')
    prep_token = next(item for item in tokens if item.text == 'из')
    noun_token = next(item for item in tokens if item.text == 'сплава')
    predicate_span = parser._resolve_span(
        text, tokens, predicate_token.index, predicate_token.index
    )
    modifier_span = parser._resolve_span(text, tokens, prep_token.index, noun_token.index)
    selected = parser._resolve_modifier_attachment(
        text,
        tokens,
        predicate_span,
        PredicateCandidate('обработал', 'обработать'),
        modifier_span,
    )
    assert selected is not None and selected.kind.value == 'PREDICATE'
    assert backend.prompt is not None
    assert 'fills a semantic relation of this PREDICATE occurrence' in backend.prompt
    assert 'Syntactic adjacency alone does not decide' in backend.prompt
    assert 'including through an affected or resulting participant' in backend.prompt
