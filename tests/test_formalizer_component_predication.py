"""General predicate/scope constructors; scripted choices test contracts only."""
import pytest
from ah.formalizer.canonical_ledger import digest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.pipeline import MorphProvider
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices, frontend


@pytest.mark.parametrize('text,root,child',[
    ('Очень жаркий день.','Очень','жаркий'),
    ('Доклад кончился вовремя.','вовремя','кончился'),
    ('Вечером занимался.','Вечером','занимался'),
    ('Почти ушёл.','Почти','ушёл'),
    ('Едва успел.','Едва','успел'),
])
def test_scoped_modifier_commits_only_outer_truth_and_replays(tmp_path,text,root,child):
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal)
    kwargs=dict(release=release,morph=MorphProvider(),run_id='scope',observation_id='O')
    st,report=interpret_full(text,None,Choices([0]*12),store,binding,**kwargs)
    assert report.applied, (report,st.diagnostics)
    nodes=store.ledger.data['nodes']; evidence={e.token_id:e.span for e in st.evidence}
    by_surface={evidence[n['source_ref']]:nid for nid,n in nodes.items() if n.get('template_ref')}
    assert set(by_surface)=={root,child}
    assert {p['conclusion_ref'] for p in store.ledger.data['supports'].values()}=={by_surface[root]}
    assert by_surface[child] in store.ledger.s_accessible()
    assert not store.ledger.data['assertions']
    assert len(store.ledger.data['usage_links'])==1
    _,again=interpret_full(text,None,Choices([0]*12),store,binding,**kwargs)
    assert again.batch_hash==report.batch_hash
    restored_core=AHCore();restored=AHStoreAdapter(restored_core.store,journal,restored_core)
    assert digest(restored.ledger.data)==digest(store.ledger.data)
    store.retract_observation(st.source_uid,1,trigger_ref='retract')
    assert not store.ledger.paths()
    assert by_surface[child] not in store.ledger.s_accessible()


def test_quality_copula_is_not_a_second_event(tmp_path):
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    st,r=interpret_full('Вода была хорошая.',None,Choices([0]*8),store,InterpretationRunBinding(journal),
        release=release,morph=MorphProvider(),run_id='quality')
    assert r.applied
    assert len(store.ledger.data['nodes'])==1
    assert not store.ledger.data['assertions']
    chosen=[f for f in st.frames if not f.semantic['structural_unresolved']]
    assert len(chosen)==1 and chosen[0].semantic['copula_ref']


@pytest.mark.parametrize('text',[
    'Очень быстро ушёл.',  # no unchecked nesting order for two modifiers
    'Хорошая.',           # do not invent an entity for an adjective
    'Вода был хорошая.',  # agreement mismatch must not consume the copula
    'После завтрака почти ушёл.', # relative scope not yet composable under a modifier
])
def test_unlicensed_composition_does_not_escape(text):
    release=with_components(test_release(AHCore()),predication=True,relative_time=True)
    st=frontend(text,MorphProvider(),Choices([0]*20),release)
    assert not st.frames or all(f.semantic['structural_unresolved'] for f in st.frames)


def test_preposition_scope_inside_conjunction_is_not_discarded(tmp_path):
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    st,r=interpret_full('Покатались на шлюпках и купались.',None,Choices([0]*16),store,InterpretationRunBinding(journal),
        release=release,morph=MorphProvider(),run_id='pp')
    assert r.applied,(r,st.diagnostics)
    evidence={e.token_id:e.span for e in st.evidence}
    nodes=store.ledger.data['nodes']
    ids={evidence[n['source_ref']]:nid for nid,n in nodes.items() if n.get('template_ref')}
    assert set(ids)=={'Покатались','на','купались'}
    visible={s['conclusion_ref'] for s in store.ledger.data['supports'].values()}
    assert ids['Покатались'] not in visible
    assert ids['на'] in visible and ids['купались'] in visible
    assert len([n for n in nodes.values() if n.get('function_id')=='AND'])==1
    assert len(r.committed_fragments)==1
    assert len(store.ledger.paths())==3
    assert ids['Покатались'] in store.ledger.s_accessible()


