"""Real reference probe/codec over constructed frames; no live-model claim."""
from types import SimpleNamespace as NS
from copy import deepcopy
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate,Decision,Ground
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.nominal_reference_local import rows
from ah.formalizer.nominal_reference_memory import resolve,attach
from ah.formalizer.nominal_reference_binding import payload,validate
s=t0('Здесь это место там')
from ah.formalizer.regions import build_regions
s.region_forest=build_regions(s.text,s.evidence,s.source_uid)
a,target,noun,later=s.evidence
constraint={'head_ref':noun.token_id,'anchor_refs':[target.token_id,noun.token_id],
            'decision_ref':'nominal','source_range':[target.start,noun.end],
            'raw':s.text[target.start:noun.end],'identity_constraint':'SAME'}
unit={'mention_ref':noun.token_id,'reference_constraint':constraint}
frames=[]
for i,token in enumerate([a,later]):
    place={'anchor_ref':token.token_id,'source_tag':[s.source_uid,s.interpretation_version],
           'source_range':[token.start,token.end],'raw':token.span,'rule_id':'source',
           'resource_sha256':'release','location_kind':'LOCATION','coordinates_status':'UNKNOWN'}
    place['entity_ref']='M:place:'+digest(place)
    f=FrameCandidate('f'+str(i),'FLAT',token.span,(),predicate_token_ref=token.token_id,
        source_range=(0,len(s.text)),semantic={'candidate_specs':{'value':{'sense_id':'S','roles':{}}},
        'spatial_slots':{'place':{'rule':{'kind':'ANCHOR','sense_id':None,'generic':True,'role_id':'LOCATION'},
                                'mention_ref':token.token_id,'selected_place':place}}})
    frames.append(f)
    s.decisions[f.frame_id+'|predicate_value']=Decision('predicate_value',f.frame_id,('value',),selected=('value',),outcome='RESOLVED')
ref=FrameCandidate('ref','FLAT',noun.span,(),predicate_token_ref=noun.token_id,
    argument_token_refs=(noun.token_id,),source_range=(target.start,noun.end),
    semantic={'lexical_units':{noun.token_id:unit},'proposed_roles':{noun.token_id:'OBJECT'}})
s.frames=[*frames,ref];s.structural_closed=True
r=rows(s,constraint)
assert {x['local_anchor_ref'] for x in r}=={a.token_id,later.token_id},r
assert not rows(s,{**constraint,'anchor_refs':[a.token_id,later.token_id,noun.token_id]})
release=NS(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
answers=[]
selector=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:answers.append(prompt) or '2')
# Missing memory read must not masquerade as a complete union with local rows.
resolve(s,release,selector)
assert not answers and not s.observation['nominal_reference_bindings']
assert s.has_diag('NOMINAL_REFERENCE_SEARCH_INCOMPLETE')
request={'decision_ref':'nominal|referent'}
attach(s,request,{'rows':[],'scope':'ACTIVE_WORKSPACE','search_incomplete':False})
resolve(s,release,selector)
assert answers,[(d.code,d.detail) for d in s.diagnostics]
p=payload(s,unit)
assert p['target_ref']==r[1]['entity_ref'],(p,r)
assert 'Established source relative place' in answers[-1]
# Future/local anchor is independent and terminal; durable validation agrees.
p.update(source_tag=[s.source_uid,s.interpretation_version],mention_ref=noun.token_id)
local=p['local_spatial_anchor'];anchor=p['anchor_binding_ref']
ledger=NS(data={'bindings':{anchor:{'target_ref':p['target_ref'],'source_tag':p['source_tag'],'binding_kind':'SPATIAL_ANCHOR'}}},
          paths=lambda:(),binding_live=lambda *args:True)
