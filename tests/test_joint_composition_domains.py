from types import SimpleNamespace
from copy import deepcopy

from ah.formalizer.pipeline import t0
from ah.formalizer.composition_tree import reference
from ah.formalizer.scope_assignment import assign


RELEASE=SimpleNamespace(entries=lambda kind:[{'max_rule_steps':20000}])
REGION=SimpleNamespace(region_id='source-area',source_range=(0,10))
CFG={'max_candidates':64}


def run_scope(monkeypatch,modifiers,choose,tree=None):
    state=t0('scope text')
    def probe(state,selector,release,key,slot,options,*args,**kwargs):
        value=choose(options)
        return value['candidate_id'] if value else None
    monkeypatch.setattr('ah.formalizer.scope_assignment._probe',probe)
    return state,assign(state,RELEASE,None,REGION,tree or reference('P'),modifiers,CFG)


def expand(tree,contents):
    if tree.get('frame_ref') in contents:
        mid=tree['frame_ref'];return (mid,expand(contents[mid],contents))
    if 'frame_ref' in tree:return tree['frame_ref']
    return (tree['operator'],*(expand(c,contents) for c in tree['operands']))


def test_parent_can_select_an_unbuilt_operator(monkeypatch):
    desired={'outer':'inner','inner':None}
    state,result=run_scope(monkeypatch,[{'id':i,'label':i} for i in desired],
        lambda options:next(v for v in options if v['target']==desired[v['label'].split()[0]]))
    tree,contents,_=result
    assert expand(tree,contents)==('outer',('inner','P'))
    assert any(r.get('kind')=='SCOPE_DOMAIN' for r in state.syntax_trace)


def test_unknown_child_resumes_after_independent_parent_edge(monkeypatch):
    calls=[]
    def choose(options):
        mid=options[0]['label'].split()[0];calls.append(mid)
        if mid=='inner' and len(options)>1:return None
        return next(v for v in options if v['target']==('inner' if mid=='outer' else None))
    _,result=run_scope(monkeypatch,[{'id':i,'label':i} for i in ('inner','outer')],choose)
    assert calls==['inner','outer','inner']
    assert expand(*result[:2])==('outer',('inner','P'))


def test_three_edge_cycle_is_not_a_closed_reading(monkeypatch):
    desired={'a':'b','b':'c','c':'a'}
    def choose(options):
        return next((v for v in options if v['target']==desired[v['label'].split()[0]]),None)
    state,result=run_scope(monkeypatch,[{'id':i,'label':i} for i in desired],choose)
    assert result is None
    assert any(d.code=='COMPOSITION_SCOPE_UNRESOLVED' for d in state.diagnostics)


def test_nested_coordinate_groups_keep_original_indices(monkeypatch):
    tree={'operator':'AND','operands':[reference(x) for x in ('P','Q','R','S')]}
    modifiers=[{'id':'outer','label':'outer','allowed_paths':[(('group',(0,3)),)]},
               {'id':'inner','label':'inner','allowed_paths':[(('group',(1,3)),)]}]
    _,result=run_scope(monkeypatch,modifiers,lambda options:next(v for v in options if v['target'] is None),tree)
    assert expand(*result[:2])==('AND',('outer',('AND','P',('inner',('AND','Q','R')))),'S')


def test_binder_scope_must_dominate_every_use(monkeypatch):
    tree={'operator':'AND','operands':[reference('P'),reference('Q')]}
    def choose(options):
        assert len(options)==1 and options[0]['base']==()
        return options[0]
    _,result=run_scope(monkeypatch,[{'id':'forall','label':'forall','required_refs':['P','Q']}],choose,tree)
    assert expand(*result[:2])==('forall',('AND','P','Q'))


def test_parallel_descriptions_share_content_without_changing_identity(monkeypatch):
    def choose(options):
        mid=options[0]['label'].split()[0]
        if mid=='a':return next(v for v in options if v['target']=='b' and v['shared'])
        return next(v for v in options if v['target'] is None)
    _,result=run_scope(monkeypatch,[{'id':i,'label':i,'allow_shared':True} for i in ('a','b')],choose)
    assert expand(*result[:2])==('AND',('b','P'),('a','P'))