def test_multiple_reference_labels_for_one_established_entity_are_not_ambiguity():
    import json
    class SameReferences(Choices):
        def select(self,prompt):
            if len([line for line in prompt.splitlines() if 'Same participant as omitted SUBJECT' in line]) == 2:
                self.prompts.append(prompt)
                ids=[line.split('. ',1)[0] for line in prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0].splitlines()
                     if 'Same participant as omitted SUBJECT' in line]
                return json.dumps({'outcome':'MULTIPLE_ADMISSIBLE','selected':ids})
            return super().select(prompt)
    release=with_components(test_release(AHCore()))
    st=frontend('Отдыхал. Гулял. Занимался.',MorphProvider(),SameReferences([0,1]),release)
    bindings=st.observation['implicit_bindings']
    assert len(bindings)==3 and len({b['entity_ref'] for b in bindings.values()})==1
    decisions=[d for d in st.decisions.values() if d.selector_outcome=='MULTIPLE_ADMISSIBLE']
    assert len(decisions)==1 and decisions[0].outcome=='RESOLVED'
    assert decisions[0].history[-1]['kind']=='EQUIVALENT_REFERENCE_SELECTION'


def test_native_receipt_never_enters_legacy_template_completion():
    from ah.integration.template_completion import TemplateCompletionService
    from ah.perception.contracts import PerceptionResult, AssertionCandidate, PredicateCandidate
    p=PerceptionResult(source_text='scope', assertions=(AssertionCandidate(local_id='a',
        predicate=PredicateCandidate(surface='unmapped scoped predicate'),actants=()),),native_receipt=object())
    # No integration/perception service may be consulted at this boundary.
    assert TemplateCompletionService(None,None).complete(p) is p


def test_coordination_counts_complete_clauses_not_possible_verb_readings(tmp_path):
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    st,r=interpret_full('Вода была хорошая и день был жаркий.',None,Choices([0]*16),store,InterpretationRunBinding(journal),
        release=release,morph=MorphProvider(),run_id='quality-and')
    assert r.applied,(r,st.diagnostics)
    assert len(r.committed_fragments)==1
    assert len(store.ledger.paths())==3
    evidence={e.token_id:e.span for e in st.evidence}
    assert {evidence[n['source_ref']] for n in store.ledger.data['nodes'].values() if n.get('template_ref')}=={'хорошая','жаркий'}
    assert not store.ledger.data['assertions']


def test_multiple_references_to_different_people_stay_unresolved():
    import json
    class DifferentReferences(Choices):
        def select(self,prompt):
            section=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0]
            ids=[line.split('. ',1)[0] for line in section.splitlines()
                 if 'Same participant as omitted SUBJECT' in line]
            if len(ids)==2:
                return json.dumps({'outcome':'MULTIPLE_ADMISSIBLE','selected':ids})
            return super().select(prompt)
    release=with_components(test_release(AHCore()))
    st=frontend('Отдыхал. Гулял. Занимался.',MorphProvider(),DifferentReferences([0,0]),release)
    values=list(st.observation['implicit_bindings'].values())
    assert len(values)==2 and values[0]['entity_ref']!=values[1]['entity_ref']
    assert any(d.outcome=='UNRESOLVED' and d.selector_outcome=='MULTIPLE_ADMISSIBLE' for d in st.decisions.values())


def test_implicit_probe_identifies_target_clause_not_just_shared_context():
    selector=Choices([0]*12)
    st=frontend('Отдыхал. Гуляли. Занимался.',MorphProvider(),selector)
    questions=[p for p in selector.prompts if 'Decision slot: implicit_argument' in p]
    assert len(questions)==3
    assert 'Target clause:  Занимался.' in questions[-1].split('\n\n',1)[0]
    assert 'Target predicate: Занимался' in questions[-1].split('\n\n',1)[0]
    assert "'number': 'sing'" in questions[-1].split('\n\n',1)[0]
    assert 'Гуляли.' in questions[-1]  # context is retained but cannot become the target
