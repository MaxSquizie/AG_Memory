from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds
from ah.formalizer import v7_pipeline
for depth in (4,18):
    steps=[]
    for marker in ['Неверно']+['неверно']*(depth-1):
        steps+=relation('NOT')+bounds('structural_introducer',marker,'что')+[('structural_partition','PARTITION')]
    steps+=relation('LEXICAL')
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        captured=[];original=v7_pipeline.build_plan
        def capture(state,*a,**kw):
            captured.append(state)
            return original(state,*a,**kw)
        patch.setattr(v7_pipeline,'build_plan',capture)
        result,_=run(Path(tmp),patch,'Неверно что '+'неверно что '*(depth-1)+'Иван пришёл.',steps)
        assert not result['diagnostics']['codes'],result['diagnostics']
        fact=result['assertions']['ah'][0]
        for _ in range(depth):
            assert fact['operator']=='NOT',fact
            fact=fact['operands'][0]
        assert fact['predicate']=='ARRIVE',fact
        trace=[r for r in captured[-1].syntax_trace if r.get('kind','').startswith('COMPOSITION_EXPANSION')]
        assert any(r['kind']=='COMPOSITION_EXPANSION_DEFERRED' for r in trace),trace
        print('PASS:',depth,'nested NOT -> ARRIVE, native write;',len(trace)//2,'expansion checkpoints')
