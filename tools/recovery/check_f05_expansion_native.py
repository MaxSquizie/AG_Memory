from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds
from ah.formalizer import v7_pipeline
steps=[]
for marker in ['Неверно','неверно','неверно','неверно']:
    steps+=relation('NOT')+bounds('structural_introducer',marker,'что')+[('structural_partition','PARTITION')]
steps+=relation('LEXICAL')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    captured=[];original=v7_pipeline.build_plan
    def capture(state,*a,**kw):
        captured.append(state)
        return original(state,*a,**kw)
    patch.setattr(v7_pipeline,'build_plan',capture)
    result,_=run(Path(tmp),patch,'Неверно что неверно что неверно что неверно что Иван пришёл.',steps)
    assert not result['diagnostics']['codes'],result['diagnostics']
    fact=result['assertions']['ah'][0]
    for _ in range(4):
        assert fact['operator']=='NOT',fact
        fact=fact['operands'][0]
    assert fact['predicate']=='ARRIVE',fact
    trace=[r for r in captured[-1].syntax_trace if r.get('kind','').startswith('COMPOSITION_EXPANSION')]
    assert any(r['kind']=='COMPOSITION_EXPANSION_DEFERRED' for r in trace),trace
    print('PASS: four nested NOT -> ARRIVE, native write, expansion checkpoint',trace)
