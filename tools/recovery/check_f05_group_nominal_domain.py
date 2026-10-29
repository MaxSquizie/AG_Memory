"""Finite K producer/ledger contracts, not a language oracle."""
from copy import deepcopy
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate,Decision
from ah.formalizer.nominal_reference_source import rows as entities
from ah.formalizer.nominal_group_source import rows,emit_anchor,validate,validate_reference
from ah.formalizer.canonical_ledger import CanonicalLedger
s=t0('шмырлик шмырлик эти');a,b,target=s.evidence
f=FrameCandidate('f','FLAT',s.text,(),predicate_token_ref=a.token_id,
    source_range=(0,len(s.text)),argument_token_refs=(a.token_id,b.token_id),semantic={
    'candidate_specs':{'c':{'roles':{a.token_id:'SUBJECT',b.token_id:'SUBJECT'},'sense_id':None}},
    'lexical_units':{t.token_id:{'mention_ref':t.token_id,'surface':t.span} for t in (a,b)},
    'nominal_groups':[{'member_refs':[a.token_id,b.token_id],'marker_refs':[],'operator':'AND','cases':None}]})
s.frames=[f];s.decisions['f|predicate_value']=Decision('predicate_value','f',('c',),selected=('c',),outcome='RESOLVED')
constraint={'head_ref':target.token_id,'anchor_refs':[target.token_id]}
assert len(entities(s,constraint))==2
r=rows(s,constraint);assert len(r)==1 and len(r[0]['member_refs'])==2
assert not any(t.variants for t in s.evidence)
assert not rows(s,{'head_ref':a.token_id,'anchor_refs':[]})
anchor=r[0]['local_group_anchor'];emitted=[]
emit_anchor(s,NS(resources={},entries=lambda k:[]),anchor,anchor['source_tag'],'frag',lambda kind,p,frag:emitted.append((kind,p)))
ledger=CanonicalLedger()
for kind,p in emitted:
    if kind=='SET_IDENTITY_BINDING':
        validate(p,ledger)
        ledger.data['bindings'][p['binding_id']]={**p,'status':'LIVE'}
group=emitted[-1][1];assert ledger.binding_live(group['binding_id'],set())
p={'local_group_anchor':anchor,'binding_kind':'NOMINAL_REFERENCE','reference_kind':'GROUP',
   'member_refs':anchor['member_refs'],'target_ref':anchor['entity_ref'],'source_tag':anchor['source_tag'],
   'reference_constraint':constraint,'anchor_binding_ref':group['binding_id'],'premise_support_refs':[]}
validate_reference(p,group)
reference={**p,'binding_id':'reference','status':'LIVE'};ledger.data['bindings']['reference']=reference
assert ledger.binding_live('reference',set())
# Member withdrawal propagates through K and the derived nominal reference.
member=anchor['member_binding_refs'][0];ledger.data['bindings'][member]['status']='RETRACTED'
assert not ledger.binding_live(group['binding_id'],set()) and not ledger.binding_live('reference',set())
try:validate(group,ledger)
except ValueError:pass
else:raise AssertionError('retired group member accepted')
ledger.data['bindings'][member]['status']='LIVE'
bad=deepcopy(p);bad['reference_constraint']['anchor_refs'].append(a.token_id)
try:validate_reference(bad,group)
except ValueError:pass
else:raise AssertionError('self-containing group accepted')
# Source role agreement/membership are obligations, not inferred from adjacency.
f.semantic['candidate_specs']['c']['roles'][b.token_id]='OBJECT'
assert not rows(s,constraint)
f.semantic['candidate_specs']['c']['roles'][b.token_id]='SUBJECT'
f.semantic['bound_arguments']={b.token_id:1}
assert not rows(s,constraint) and len(entities(s,constraint))==1
try:emit_anchor(s,NS(resources={},entries=lambda k:[]),anchor,anchor['source_tag'],'frag',lambda *a:None)
except ValueError as e:assert str(e)=='NOMINAL_GROUP_ANCHOR_STALE'
else:raise AssertionError('stale group emitted')
del f.semantic['bound_arguments']
f.semantic['nominal_groups'][0]['source_evidence']=[]
assert not rows(s,constraint)
print('PASS: repeated OOV members, individual candidates retained, whole group, self exclusion, role/binding/coordination grounds, transitive durable withdrawal')