store=NS(get_element_any_domain=lambda uid:NS(meta={'relative_place':{k:v for k,v in local.items() if k!='entity_ref'}}))
validate(p,ledger,NS(),store)
bad=deepcopy(p);bad['reference_constraint']['anchor_refs'].append(local['anchor_ref'])
try:validate(bad,ledger,NS(),store)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_LOCAL_ANCHOR_INVALID'
else:raise AssertionError('self anchor accepted')
# A newly changed read invalidates a previously selected LOCAL candidate too.
s.observation['nominal_reference_reads']['nominal|referent']['search_incomplete']=True
try:payload(s,unit)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_DOMAIN_STALE'
else:raise AssertionError('changed union retained')
resolve(s,release,selector)
assert not s.observation['nominal_reference_bindings']
assert not s.decisions['nominal|referent'].selected and s.decisions['nominal|referent'].outcome=='UNRESOLVED'
# Restoring the read and then retiring the selected decision cannot emit its old binding.
s.observation['nominal_reference_reads']['nominal|referent']['search_incomplete']=False
resolve(s,release,selector)
s.decisions['nominal|referent'].outcome='UNRESOLVED'
try:payload(s,unit)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_SELECTION_STALE'
else:raise AssertionError('retired selection retained')
# Each fresh negative/unknown/alternative reply withdraws the prior binding.
for reply in ['0','?','1,2']:
    s.component_probe_records.clear()
    resolve(s,release,selector)
    assert s.observation['nominal_reference_bindings']
    s.component_probe_records.clear()
    resolve(s,release,NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:reply))
    assert not s.observation['nominal_reference_bindings'],reply
s.component_probe_records.clear()
resolve(s,release,selector)
frames[1].semantic['proposed_roles']={later.token_id:'OBJECT'}
try:payload(s,unit)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_DOMAIN_STALE'
else:raise AssertionError('changed source structure retained')
del frames[1].semantic['proposed_roles']
s.decisions['f1|predicate_value'].outcome='UNRESOLVED'
try:payload(s,unit)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_DOMAIN_STALE'
else:raise AssertionError('unresolved anchor retained')
s.decisions['f1|predicate_value'].outcome='RESOLVED'
# A competing local candidate changes while the selected future anchor is intact.
resolve(s,release,selector)
s.decisions['f0|predicate_value'].outcome='UNRESOLVED'
try:payload(s,unit)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_DOMAIN_STALE'
else:raise AssertionError('changed competitor did not invalidate union')
s.decisions['f0|predicate_value'].outcome='RESOLVED'
# Retiring a page invalidates its derived parent identity too.
resolve(s,release,selector)
page=s.observation['nominal_reference_bindings'][noun.token_id]['reference_page_proofs'][0]
s.component_probe_records[page['decision_ref']]['superseded_by']='changed grounds'
try:payload(s,unit)
except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_PAGE_PROOF_STALE'
else:raise AssertionError('retired page retained parent identity')
# A source-domain change during the call cannot be published as a fresh result.
s.component_probe_records.clear()
def mutate(prompt):
    s.decisions['f0|predicate_value'].outcome='UNRESOLVED'
    return '2'
resolve(s,release,NS(selection_reply_format='SELECT_LABELS_V1',select=mutate))
assert not s.observation['nominal_reference_bindings']
assert not s.decisions['nominal|referent'].selected
s.decisions['f0|predicate_value'].outcome='RESOLVED'
# The domain owner now consumes a union beyond 32 without truncating source.
s.budget.llm_limit=1000
s.component_probe_records.clear()
s.text+=' '*2200
memory=[{'entity_ref':'M:memory:'+str(i),'memory_binding_ref':'memory-binding:'+str(i),
         'source_tag':['other',1],'label':'Previously introduced person '+str(i),
         'features':[],'reference_kind':'ENTITY','premise_support_refs':[]} for i in range(65)]
attach(s,request,{'rows':memory,'scope':'ACTIVE_WORKSPACE','search_incomplete':False})
replies=iter(['0','0','3']);calls=[]
def paged(prompt):
    calls.append(prompt)
    return next(replies)
resolve(s,release,NS(selection_reply_format='SELECT_LABELS_V1',select=paged))
assert len(calls)==3 and all(s.text in prompt for prompt in calls)
assert payload(s,unit)['target_ref']=='M:memory:64'
assert s.syntax_trace[-1]['candidate_count']==67
# Removing the reference task removes its derived binding on the next pass.
ref.semantic['lexical_units']={}
resolve(s,release,selector)
assert not s.observation['nominal_reference_bindings']
print('PASS: generic/same-clause/future anchors, missing union, live real probe, durable self exclusion, stale union/decision/competitor/page, changed domain during call, 67-row union, full long context, removed task')
