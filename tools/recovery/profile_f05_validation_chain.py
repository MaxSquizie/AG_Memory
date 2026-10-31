"""Test-only deep chain of actual producers; production frontier remains 1..3."""
import argparse,json,re,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from pytest import MonkeyPatch
from test_structural_open_forest import native
from ah.formalizer import structural_frontier as frontier
from ah.formalizer.composition_session import _current,activate
from ah.formalizer.structural_conditions import child_scope
from ah.formalizer.structural_shells import produce,live
from ah.formalizer.validation_graph import scope


def answer(slot,prompt):
    runtime=_current.get();tokens=runtime.area_inputs[1]
    labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
    cuts=[i for i,t in enumerate(tokens) if t.span=='и']
    if slot=='structural_relation':
        label='Conjunction:' if cuts else 'One lexical predication'
        return next((n for n,v in labels if label in v),'0')
    if 'Optional search:' in prompt:return '0'
    # Deliberate binary encoding for the historical stress test, not a claim
    # that a homogeneous source list semantically requires this nesting.
    if slot=='structural_operand_count':
        return next((n for n,v in labels if v.startswith('2 direct content parts')),'0')
    if slot in {'structural_partition','relation_marker_role'}:return '1'
    if not cuts:return '?'
    cut=cuts[0]
    token={'structural_operand_1_start':tokens[0],'structural_operand_1_end':tokens[cut-1],
           'structural_operand_2_start':tokens[cut+1],'structural_operand_2_end':tokens[-1]}.get(slot)
    if token:
        label=('Start at' if slot.endswith('start') else 'End after')+' «'+token.span+'» @'+str(token.start if slot.endswith('start') else token.end)
        return next((n for n,v in labels if v.startswith(label)),'0')
    return '?'


def main(depth):
    original=frontier.start;selected=[]
    def start(runtime,*args):
        result=original(runtime,*args)
        driver=next(iter(runtime.structural_frontiers.values()))
        for level in range(4,depth+1):
            job=next(j for j in driver.jobs.values() if j['depth']==level and len(j['tokens'])>2)
            state=job['state'];local=job['runtime'];driver.sync(job);begin=len(state.syntax_trace)
            with activate(local),child_scope(state,job['parent_shell'],job['child'],job['cfg']):
                job['forest']=frontier.one_level(state,local,job['region'],job['tokens'],job['cfg'],job['request'])
                assert job['forest'] is not None
                job['results']=produce(state,local.release,local.selector,job['region'],job['tokens'],job['cfg'],job['request'],job['forest'])
            driver.publish_diagnostics(job,begin)
            shell=next(s for s in job['results'] if s['status']=='SHELL_PRODUCED')
            assert live(state,shell)
            driver.enqueue_children(job,shell)
            selected[:]=[(state,shell)]
            print('producer depth',level,'complete',file=sys.stderr,flush=True)
        if not selected:
            job=next(j for j in driver.jobs.values() if j['depth']==3 and j['results'] and j['results'][0]['status']=='SHELL_PRODUCED')
            selected.append((job['state'],job['results'][0]))
        return result
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        patch.setattr(frontier,'start',start)
        before=perf_counter();native(Path(tmp),patch,('AND','OR'),answer,text=' и '.join(['Иван читает']*(depth+1)))
        report={'depth':depth,'production_seconds':round(perf_counter()-before,4)}
        print('production complete; measuring pure validation',file=sys.stderr,flush=True)
        state,shell=selected[0]
        report['shell_bytes']=len(json.dumps(shell,ensure_ascii=False).encode())
        from ah.formalizer import validation_graph
        actual_expand=validation_graph.expand;frame_depths=[]
        def measured_expand(item):
            frame=sys._getframe();count=0
            while frame:count+=1;frame=frame.f_back
            frame_depths.append(count)
            return actual_expand(item)
        patch.setattr(validation_graph,'expand',measured_expand)
        for name in ('pure','repeat'):
            frame_depths.clear()
            before=perf_counter()
            with scope() as graph:assert live(state,shell)
            report[name]={'seconds':round(perf_counter()-before,4),**graph.stats,
                'python_frames_min':min(frame_depths),'python_frames_max':max(frame_depths)}
        node=state.observation['structural_condition_registry'][shell['condition']['condition_ref']]
        for _ in range(max(0,depth//2-1)):
            node=state.observation['structural_condition_registry'][node['parent_condition_ref']]
        state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':node['forest']['membership']['decision_ref']})
        before=perf_counter()
        with scope() as graph:assert not live(state,shell)
        report['ancestor_revoked']={'seconds':round(perf_counter()-before,4),**graph.stats}
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--depth',type=int,default=3)
    main(parser.parse_args().depth)
