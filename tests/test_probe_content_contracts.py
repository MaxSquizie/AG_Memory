"""Small cross-layer contracts for the probe-content audit (no live provider)."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.composition_equivalence import component_signature,coalesce_components


def frame(fid,role='SUBJECT',caps=None):
    return FrameCandidate('frame:'+fid,'FLAT','reads',('person',),predicate_token_ref='p',
        semantic={'proposed_roles':{'a':role},'morph_bindings':{},'component_questions':[],
                  'allowed_proposition_roles':caps})


def test_equivalence_keeps_all_producer_capabilities_but_not_different_roles():
    a,b=frame('a',caps=[]),frame('b',caps=None)
    state=t0('source');region=SimpleNamespace(region_id='r')
    retained,duplicates=coalesce_components(state,region,[[a],[b]])
    assert len(retained)==1 and duplicates=={'frame:b'}
    assert retained[0][0].semantic['allowed_proposition_roles'] is None
    assert state.syntax_trace[-1]['capability_union'][0]['producer_domains']==[[],None]
    c=frame('c',role='OBJECT')
    assert component_signature([a])!=component_signature([c])
    d=deepcopy(a);d.semantic['future_unrecognized_field']='meaningful'
    assert component_signature([a])!=component_signature([d])
    a.semantic['action_description']={'unassigned_roles':[],'valency_digest':'released'}
    b.semantic['action_description']={'unassigned_roles':[],'valency_digest':None}
    retained,_=coalesce_components(state,region,[[a],[b]])
    assert len(retained)==1
    assert retained[0][0].semantic['action_description']['valency_digests']==['released']
    c=deepcopy(b);c.semantic['action_description']['unassigned_roles']=['OBJECT']
    assert component_signature([b])!=component_signature([c])


def test_invisible_difference_never_reaches_provider():
    from ah.formalizer.component_probe import _live_probe
    class Selector:
        def select(self,prompt):raise AssertionError('must not ask an impossible question')
    state=t0('source')
    assert _live_probe(state,Selector(),SimpleNamespace(sha256='release'),'k','role',[
        {'candidate_id':'a','label':'same'}, {'candidate_id':'b','label':'same'}],state.text,(0,6)) is None
    assert state.diagnostics[-1].code=='PROBE_OPTIONS_INDISTINGUISHABLE'


def test_common_description_projection_is_lossless():
    from ah.formalizer.probe_presentation import factor_options
    values=[{'candidate_id':'a','label':'predicate read; noun book; attaches to event'},
            {'candidate_id':'b','label':'predicate read; noun book; attaches to entity'}]
    shortened,common=factor_options(values)
    assert [common+'; '+r['label'] for r in shortened]==[r['label'] for r in values]
    assert [r['candidate_id'] for r in shortened]==['a','b']


def test_established_role_cannot_be_overridden_by_complete_candidate():
    from ah.formalizer.component_constraints import retain_role,compatible_bundle
    state=t0('source');region=SimpleNamespace(region_id='r')
    retain_role(state,region,SimpleNamespace(token_id='p'),SimpleNamespace(token_id='a'),
                ({'candidate_id':'SUBJECT'},{'decision_ref':'proof','candidate_id':'SUBJECT'}))
    assert compatible_bundle(state,region,[frame('f')])
    assert not compatible_bundle(state,region,[frame('g',role='OBJECT')])


@pytest.mark.parametrize('text,word,kind',[('Он пришёл.','Он','REFERENCE'),('Многие пришли.','Многие','QUANTITY')])
def test_shared_function_and_head_remain_selectable(tmp_path,monkeypatch,text,word,kind):
    from test_structural_relation_tasks import run,relation,bounds
    label='An expression points' if kind=='REFERENCE' else 'An expression says how many'
    steps=relation('LEXICAL')+[('nominal_function',label)]+bounds('nominal_function_source',word,word)+[
        ('nominal_function_head','Nominal head «'+word+'»')]
    if kind=='REFERENCE':steps+=[('nominal_identity_function','Identify the nominal')]
    else:steps+=[('nominal_external_case','Nominative case')]
    steps+=[('nominal_function','0')]
    if kind=='QUANTITY':steps+=[('predicate_function','Predicate occurrence «пришли»'),('component_attachment','прийти')]
    result,script=run(tmp_path,monkeypatch,text,steps)
    head=next(p for s,p in script.calls if s=='nominal_function_head')
    assert 'this occurrence also carries the selected function' in head
    assert 'PROBE_OPTIONS_INDISTINGUISHABLE' not in result['diagnostics']['codes']
    selected=[f for f in result['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved')]
    assert selected
    if kind=='QUANTITY':
        assert result['diagnostics']['codes']==[]
        assert result['assertions']['ah'][0]['predicate']=='ARRIVE'
        assert any(g['head_ref']==g['marker_ref'] for f in selected for g in f['semantic'].get('qualitative_groups',()))
    else:
        assert any(u.get('reference_constraint',{}).get('head_ref') in u.get('reference_constraint',{}).get('function_refs',())
                   for f in selected for u in f['semantic'].get('lexical_units',{}).values())


def test_lexical_choice_receives_selected_child_and_definition(tmp_path,monkeypatch):
    from test_structural_relation_tasks import run,relation,content_steps
    result,script=run(tmp_path,monkeypatch,'Иван сказал, что Пётр пришёл.',content_steps('сказал','Пётр','пришёл')+relation('LEXICAL'))
    prompt=next(p for s,p in script.calls if s=='predicate_value' and 'TARGET: Иван сказал' in p)
    assert 'Пётр пришёл' in prompt and 'ESTABLISHED STRUCTURE' in prompt
    assert 'communicates the propositional content' in prompt


def test_missing_extension_meanings_do_not_trigger_model():
    from ah.formalizer.open_set_probe import propose_value
    class Selector:
        def select(self,prompt):raise AssertionError('missing semantic contract')
    assert propose_value('slot',['text'],Selector(),['OLD']) is None


def test_control_of_passive_content_binds_patient_not_actor(tmp_path,monkeypatch):
    from test_structural_relation_tasks import run,relation,content_steps
    result,script=run(tmp_path,monkeypatch,'Иван хочет быть приглашён.',
        content_steps('хочет','быть','приглашён',attitude='HYPOTHETICAL')+
        [('structural_control','Same SUBJECT')]+relation('LEXICAL')+
        [('predicate_function','Predicate occurrence «приглашён»')])
    assert result['diagnostics']['codes']==[]
    child=next(f for f in result['runtime']['ir']['frames'] if f['anchor_span']=='приглашён' and not f['semantic']['structural_unresolved'])
    assert child['semantic']['control_binding']['child_role']=='OBJECT'
    assert set(child['semantic']['proposed_roles'].values())=={'OBJECT'}
    assert len(result['assertions']['ah'])==1
    assert result['assertions']['ah'][0]['predicate']=='WANT'
    assert 'A passive subject receives the action' in next(p for s,p in script.calls if s=='structural_control')


def test_predicted_numeral_lemma_is_not_a_resource_fact():
    from ah.formalizer.numeral_extraction import extract_cardinal_value
    token=SimpleNamespace(span='unknown',lemma='пять',variants=[SimpleNamespace(lemma='пять',origin='PREDICTED')])
    assert extract_cardinal_value([token]) is None
