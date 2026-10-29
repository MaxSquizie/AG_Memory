"""Inspect final real requests and explicit context-budget refusal."""
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.regions import TextRegion
from ah.formalizer.state import TokenEvidence
from ah.formalizer.component_probe import _probe
from ah.formalizer.structural_tasks import choose
from ah.formalizer.component_source import probe_context

s=t0('Он придёт. Хотя нет всё отменилось')
s.evidence=[TokenEvidence('Он','a',0,2),TokenEvidence('придёт','b',3,9)]
r=TextRegion('sentence','SENTENCE',(0,10),('a','b'),None)
release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
seen=[];selector=SimpleNamespace(selection_reply_format='SELECT_LABELS_V1',select=lambda p:seen.append(str(p)) or '1')
options=[{'candidate_id':'a','label':'Proposed interpretation'}]
context,question=probe_context(s,r,{'context_chars':10},s.text[:10])
assert s.text in context
assert choose(s,release,selector,r,{'context_chars':10,'max_candidates':8},
    'structural_relation',options,'Which interpretation?') is None
assert not seen and s.syntax_trace[-1]['reason']=='CONTEXT_LIMIT'
_probe(s,selector,release,'direct','structural_relation',options,s.text[:10],r.source_range,
    question='Which interpretation of this target?')
assert len(seen)==1 and s.text in seen[0] and 'characters 0:10' in seen[0]
print('Source context: sentence boundary and small budget never silently remove later evidence; direct final prompt retains it: PASS')
