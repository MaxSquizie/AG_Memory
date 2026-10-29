"""Actual probe dependencies and inventory consumers; no model quality claim."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.composition_dispatcher import Dispatcher
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose
from ah.formalizer.component_probe_replay import supersede
from ah.formalizer import function_inventory as inv,nominal_functions as nominal,temporal_functions as temporal
from ah.formalizer.component_phrases import prepositional_groups
release=NS(sha256='release',entries=lambda k:[{'max_rule_steps':100}])
cfg={'max_candidates':1,'context_chars':2000}
def fixture(kind):
    s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)]
    r=TextRegion('r','SENTENCE',(0,6),('t',),None)
    select=lambda answer:NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:answer)
    positive=choose(s,release,select('1'),r,cfg,'custom',[{'candidate_id':'x','label':'function'}],'Which?')
    negative=choose(s,release,select('0'),r,cfg,'custom',[{'candidate_id':'y','label':'more'}],'More?',empty={'candidate_id':'DONE','label':'no more'})
    metadata=inv.begin(s,kind,s.evidence,'constraints-A')
    row={**metadata,'kind':kind+'_FUNCTION','unit_ref':'unit','function':'REFERENCE',
        'anchor_refs':['t'],'token_refs':['t'],'proofs':[positive[1]],'source_range':[0,6]}
    s.syntax_trace.append(row)
    assert inv.complete(s,metadata,negative[1])
    return s,r,row,positive,negative
for kind in ('NOMINAL','TEMPORAL'):
    for which in ('positive','negative'):
        s,r,row,pos,neg=fixture(kind)
        assert inv.current(s,kind,s.evidence,'constraints-A')
        assert inv.current(s,kind,s.evidence,'constraints-B') is None
        assert inv.unit_live(s,deepcopy(row))
        frame=NS(semantic={'function_inventory_refs':[row['inventory_ref']],
            'temporal_functions':[deepcopy(row)] if kind=='TEMPORAL' else []})
        assert inv.frame_live(s,frame)
        proof=(pos if which=='positive' else neg)[1]
        domain=next(x for x in s.syntax_trace if x.get('kind')=='TASK_DOMAIN' and x['task_ref']==proof['domain_ref'])
        supersede(s,domain['page_refs'][0],'replacement')
        assert not inv.frame_live(s,frame) and not inv.unit_live(s,row)
        assert inv.begin(s,kind,s.evidence,'constraints-A') is not None
        if kind=='NOMINAL':
            assert not nominal.prepared(s,s.evidence,'constraints-A') and not nominal.rows(s,s.evidence)
            try:prepositional_groups(s.evidence,state=s,constraints='constraints-A')
            except inv.InventoryUnavailable:pass
            else:raise AssertionError('stale inventory fell back to lexical rules')
        else:
            assert not temporal.units(s,['t']) and not temporal.owned_refs(s,s.evidence)
            assert temporal.normalize(s,release,frame.semantic['temporal_functions'][0])==(None,['FUNCTION_INVENTORY_UNRESOLVED'])
# A copied unit cannot remain valid just because it lacks the mutated retired flag.
s,r,row,pos,neg=fixture('NOMINAL');copy=deepcopy(row)
assert nominal.prepared(s,s.evidence,'constraints-A') and not nominal.prepared(s,s.evidence)
row['function']='QUANTITY'
assert not inv.unit_live(s,copy) and not inv.current(s,'NOMINAL',s.evidence,'constraints-A')
# Returning from a child changes current input identity; it does not retire the
# child's already licensed receipt in a parent snapshot.
s,r,row,pos,neg=fixture('TEMPORAL')
with patch('ah.formalizer.composition_session.current',return_value=NS(input_signature=lambda:'parent',context_signature=lambda:'context',domain_feedback=None,
        dispatcher=Dispatcher(s))):
    assert inv.unit_live(s,row) and inv.current(s,'TEMPORAL',s.evidence,'constraints-A') is None
print('Inventories: exact constraints, positive/negative retirement, copied units, no lexical fallback, parent vs child identity: PASS')
