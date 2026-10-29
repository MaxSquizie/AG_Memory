"""Terminal source-entity candidate and consumer contracts, no language oracle."""
from copy import deepcopy
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate,Decision
from ah.formalizer.nominal_reference_source import rows,emit_anchor,validate
from ah.formalizer.nominal_entity_plan import operations
s=t0('шмырлик шмырлик этот');a,b,target=s.evidence
frames=[]
for n,t in enumerate([a,b]):
    frame=FrameCandidate('f'+str(n),'FLAT',t.span,(),predicate_token_ref=t.token_id,
        argument_token_refs=(t.token_id,),source_range=(t.start,t.end),
        semantic={'candidate_specs':{'c':{'roles':{t.token_id:'SUBJECT'},'sense_id':None}},
                  'lexical_units':{t.token_id:{'head_ref':t.token_id,'mention_ref':t.token_id,'surface':t.span}}})
    s.decisions[frame.frame_id+'|predicate_value']=Decision('predicate_value',frame.frame_id,('c',),selected=('c',),outcome='RESOLVED')
    frames.append(frame)
s.frames=frames;constraint={'head_ref':target.token_id,'anchor_refs':[target.token_id]}
options=rows(s,constraint)
assert len(options)==2 and len({r['entity_ref'] for r in options})==2
assert all(not t.variants for t in s.evidence)  # no invented morphology for OOV
release=NS(resources={},entries=lambda k:[])
anchor=options[1]['local_nominal_anchor'];tag=anchor['source_tag'];emitted=[]
emit_anchor(s,release,anchor,tag,'frag',lambda kind,p,frag:emitted.append((kind,p)))
entity,binding=operations(s,frames[1],b.token_id,tag)
assert emitted==[('ENSURE_ENTITY',entity),('SET_IDENTITY_BINDING',binding)]
p={'local_nominal_anchor':anchor,'source_tag':tag,'target_ref':options[1]['entity_ref'],
   'anchor_binding_ref':options[1]['memory_binding_ref'],'mention_ref':target.token_id,
   'reference_constraint':constraint,'premise_support_refs':[]}
validate(p,binding)
for bad in [{**binding,'binding_kind':'NOMINAL_REFERENCE'},{**binding,'mention_ref':target.token_id}]:
    try:validate(p,bad)
    except ValueError:pass
    else:raise AssertionError('nonterminal or wrong anchor accepted')
frames[1].semantic['bound_arguments']={b.token_id:1}
assert len(rows(s,constraint))==1
try:emit_anchor(s,release,anchor,tag,'frag',lambda *a:None)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_LOCAL_ANCHOR_STALE'
else:raise AssertionError('bound variable turned into M')
del frames[1].semantic['bound_arguments']
frames[1].semantic['lexical_units'][b.token_id]['reference_constraint']={'unresolved':True}
assert len(rows(s,constraint))==1
del frames[1].semantic['lexical_units'][b.token_id]['reference_constraint']
s.decisions['f1|predicate_value'].outcome='UNRESOLVED'
assert len(rows(s,constraint))==1
assert not rows(s,{'head_ref':a.token_id,'anchor_refs':[a.token_id]})
print('PASS: repeated OOV source addresses, identical compiler operations, bound/reference exclusions, self exclusion, retired anchor')
