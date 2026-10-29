"""Controlled helper-level witnesses; not an executor or end-to-end run.
Run from repo root with PYTHONPATH=src (plus project dependencies).
"""
import json
from types import SimpleNamespace as NS
from unittest.mock import patch
from ah.formalizer import function_inventory as inv
from ah.formalizer import nominal_functions as nominal
from ah.formalizer import temporal_functions as temporal
from ah.formalizer.component_probe_replay import supersede
from ah.formalizer.structural_tasks import licensed
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.composition_session import CompositionSession

state=NS(syntax_trace=[], decisions={}, component_probe_records={},clarification_candidates=[])
tokens=[NS(token_id='t1')]
version=['A']
runtime=NS(input_signature=lambda:version[0],context_signature=lambda:'context',domain_feedback=None)
with patch('ah.formalizer.composition_session.current',return_value=runtime):
    metadata=inv.begin(state,'NOMINAL',tokens)
    inv.complete(state,metadata)
    version[0]='B'
    mismatch={'old_signature':metadata['inventory_signature'],
              'current_signature':inv.identity(state,'NOMINAL',tokens)[2],
              'prepared_after_input_change':nominal.prepared(state,tokens)}
    assert mismatch['old_signature']!=mismatch['current_signature']
    assert mismatch['prepared_after_input_change'] is True
    assert inv.begin(state,'NOMINAL',tokens) is not None

# A previously valid structural proof is explicitly retired. The source and
# input signature stay unchanged; neither rows nor the inventory notices it.
state.syntax_trace=[]
candidate={'candidate_id':'c1'}
proof={'decision_ref':'p1','candidate_id':'c1','payload_hash':digest(candidate)}
state.decisions['p1']=NS(outcome=None,selected=('c1',),candidates=('c1',),
                        grounds=[NS(value='c1')],search_complete=True)
state.component_probe_records['p1']={}
state.syntax_trace.append({'kind':'STRUCTURAL_TASK','decision_ref':'p1','selected':'c1',
  'enumeration_complete':True,'payload_hash':digest(candidate),'alternatives':[candidate]})
assert licensed(state,proof)
for kind in ('NOMINAL','TEMPORAL'):
    metadata=inv.begin(state,kind,tokens)
    state.syntax_trace.append({**metadata,'kind':kind+'_FUNCTION','unit_ref':kind,
      'anchor_refs':['t1'],'token_refs':['t1'],'function':'REFERENCE','proofs':[proof]})
    inv.complete(state,metadata)
supersede(state,'p1','p2')
retired={'proof_licensed_after_retirement':licensed(state,proof),
         'nominal_inventory_reused':inv.begin(state,'NOMINAL',tokens) is None,
         'temporal_inventory_reused':inv.begin(state,'TEMPORAL',tokens) is None,
         'nominal_rows_returned':len(nominal.rows(state,tokens)),
         'temporal_units_returned':len(temporal.units(state,['t1']))}
assert retired=={'proof_licensed_after_retirement':False,'nominal_inventory_reused':True,
 'temporal_inventory_reused':True,'nominal_rows_returned':1,'temporal_units_returned':1}
# The reader is configured, but singleton exits before any memory work.
class NeverRead:
    def read(self,*args,**kwargs):raise AssertionError('reader unexpectedly called')
singleton_memory=CompositionSession.memory(NS(reader=NeverRead()),'nominal_attachment',
                                           [{'candidate_id':'c1'}],(0,1),{})
assert singleton_memory==''
print(json.dumps({'kind':'CONTROLLED_HELPER_WITNESSES','changed_inputs':mismatch,
 'retired_proof':retired,'singleton_memory':singleton_memory,
 'limits':'No live model, no full dispatcher schedule, no GUI, no durable write.'},ensure_ascii=False,indent=2))
