"""Parent input projection and final prompt guards, using scripted selection."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.composition_tree import InputSlot
from ah.formalizer.composition_session import CompositionSession
from ah.formalizer.component_probe import _probe

s=t0('Иван сказал он придёт')
s.evidence=[TokenEvidence(w,ref,a,b) for w,ref,a,b in
    [('Иван','a',0,4),('сказал','p',5,11),('он','c',12,14),('придёт','d',15,21)]]
release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
runtime=CompositionSession(s,release)
r=TextRegion('parent','SENTENCE',(0,11),('a','p'),None)
request=InputSlot(proposition_slots={'p':{'OBJECT':{'tree':{'frame_ref':'child'},'attitude':'QUOTED'}}},
    proposition_sources={'p':{'OBJECT':('c','d')}})
seen=[];selector=SimpleNamespace(selection_reply_format='SELECT_LABELS_V1',select=lambda p:seen.append(str(p)) or '1')
options=[{'candidate_id':'one','label':'Parent interpretation'}]
with runtime.area(r,s.evidence[:2],request),patch('ah.formalizer.composition_session.current',return_value=runtime),\
     patch('ah.formalizer.component_policy.policy',return_value={'max_candidates':8,'context_chars':2000}):
    assert not runtime.input_errors()
    assert _probe(s,selector,release,'parent','predicate_function',options,s.text[:11],r.source_range,
        question='Which predicate?')=='one'
assert '«сказал» @5' in seen[0] and '«придёт» @15' in seen[0]
assert 'not an omitted slot to discover' in seen[0] and 'Status: QUOTED' in seen[0]
for bad,code in [(replace(request,proposition_sources=None),'SUPPLIED_CONTENT_SOURCE_UNAVAILABLE'),
                 (replace(request,head_ref='missing'),'PARENT_HEAD_UNAVAILABLE')]:
    with runtime.area(r,s.evidence[:2],bad),patch('ah.formalizer.composition_session.current',return_value=runtime):
        assert code in runtime.input_errors()
        assert _probe(s,selector,release,'parent','predicate_function',options,s.text[:11],r.source_range,
            question='Which predicate?') is None
assert len(seen)==1,'invalid parent input must not reuse or call a selector'
with runtime.area(r,s.evidence[:2],InputSlot(inside_attitude=True)):
    assert 'does not independently assert' in runtime.input_question('relative_marker_reading')
print('Parent inputs: exact supplied content/owner/role in final prompt; missing sources/head block replay; nested status retained: PASS')
