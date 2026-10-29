"""Real omitted-participant consumer with scripted answers; no live model."""
from types import SimpleNamespace
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence,FrameCandidate
from ah.formalizer.component_participants import resolve_implicit,add_memory_options
from ah.formalizer.reference_structure import implicit_inputs

release=SimpleNamespace(sha256='r',entries=lambda kind:[{'max_rule_steps':100}])
s=t0('Пришёл. Позже объяснил, что это был Саша.')
s.evidence=[TokenEvidence('Пришёл','p',0,6)]
options=[{'candidate_id':'m','kind':'MENTION','entity_ref':'entity','mention_ref':'a',
          'anchor_label':'Саша','label':'Саша at characters 34:38'}]
gap={'gap_id':'gap','features':{},'options':options,'context_range':[0,7]}
f=FrameCandidate('f','FLAT','Пришёл',(),predicate_token_ref='p',source_range=(0,7),
    semantic={'implicit_arguments':{'SUBJECT':gap}})
s.frames=[f];s.structural_closed=True
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def select(self,prompt):
        assert 'Позже объяснил' in prompt
        assert 'omitted' in prompt and '34:38' in prompt
        return '1'
with patch('ah.formalizer.component_participants.policy',return_value={'max_candidates':8}):
    resolve_implicit(s,release,Selector())
assert s.observation['implicit_bindings']['gap']['entity_ref']=='entity'
task=implicit_inputs(s,f,'OBJECT',options)
assert 'OMITTED_ROLE_NOT_ESTABLISHED' in task.errors(s,'implicit_argument',options,f.source_range)
gap={'gap_id':'g','features':{},'options':[]}
rows=[{'entity_ref':'same','binding_ref':bid,'premise_support_refs':[bid],
       'label':'Саша','source_context':text} for bid,text in [('a','Саша говорил о плане'),('b','Саша отменил поездку')]]
with patch('ah.formalizer.component_participants.policy',return_value={'max_candidates':8}),patch('ah.formalizer.narrative_groups.add_memory'):
    add_memory_options(gap,rows,release)
assert len(gap['options'])==1
assert all(r['source_context'] in gap['options'][0]['label'] for r in rows)
assert len(gap['options'][0]['grounding_paths'])==2
print('F03 implicit later context, addressed role contract and all memory descriptions: PASS')
