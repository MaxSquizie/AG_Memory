"""Native closed-choice inventory and executable contract guards."""
import ast
from pathlib import Path
from types import SimpleNamespace
from ah.formalizer.probe_families import FAMILIES,errors
from ah.formalizer.pipeline import t0
from ah.formalizer.component_probe import _probe

sites=[]
for p in Path('src/ah/formalizer').glob('*.py'):
    tree=ast.parse(p.read_text())
    imported=set()
    for node in tree.body:
        if isinstance(node,ast.ImportFrom) and node.module=='structural_tasks':
            imported.update(a.asname or a.name for a in node.names if a.name in {'choose','choose_domain'})
    # Imports inside functions are equally valid producers.
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom) and node.module=='structural_tasks':
            imported.update(a.asname or a.name for a in node.names if a.name in {'choose','choose_domain'})
    for n in ast.walk(tree):
        if not isinstance(n,ast.Call) or not isinstance(n.func,ast.Name):continue
        name=n.func.id
        if name!='_probe' and name not in imported:continue
        idx=4 if name=='_probe' else 5
        if len(n.args)<=idx:continue
        slot=n.args[idx]
        if isinstance(slot,ast.Constant) and isinstance(slot.value,str):
            assert slot.value in FAMILIES,(p,n.lineno,slot.value)
            if name=='_probe':assert any(k.arg=='question' for k in n.keywords),(p,n.lineno,'question missing')
            sites.append((p.name,n.lineno,slot.value))
        else:
            assert p.name=='structural_tasks.py',(p,n.lineno,'unaccounted dynamic native slot')
            assert any(k.arg in {'inputs','source_selection'} for k in n.keywords),(p,n.lineno)
assert sites
state=t0('source')
options=[{'candidate_id':'a','label':'Proposed interpretation'}]
assert 'QUESTION_MISSING' in errors(state,'component_attachment',options,'source',(0,6),None)
assert 'TARGET_RANGE_INVALID' in errors(state,'component_attachment',options,'source',(0,100),'Which?')
assert 'PROBE_FAMILY_UNDECLARED' in errors(state,'undeclared_slot',options,'source',(0,6),'Which?')
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    calls=0
    def select(self,prompt):self.calls+=1;return '1'
sel=Selector();release=SimpleNamespace(sha256='r')
assert _probe(state,sel,release,'p','component_attachment',options,'source',(0,6)) is None
assert sel.calls==0
print('F04 native slot inventory:',len(sites),'literal call sites;',len({s[2] for s in sites}),'used slots;',len(FAMILIES),'registered slots; guards: PASS')

# With a declared reader, singleton must use it; cardinality is not context.
from unittest.mock import patch
from ah.formalizer.state import TokenEvidence
from ah.formalizer.composition_session import CompositionSession
state.evidence=[TokenEvidence('source','t',0,6)]
release.entries=lambda kind:[{'max_rule_steps':100}]
class Reader:
    base={'memory_hash':'fixed'}
    calls=0
    def read(self,*args):
        self.calls+=1
        return {'rows':[{'label':'source-qualified evidence'}],'proof_sem':[]}
reader=Reader();runtime=CompositionSession(state,release,reader)
with patch('ah.formalizer.context_proofs.compile_goals',return_value=[]):
    first=runtime.memory('nominal_attachment',options,(0,6),{'max_candidates':8,'context_chars':1000})
    again=runtime.memory('nominal_attachment',options,(0,6),{'max_candidates':8,'context_chars':1000})
assert reader.calls==1 and first==again and 'source-qualified evidence' in first
print('F04/F13 singleton addressed context read and unchanged-context reuse: PASS')
