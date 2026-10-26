"""Exercise raw/replayed pages versus complete-domain offers; no live model."""
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.component_probe import _probe
from ah.formalizer.selection_labels import PROTOCOL_VERSION
from ah.formalizer.structural_tasks import choose_domain
from ah.formalizer.partial_readings import valid_domain

class Selector:
    selection_reply_format=PROTOCOL_VERSION
    def __init__(self,answers):self.answers=iter(answers);self.calls=0
    def select(self,prompt):self.calls+=1;return next(self.answers)

release=SimpleNamespace(sha256='contract',entries=lambda k:[{}])
options=[{'candidate_id':x,'label':'Meaning '+x} for x in 'abc']
for response in ('0','?','1,2'):
    state=t0('source');selector=Selector([response])
    _probe(state,selector,release,'raw-page','role',options,state.text,(0,6))
    assert not state.clarification_candidates
    _probe(state,selector,release,'raw-page','role',options,state.text,(0,6))
    assert selector.calls==1 and not state.clarification_candidates

state=t0('source');selector=Selector(['1','1'])
region=SimpleNamespace(region_id='r',token_refs=tuple(t.token_id for t in state.evidence),
                       source_range=(0,6),grounds=())
domain=choose_domain(state,release,selector,region,{'max_candidates':2,'context_chars':100},
                     'role',options,'Which meaning fits?')
assert domain and valid_domain(state,domain.record())
assert {v['candidate_id'] for v in domain.values}=={'a','c'}
assert len(state.clarification_candidates)==1
assert {v['candidate_id'] for v in state.clarification_candidates[0]['options']}=={'a','c'}

state=t0('source');selector=Selector(['0','?'])
assert choose_domain(state,release,selector,region,{'max_candidates':2,'context_chars':100},
                     'role',options,'Which meaning fits?') is None
assert not state.clarification_candidates
assert not any(r.get('kind')=='TASK_DOMAIN' for r in state.syntax_trace)
print('PASS: raw and replayed 0/?/multiple pages do not offer choices; only complete supported domain does')
