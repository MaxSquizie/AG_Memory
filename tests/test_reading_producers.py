"""P02 raw selection integration; real codec, controlled answers, no model claims."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.state import MorphVariant
from ah.formalizer.regions import TextRegion
from ah.formalizer.morphology_domain import offer,clean,license_use,attested
from ah.formalizer.reading_producers import binding,attach,from_selection,issue,assessment
from ah.formalizer.component_probe import _probe
from test_composition_dispatcher import First


def prepared(issue_use=True):
    state=t0('example');state.budget.llm_limit=10
    token=state.evidence[0];token.token_id='t'
    token.variants=(MorphVariant('example','ADJF',frozenset({'nom'})),)
    release=NS(sha256='test');region=TextRegion('r','SENTENCE',(0,7),('t',),None)
    value=offer(state,token,[replace(token.variants[0],pos='NOUN')],'TEST')[0]
    entry=binding(state,release,region,'t',value,{'kind':'ARGUMENT','role':'SUBJECT'})
    options=[attach({'candidate_id':'selected','label':'The occurrence is the subject'},[entry])]
    assert _probe(state,First(),release,'d','nominal_attachment',options,state.text,(0,7),
                  question='Which function does the occurrence have?',target_refs=('t',))=='selected'
    w=from_selection(state,'d','selected',entry)
    if issue_use:license_use(state,'t',clean(value),'d','selected',witness=w)
    return state,token,clean(value),w


def test_raw_selected_payload_licenses_exact_whole_reading():
    state,token,reading,w=prepared()
    assert assessment(state,w).selected_use
    assert attested(state,token,reading)
    assert not attested(state,token,{**reading,'cases':['dat']})


def test_recapture_changed_packet_does_not_forge_new_role():
    state,_,_,_=prepared()
    entry=state.component_probe_records['d']['payload_contract']['options'][0]['reading_uses'][0]
    entry['use']['role']='OBJECT'
    w=from_selection(state,'d','selected',entry)
    assert assessment(state,w).reason=='DIRECT_PAYLOAD_NOT_BOUND'


@pytest.mark.parametrize('field,value',[('reading',{'pos':'VERB'}),('use',{'role':'OBJECT'}),('token_ref','elsewhere')])
def test_preselected_entry_cannot_be_replaced_after_answer(field,value):
    state,_,_,_=prepared()
    entry=deepcopy(state.component_probe_records['d']['payload_contract']['options'][0]['reading_uses'][0])
    entry[field]=value
    assert not assessment(state,from_selection(state,'d','selected',entry)).selected_use


def test_context_revision_retires_direct_use():
    state,_,_,w=prepared();state.context_version+=1
    assert assessment(state,w).reason=='DIRECT_CONTEXT_CHANGED'


def test_negative_cached_query_is_invalidated_when_exact_use_is_issued(monkeypatch):
    from ah.formalizer.composition_dispatcher import Dispatcher
    from ah.formalizer import composition_session
    state,token,reading,w=prepared(issue_use=False);dispatcher=Dispatcher(state)
    monkeypatch.setattr(composition_session,'current',lambda _:NS(dispatcher=dispatcher))
    calls=[]
    def compute():calls.append(1);return attested(state,token,reading)
    assert not dispatcher.run('consumer',[],compute,kind='TEST')
    assert not dispatcher.run('consumer',[],compute,kind='TEST') and len(calls)==1
    license_use(state,'t',reading,'d','selected',witness=w)
    assert dispatcher.run('consumer',[],compute,kind='TEST') and len(calls)==2
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':'d'})
    assert not dispatcher.run('consumer',[],compute,kind='TEST') and len(calls)==3


def test_same_condition_does_not_authorize_sibling_scope():
    from ah.formalizer.reading_producers import evaluate
    state,_,_,w=prepared()
    scope={'input_scope':'sibling','region_ref':'r','token_refs':['t'],'morphology_scope':None}
    assert evaluate(state,w,None,scope).reason=='READING_USE_OUTSIDE_SCOPE'
