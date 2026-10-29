"""Actual nominal-function producer, controlled answers, no language oracle."""
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.nominal_functions import prepare,rows
from ah.formalizer.structural_tasks import licensed
s=t0('два дома');s.evidence=[TokenEvidence('два','q',0,3),TokenEvidence('дома','n',4,8)]
r=TextRegion('r','SENTENCE',(0,8),('q','n'),None)
release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
answers=iter(['3','1','1','0','2','1','0']);seen=[]
selector=SimpleNamespace(selection_reply_format='SELECT_LABELS_V1',select=lambda p:seen.append(str(p)) or next(answers))
assert prepare(s,release,selector,r,s.evidence,{'max_candidates':8,'context_chars':4000})
row=rows(s,s.evidence)[0]
assert row['external_case']=='nom' and row['head_ref']=='n' and row['function_refs']==['q']
prompt=next(p for p in seen if 'Decision slot: nominal_external_case' in p)
assert '«два» @0' in prompt and '«дома» @4' in prompt
assert row['case_proof'] in row['proofs'] and licensed(s,row['case_proof'])
s.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':row['decision_ref']})
assert not licensed(s,row['case_proof'])
print('Actual nominal chain: exact quantity/head in case prompt; case proof retained; source-function retirement invalidates it: PASS')
