"""Joint-set completion via real source collection; no live model."""
from copy import deepcopy
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import source_set
from ah.formalizer.source_collections import valid
from ah.formalizer.component_probe_replay import supersede
release=NS(sha256='release',entries=lambda k:[{'max_rule_steps':100}])
def collect(answers,exclude=()):
    s=t0('а а а');s.evidence=[TokenEvidence('а',ref,i,i+1) for ref,i in [('a',0),('b',2),('c',4)]]
    r=TextRegion('r','SENTENCE',(0,5),('a','b','c'),None);it=iter(answers)
    sel=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:next(it))
    result=source_set(s,release,sel,r,s.evidence,{'max_candidates':8,'context_chars':2000},'part','Select expression.',exclude=exclude)
    receipt=next((row for row in reversed(s.syntax_trace) if row.get('kind')=='SOURCE_SET'),None)
    return s,result,receipt
s,result,row=collect(['1','1','2','1','0'])
assert [t.token_id for t in result[0]]==['a','c'] and valid(s,row)
assert row['completion_reason']=='NO_SUPPORTED_ADDITION' and row['multiplicity']=='COMPATIBLE_OCCURRENCES'
assert not row['search_complete'] and not row['interpretation_complete']
changed=deepcopy(row);changed['multiplicity']='ALTERNATIVE_READINGS'
assert not valid(s,changed)
completion=row['completion_proof']
domain=next(r for r in s.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==completion['domain_ref'])
supersede(s,domain['page_refs'][0],'replacement')
assert not valid(s,row)
s,result,row=collect(['1','3'])
assert valid(s,row) and row['completion_reason']=='ALL_AVAILABLE_OCCURRENCES' and row['completion_proof'] is None
s,result,row=collect(['1','1'],exclude=('b','c'))
assert valid(s,row) and row['selected_refs']==('a',) and row['excluded_refs']==('b','c')
# Two candidate starts are alternative sets; never unioned into one collected set.
s,result,row=collect(['1,2'])
assert result is None and row is None
print('Source collection: discontinuity, exhausted/negative completion, exclusions, alternative starts and retired completion: PASS')
