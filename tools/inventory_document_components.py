"""Diagnostic source inventory: real morphology/IR, deliberately no model decisions.

Every requested probe returns INSUFFICIENT_CONTEXT. Counts describe candidates,
not semantic accuracy or committed events. No AH commit is performed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from time import monotonic


class NoDecision:
    def __init__(self): self.prompts=[]
    def select(self,prompt):
        self.prompts.append(prompt)
        return json.dumps({'outcome':'INSUFFICIENT_CONTEXT','selected':[]})
    def propose(self,prompt): raise AssertionError('model graphs are forbidden')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--development-fixture',action='store_true',required=True)
    args=parser.parse_args(argv)
    args.out.mkdir(parents=True,exist_ok=False)
    from ah.core import AHCore
    from ah.formalizer.native_frontend import run_native
    from ah.formalizer.pipeline import MorphProvider
    from tools.formalizer_v7_native_binding import fixture
    from tools.formalizer_component_fixture import with_components
    raw=args.source.read_bytes(); text=raw.decode('utf-8')
    core=AHCore(); release,_=fixture(core,'known'); release=with_components(release)
    selector=NoDecision(); start=monotonic(); source_hash=hashlib.sha256(raw).hexdigest()
    state=run_native(text,selector,release,{'observation_id':'inventory:'+source_hash,
        'source_id':'source:'+source_hash,'interpretation_version':1,'text':text,
        'structural_contract':'region_probes','syntax_budget_scope':'SOURCE_WINDOW_V1'},MorphProvider())
    rows=[{'id':f.frame_id,'range':f.source_range,'text':text[slice(*f.source_range)],
        'anchor':f.anchor_span,'construction':f.construction,
        'blocked':f.semantic.get('structural_unresolved',False),
        'uncovered':f.semantic.get('uncovered_token_refs',[]),
        'gap_roles':list(f.semantic.get('implicit_arguments',{})),
        'missing_roles':f.semantic.get('missing_required_roles',[]),
        'questions':f.semantic.get('component_questions',[])} for f in state.frames]
    report={'mode':'GENERATOR_INVENTORY_NO_MODEL_ALL_PROBES_INSUFFICIENT',
        'source_sha256':source_hash,'resource_sha256':release.sha256,
        'seconds':monotonic()-start,'tokens':len(state.evidence),'frames':len(rows),
        'composed':sum(r['construction']=='COMPONENTS_V1' for r in rows),
        'complete_composed':sum(r['construction']=='COMPONENTS_V1' and not r['blocked'] for r in rows),
        'prepositional_questions':sum(q['kind']=='RELATION_TO_EVENT' for r in rows for q in r['questions']),
        'missing_role_questions':sum(q['kind']=='MISSING_REQUIRED_ROLE' for r in rows for q in r['questions']),
        'probe_requests':len(selector.prompts),
        'diagnostics':dict(Counter(d.code for d in state.diagnostics))}
    for name,value in [('inventory',report),('frames',rows),('prompts',selector.prompts),('resource_manifest',release.manifest)]:
        (args.out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=='__main__': raise SystemExit(main())
