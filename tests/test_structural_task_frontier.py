from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.structural_tasks import choose,span,licensed


def setup(monkeypatch,answers,limit=100):
    state=t0('one two three');state.component_probe_records={};calls=[]
    release=SimpleNamespace(entries=lambda kind:[{'max_rule_steps':limit}])
    from ah.formalizer.regions import TextRegion
    state.evidence=[SimpleNamespace(token_id=str(i),span=word,start=a,end=b)
        for i,(word,a,b) in enumerate([('one',0,3),('two',4,7),('three',8,13)])]
    region=TextRegion('r','SENTENCE',(0,len(state.text)),tuple(t.token_id for t in state.evidence),None)
    cfg={'max_candidates':2,'context_chars':100}
    def probe(state,selector,release,key,slot,options,*args,**kwargs):
        answer=answers.pop(0);calls.append((slot,[o['candidate_id'] for o in options]))
        selected=options[0]['candidate_id'] if answer=='first' else None
        state.decisions[key]=SimpleNamespace(outcome='RESOLVED' if selected else 'UNRESOLVED',
            selected=(selected,) if selected else (),selector_outcome='ONE_SELECTED' if selected else answer)
        state.component_probe_records[key]={'decision':{}}
        state.clarification_candidates.append({'decision_ref':key}) if not selected else None
        return selected
    monkeypatch.setattr('ah.formalizer.structural_tasks._probe',probe)
    return state,release,region,cfg,calls


def test_none_fit_expands_and_retires_all_rejected_pages(monkeypatch):
    state,release,region,cfg,calls=setup(monkeypatch,['NONE_FIT','NONE_FIT','first'])
    options=[{'candidate_id':str(i),'label':str(i),'relation':'NOT'} for i in range(5)]
    value,proof=choose(state,release,None,region,cfg,'relation',options,'question')
    assert value['candidate_id']=='4' and len(calls)==3
    assert not state.clarification_candidates
    assert licensed(state,proof,relation='NOT') and not licensed(state,proof,relation='AND')
    assert all(r.get('superseded_by') for r in list(state.component_probe_records.values())[:2])


def test_unknown_keeps_unexamined_frontier(monkeypatch):
    state,release,region,cfg,calls=setup(monkeypatch,['INSUFFICIENT_CONTEXT'])
    assert choose(state,release,None,region,cfg,'relation',
        [{'candidate_id':str(i),'label':str(i)} for i in range(5)],'question') is None
    row=state.syntax_trace[-1]
    assert len(calls)==1 and row['status']=='PENDING' and not row['enumeration_complete']


def test_budget_is_shared_and_is_not_none_fit(monkeypatch):
    state,release,region,cfg,calls=setup(monkeypatch,['first'],limit=2)
    options=[{'candidate_id':str(i),'label':str(i)} for i in range(2)]
    assert choose(state,release,None,region,cfg,'first',options,'question')
    assert choose(state,release,None,region,cfg,'second',options,'question') is None
    assert len(calls)==1 and state.syntax_trace[-1]['reason']=='SEARCH_LIMIT'


def test_endpoint_rejection_reopens_start_domain(monkeypatch):
    state,release,region,cfg,calls=setup(monkeypatch,['first','NONE_FIT','NONE_FIT','NONE_FIT','first','first'])
    tokens=[SimpleNamespace(token_id=str(i),span=word,start=a,end=b)
        for i,(word,a,b) in enumerate([('one',0,3),('two',4,7),('three',8,13)])]
    result=span(state,release,None,region,tokens,cfg,'bounds','whole area')
    assert [t.span for t in result[0]]==['two']
    assert calls[-2][1]==['start:1','start:2']
    assert any(r.get('kind')=='STRUCTURAL_BOUNDARY_CONSTRAINT' for r in state.syntax_trace)


def test_context_limit_records_no_probe_reason(monkeypatch):
    state,release,region,cfg,calls=setup(monkeypatch,[])
    cfg['context_chars']=2
    assert choose(state,release,None,region,cfg,'bounds',[],'question') is None
    assert not calls and state.syntax_trace[-1]['reason']=='CONTEXT_LIMIT'


def test_incomplete_grammar_projection_cannot_fall_through_to_components(monkeypatch):
    from ah.formalizer.component_refinement import _compose_lexical_area
    state=t0('word');region=SimpleNamespace(region_id='r',source_range=(0,4))
    def reuse(*args):
        state.grammar_search_incomplete=True
        return []
    runtime=SimpleNamespace(sources=SimpleNamespace(reuse=reuse))
    monkeypatch.setattr('ah.formalizer.composition_session.current',lambda state:runtime)
    assert _compose_lexical_area(state,None,None,region,[],{'_literal_relation':True})==[]
    assert state.syntax_trace[-1]['reason']=='GRAMMAR_SEARCH_LIMIT'
    assert state.diagnostics[-1].code=='COMPONENT_SEARCH_INCOMPLETE'
