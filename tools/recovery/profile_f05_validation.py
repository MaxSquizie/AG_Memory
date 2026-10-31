"""Scripted native production and pure validation, measured separately."""
from collections import Counter
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import json
from pytest import MonkeyPatch
from test_structural_open_forest import native
from test_structural_frontier import TEXT,answer
from ah.formalizer import structural_conditions as conditions,structural_shells as shells
from ah.formalizer import structural_tasks as tasks,structural_probe_inputs as inputs


def main():
    calls=Counter();nested=0;maximum=0
    def wrap(name,fn):
        @wraps(fn)
        def measured(*args,**kw):
            nonlocal nested,maximum
            calls[name]+=1;nested+=1;maximum=max(maximum,nested)
            try:return fn(*args,**kw)
            finally:nested-=1
        return measured
    def reset():
        nonlocal maximum
        calls.clear();maximum=0
    def stats(start):return {'seconds':round(perf_counter()-start,4),'calls':dict(calls),'maximum_validation_call_nesting':maximum}
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        for module,name in [(conditions,'historical'),(shells,'live'),(shells,'evidence_state'),
                            (tasks,'_licensed'),(inputs,'source_signature')]:
            patch.setattr(module,name,wrap(name,getattr(module,name)))
        from ah.formalizer.validation_graph import ValidationGraph
        actual_run=ValidationGraph.run;totals=Counter()
        def measured_run(self,*args,**kwargs):
            before=dict(self.stats)
            try:return actual_run(self,*args,**kwargs)
            finally:
                for key,value in self.stats.items():
                    if key=='maximum_pending':totals[key]=max(totals[key],value)
                    else:totals[key]+=value-before[key]
        patch.setattr(ValidationGraph,'run',measured_run)
        start=perf_counter();state,result,_=native(Path(tmp),patch,('AND','OR'),answer,text=TEXT)
        report={'native_bfs3':{**stats(start),'graph':dict(totals)}}
        assert not result['assertions']['ah']
        row=next(r for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL')
        report['shell_json_bytes']=len(json.dumps(row,ensure_ascii=False).encode())
        report['registry_json_bytes']=len(json.dumps(state.observation['structural_condition_registry'],ensure_ascii=False).encode())
        reset();totals.clear();start=perf_counter();assert shells.live(state,row)
        report['pure_shell']={**stats(start),'graph':dict(totals)}
        reset();totals.clear();start=perf_counter();assert shells.live(state,row)
        report['repeat_shell']={**stats(start),'graph':dict(totals)}
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
