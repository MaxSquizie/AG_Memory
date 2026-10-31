"""Native flat-group production profile with scripted, occurrence-addressed replies.

Initial AND/OR membership is deliberately ambiguous, as in the chain profile.
Leaf LEXICAL producers stay pending capability; this is not a publication run.
"""
import argparse
import json
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_open_forest import native
from ah.formalizer.composition_session import _current
from ah.formalizer.structural_shells import live


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parts',type=int,default=17)
    args=parser.parse_args()
    if args.parts<2:parser.error('parts must be at least 2')
    text=' и '.join(['Иван читает']*args.parts)
    def answer(slot,prompt):
        labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
        if slot=='structural_group_next':
            return next((n for n,label in labels if label.startswith('Another direct part begins at «Иван»')),'0')
        if 'Optional search:' in prompt:return '0'
        if slot=='structural_relation':
            return next((n for n,label in labels if 'One lexical predication' in label),'0')
        if slot in {'structural_partition','relation_marker_role'}:return '1'
        match=re.fullmatch(r'structural_operand_(\d+)_(start|end)',slot)
        if match:
            index=int(match[1])-1;start=match[2]=='start'
            token=_current.get().area_inputs[1][3*index+(0 if start else 1)]
            prefix=('Start at' if start else 'End after')+' «'+token.span+'» @'+str(token.start if start else token.end)
            return next((n for n,label in labels if label.startswith(prefix)),'0')
        return '?'
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        begin=time.perf_counter()
        state,result,prompts=native(Path(tmp),patch,('AND','OR'),answer,text=text)
        elapsed=time.perf_counter()-begin
        rows=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL']
        assert len(rows)==2 and all(live(state,r) and len(r['children'])==args.parts for r in rows)
        snapshot=next(iter(state.observation['structural_frontiers'].values()))
        assert len(snapshot['jobs'])==1+2*args.parts and max(j['depth'] for j in snapshot['jobs'])==2
        assert not result['assertions']['ah']
        print(json.dumps({'parts':args.parts,'production_seconds':elapsed,'prompt_calls':len(prompts),
            'shells':len(rows),'jobs':len(snapshot['jobs']),'max_depth':2,
            'execution':'native producers, scripted answers, no publication'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
