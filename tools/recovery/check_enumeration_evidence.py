"""Actual closed selector: all page evidence must remain usable at closure/use."""
from copy import deepcopy
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.regions import TextRegion
from ah.formalizer.structural_tasks import choose,choose_domain,licensed
from ah.formalizer.component_probe_replay import supersede
from ah.formalizer.selection_domains import valid,valid_frozen
from ah.formalizer.partial_readings import valid_domain

release=NS(sha256='release',entries=lambda k:[{'max_rule_steps':100}])
cfg={'max_candidates':1,'context_chars':2000}
options=[{'candidate_id':c,'label':'reading '+c} for c in 'ab']
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,*answers):self.answers=iter(answers);self.count=0;self.hook=None
    def select(self,prompt):
        self.count+=1
        if self.hook:self.hook(self.count)
        return next(self.answers)
def fixture():
    s=t0('source');s.evidence=[TokenEvidence('source','t',0,6)]
    return s,TextRegion('r','SENTENCE',(0,6),('t',),None)
def task(s,r,sel,opts=options):
    return choose(s,release,sel,r,cfg,'custom',opts,'Which?',empty={'candidate_id':'DONE','label':'no remaining candidate'})
def domain(s,p):return next(r for r in reversed(s.syntax_trace) if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==p['domain_ref'])

# Positive singleton and EMPTY depend equally on every accepted/rejected page.
for answers in [('0','0'),('1','0')]:
    for page_index in [0,1]:
        s,r=fixture();value,proof=task(s,r,Selector(*answers));row=domain(s,proof)
        assert licensed(s,proof) and valid(s,row)
        independent=choose(s,release,Selector('1'),r,cfg,'other',options[:1],'Independent?')
        page=row['page_refs'][page_index];supersede(s,page,'replacement')
        assert not licensed(s,proof) and not valid(s,row)
        assert licensed(s,independent[1])
# Replacement at the same address must not resurrect old completion.
s,r=fixture();_,p=task(s,r,Selector('0','0'));row=domain(s,p)
s.decisions[row['page_refs'][0]].selected=('a',)
assert not licensed(s,p)
# Retirement while the last page is executing prevents publication at all.
s,r=fixture();sel=Selector('0','0')
def retire(n):
    if n==2:
        first=next(x['decision_ref'] for x in s.syntax_trace if x.get('kind')=='STRUCTURAL_TASK' and x.get('page')==0)
        supersede(s,first,'replacement')
sel.hook=retire
assert task(s,r,sel) is None
assert s.syntax_trace[-1]['reason']=='ENUMERATION_EVIDENCE_CHANGED'
# Empty iterator is exhaustion of zero candidates; not language-domain closure.
s,r=fixture();_,p=task(s,r,Selector(),[])
assert licensed(s,p) and not domain(s,p)['interpretation_complete']
# Altering any page outcome invalidates retained alternatives and frozen offers.
s,r=fixture();d=choose_domain(s,release,Selector('1','1'),r,cfg,'custom',options,'Which?')
assert valid_domain(s,d.record());row=domain(s,{'domain_ref':d.domain_ref})
frozen={'syntax_trace':deepcopy(s.syntax_trace),'component_probe_records':deepcopy(s.component_probe_records)}
assert valid_frozen(frozen,row)
frozen['component_probe_records'][row['page_refs'][0]]['superseded_by']='replacement'
assert not valid_frozen(frozen,row)
s.decisions[row['page_refs'][1]].selected=()
assert not valid_domain(s,d.record())
print('Enumeration evidence: EMPTY/positive/retained/frozen outcomes, in-flight retirement, same-address mutation and independent domains: PASS')

# No compatibility bypass for a selected row lacking its enumeration witness.
s,r=fixture();_,p=task(s,r,Selector('0','0'))
s.syntax_trace[:]=[row for row in s.syntax_trace if not (row.get('kind')=='TASK_DOMAIN' and row['task_ref']==p['domain_ref'])]
p.pop('selection_purpose')
assert not licensed(s,p)
print('Missing domain evidence cannot be bypassed by a legacy untyped proof: PASS')
