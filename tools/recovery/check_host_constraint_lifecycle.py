"""Real host producer and later context projection on authored responses."""
from types import SimpleNamespace as NS
from unittest.mock import patch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.component_nominal_questions import select_hosts
from ah.formalizer.component_constraints import question,frame_hosts_live
from ah.formalizer.component_probe_replay import supersede
s=t0('видит дом у реки')
s.evidence=[TokenEvidence(word,ref,a,b) for word,ref,a,b in [('видит','p',0,5),('дом','n',6,9),('у','m',10,11),('реки','h',12,16)]]
r=TextRegion('r','SENTENCE',(0,16),('p','n','m','h'),None)
f=NS(predicate_token_ref='p',argument_token_refs=('n',),semantic={'proposed_roles':{'n':'OBJECT'}})
u={'token':s.evidence[2],'entities':[(s.evidence[3],None)],'refs':('m','h'),'adjectives':[]}
release=NS(sha256='release',entries=lambda k:[{'max_rule_steps':100}])
sel=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:'1')
assert select_hosts(s,release,sel,r,[u],f,{'max_candidates':8})=={'h':'EVENT'}
assert 'у реки' in question(s,r) and frame_hosts_live(s,f)
with patch('ah.formalizer.composition_session.current',return_value=NS(input_signature=lambda:'another-parent')):
    assert question(s,r)==''
key=f.semantic['nominal_host_evidence'][0]['decision_ref'];supersede(s,key,'replacement')
assert question(s,r)=='' and not frame_hosts_live(s,f)
print('Host producer/context/snapshot: live address retained; other parent and retired choice excluded: PASS')
