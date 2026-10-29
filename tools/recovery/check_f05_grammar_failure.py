"""Grammar projection retry/cache evidence, controlled producer failures."""
from pytest import MonkeyPatch
from test_composition_dispatcher import setup_morphology
from ah.formalizer.composition_session import session
from ah.formalizer import syntax_rules

for failure in [syntax_rules.SearchLimit('controlled budget'),RuntimeError('controlled failure')]:
    state,release,region,cfg=setup_morphology('Иван пришёл.')
    calls=[]
    with MonkeyPatch.context() as patch,session(state,release) as runtime:
        def fail(*args):
            calls.append(1)
            raise failure
        patch.setattr(syntax_rules,'propose_graphs',fail)
        if isinstance(failure,syntax_rules.SearchLimit):
            assert runtime.sources.project_grammar(state.evidence) is False
            node=next((k,n) for k,n in runtime.dispatcher.nodes.items() if n['kind']=='GRAMMAR')
            assert node[1]['receipt']['task_outcome']=='SEARCH_INCOMPLETE'
            runtime.dispatcher.invalidate(node[0],'CONTROLLED_RECHECK')
            assert runtime.sources.project_grammar(state.evidence) is False
            assert len(calls)==1 # no provider retry on the same exhausted search
            assert node[1]['receipt']['task_outcome']=='SEARCH_INCOMPLETE'
            assert any(d.code=='COMPONENT_SEARCH_INCOMPLETE' for d in state.diagnostics)
        else:
            for _ in range(2):
                try:runtime.sources.project_grammar(state.evidence)
                except RuntimeError as exc:assert exc is failure
                else:raise AssertionError('failed projection masqueraded as completed')
            assert len(calls)==2 and not runtime.sources.projected
print('PASS: cached search failure retains diagnostics/receipt; unexpected failure never marks projection completed')