def test_recursive_grammar_closes_original_rule_over_child_tokens():
    from test_formalizer_v7_syntax_fixture import released,grammar
    from tools.formalizer_v7_test_support import role
    from ah.formalizer.pipeline import MorphProvider
    from ah.formalizer.composition_sources import CompositionSources
    release=released([('MOVE','перенести','VERB',[role('SUBJECT'),role('OBJECT',('acc',))])])
    state=grammar('Курьер не перенёс книгу.',release,MorphProvider())
    assert not state.frames
    original=deepcopy(state.evidence)
    inventory=CompositionSources(state,release)
    child=[t for t in state.evidence if t.span!='не']
    inventory.project_grammar(child)
    alternatives=inventory.alternatives(child)
    assert len(alternatives)==1
    assert set(alternatives[0][1][0].semantic['proposed_roles'].values())=={'SUBJECT','OBJECT'}
    assert state.evidence==original
    rows=[r for r in state.syntax_trace if r.get('kind')=='GRAMMAR_DOMAIN']
    assert any(any(s['status']=='COMPLETE' for s in r['states'].values()) for r in rows)
    before=len(state.syntax_trace);inventory.project_grammar(child)
    assert len(state.syntax_trace)==before


def test_resumed_real_probe_retires_obsolete_pending_question():
    from ah.formalizer.composition_session import session
    class Release:
        sha256='scope-test-release'
        def entries(self,kind):
            return [{'max_rule_steps':20000,'composition':CFG}] if kind=='ProposalPolicy' else []
    class Selector:
        selection_reply_format='SELECT_LABELS_V1'
        def __init__(self):self.replies=iter(['?','2','1'])
        def select(self,prompt):return next(self.replies)
    state=t0('scope text');state.budget.llm_limit=10
    modifiers=[{'id':i,'label':i} for i in ('inner','outer')]
    with session(state,Release()) as runtime:
        def compute():
            result=assign(state,Release(),Selector(),REGION,reference('P'),modifiers,CFG)
            assert result is not None and expand(*result[:2])==('outer',('inner','P'))
            return [SimpleNamespace(frame_id='P',semantic={})]
        runtime.child('child',compute)
        assert runtime.tasks.cache['child',None]['complete']
        assert runtime.tasks.cache['child',None]['pending']==[]
    assert state.clarification_candidates==[]
    old=[r for r in state.component_probe_records.values() if r.get('superseded_by')]
    assert len(old)==1 and old[0]['decision']['raw_response']=='?'


def test_conflicting_restriction_rules_are_not_silently_overwritten():
    from ah.formalizer.quantifier_composition import lexical_matches
    state=t0('каждый')
    token=SimpleNamespace(token_id='q',start=0,end=6)
    region=SimpleNamespace(region_id='r',source_range=(0,6))
    rule={'pattern':'каждый','operator':'FORALL','attachment_kinds':['QUANTIFIED_NOMINAL'],
          'variable_sort':'ENTITY','restriction_pattern':{'role':'SUBJECT'}}
    other={**rule,'restriction_pattern':{'role':'OBJECT'}}
    release=SimpleNamespace(entries=lambda kind:[rule,other])
    assert lexical_matches(state,release,region,[token]) is None
    assert state.diagnostics[-1].code=='QUANTIFIER_LEXICAL_SCOPE_UNRESOLVED'


def test_binder_search_budget_blocks_before_binding_or_probing():
    from ah.formalizer.quantifier_composition import bind
    state=t0('q noun')
    release=SimpleNamespace(entries=lambda kind:[{'max_rule_steps':0}])
    rule={'restriction_pattern':{}}
    frame=SimpleNamespace(semantic={},argument_token_refs=['noun'])
    assert bind(state,release,None,REGION,[frame],{(0,1,'FORALL'):([],rule)},CFG) is None
    assert state.diagnostics[-1].code=='COMPONENT_SEARCH_INCOMPLETE'
    assert frame.semantic=={}
