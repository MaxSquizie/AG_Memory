"""Real choose/codec/proof validator, authored answers; no live model or write."""
import json
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose,licensed
from ah.formalizer.component_probe_replay import supersede
state=t0('source');state.evidence=[TokenEvidence('source','t',0,6)]
release=NS(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
selector=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:'0')
value,proof=choose(state,release,selector,TextRegion('r','SENTENCE',(0,6),('t',),None),
 {'max_candidates':1,'context_chars':1000},'temporal_function',
 [{'candidate_id':'a','label':'first'},{'candidate_id':'b','label':'second'}],
 'Select the first time expression.',empty={'candidate_id':'NONE','label':'no remaining time expression'})
before=licensed(state,proof)
completion=next(r for r in state.syntax_trace if r.get('decision_ref')==proof['decision_ref'] and r.get('task_outcome')=='EMPTY')
page=completion['page_refs'][0]
supersede(state,page,'replacement')
after=licensed(state,proof)
assert before and after and state.component_probe_records[page]['superseded_by']=='replacement'
# Contrast: positive selection explicitly links its negative peer page.
s2=t0('source');s2.evidence=[TokenEvidence('source','t',0,6)]
answers=iter(['1','0'])
sel2=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:next(answers))
_,p2=choose(s2,release,sel2,TextRegion('r2','SENTENCE',(0,6),('t',),None),
 {'max_candidates':1,'context_chars':1000},'slot',
 [{'candidate_id':'a','label':'first'},{'candidate_id':'b','label':'second'}],'Which fits?')
assert licensed(s2,p2)
domain=next(r for r in s2.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==p2['domain_ref'])
supersede(s2,domain['page_refs'][1],'replacement')
assert not licensed(s2,p2)
print(json.dumps({'positive_domain_after_peer_retirement':licensed(s2,p2),'kind':'CONTROLLED_REAL_PROTOCOL_WITNESS','completion':value,
 'negative_pages':completion['page_refs'],'retired_page':page,
 'licensed_before':before,'licensed_after_retirement':after,
 'limit':'No natural-language model, GUI schedule or durable write tested.'},indent=2))
