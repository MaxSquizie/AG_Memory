"""Controlled checks of complete boundary reachability and lexical obligations."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from pytest import MonkeyPatch
import re
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session

calls=[];relations=0
def generate(self,prompt,**kwargs):
    global relations
    slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
    calls.append((slot,str(prompt)))
    if slot=='structural_relation':
        relations+=1;return '1' if relations==1 else '?'
    if slot=='infinitive_head':return '1'
    if slot=='infinitive_content_end':
        return next(n for n,label in re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
                    if label.startswith('End after «принтер»'))
    if slot=='infinitive_content_continue':return '0'
    return '?'

text='Я попросил Диму починить принтер но он ушёл.'
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    patch.setattr(ChatBackend,'generate',generate)
    payload={'raw_input':{'text':text,'source_id':'boundary-contract','revision':1,'range':[0,len(text)],
                         'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    result=execute_native(Session([payload],Path(tmp)/'j'),payload,
        {'provider':'lmstudio','model':'controlled-contract','structure_mode':'region_probes'})
ir=result['runtime']['ir'];by_id={e['token_id']:e['span'] for e in ir['evidence']}
row=next(r for r in ir['syntax_trace'] if r.get('kind')=='INFINITIVE_BOUNDARY')
assert [by_id[t] for t in row['content_token_refs']]==['починить','принтер']
assert not result['assertions']['ah']

from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.composition_contracts import LexicalRoute,conflicts
from ah.formalizer.structural_tasks import choose
from ah.formalizer.selection_labels import PROTOCOL_VERSION
state=t0('Иван пришёл и Пётр ушёл')
region=SimpleNamespace(region_id='contract',source_range=(0,len(state.text)),
    token_refs=tuple(t.token_id for t in state.evidence),grounds=())
release=SimpleNamespace(sha256='contract',entries=lambda k:[{}])
selector=SimpleNamespace(selection_reply_format=PROTOCOL_VERSION,select=lambda p:'1')
option,proof=choose(state,release,selector,region,{'context_chars':1000,'max_candidates':10},
    'structural_relation',[{'candidate_id':'LEXICAL','relation':'LEXICAL','label':'One lexical predication',
                           'region_ref':region.region_id,'token_refs':list(region.token_refs),
                           'source_uid':state.source_uid,
                           'input_scope':None}],
    'Which relation?')
route=LexicalRoute(region.region_id,region.token_refs,proof,state.interpretation_version)
route.validate(state,region,state.evidence)
state.interpretation_version+=1
try:route.validate(state,region,state.evidence)
except ValueError as exc:assert str(exc)=='LEXICAL_ROUTE_UNGROUNDED'
else:raise AssertionError('old execution route accepted')
state.interpretation_version-=1
left=FrameCandidate('left','FLAT','пришёл',(),predicate_token_ref=state.evidence[1].token_id)
right=FrameCandidate('right','FLAT','ушёл',(),predicate_token_ref=state.evidence[-1].token_id,
    semantic={'component_child':True})
assert route.accept(state,region,[left])
left.semantic['component_scope_tree']={'operator':'AND','operands':[{'frame_ref':'left'},{'frame_ref':'right'}]}
left.semantic['partial_composition']={'tree':left.semantic['component_scope_tree']}
assert not route.accept(state,region,[left,right])
assert all(f.semantic['structural_unresolved'] for f in [left,right])
from ah.formalizer.composition_tree import roots
assert not roots([left,right])
assert len(conflicts(state,region,0))==1
changed=SimpleNamespace(**{**region.__dict__,'region_id':'other'})
try:route.validate(state,changed,state.evidence)
except ValueError as exc:assert str(exc)=='LEXICAL_ROUTE_UNGROUNDED'
else:raise AssertionError('changed route address accepted')
print('PASS: boundary before connective reachable; unknown parent not written; lexical route rejects nested relation and changed address')

# A rejected proposal is addressed evidence, not exhaustion of all partitions.
# Repeating exactly that proposal with unchanged input must not ask again.
from ah.formalizer.relation_composition import confirm_partition
from ah.formalizer.structural_tasks import licensed
from ah.formalizer.component_probe_replay import supersede
state=t0('Иван пришёл и Пётр ушёл')
counter=[]
def select(prompt):
    slot=re.search(r'Decision slot: (\S+)',prompt).group(1);counter.append(slot)
    return '0' if slot=='structural_partition' else '1'
selector.select=select
_,proof=choose(state,release,selector,region,{'context_chars':1000,'max_candidates':10},
    'structural_relation',[{'candidate_id':'AND','relation':'AND','label':'Conjunction',
                           'region_ref':region.region_id,'token_refs':list(region.token_refs)}],
    'Which relation?')
groups=[state.evidence[:2],state.evidence[3:]]
args=(state,release,selector,region,state.evidence,{'context_chars':1000,'max_candidates':10},'AND',groups,proof)
assert confirm_partition(*args) is None
failure=next(r for r in state.syntax_trace if r.get('kind')=='COMPOSITION_OBLIGATION_FAILURE')
assert failure['category']=='PARTITION_REJECTED' and failure['search_complete'] is False
assert failure['owner_proof']==proof
before=len(counter)
assert confirm_partition(*args) is None
assert len(counter)==before and state.diagnostics[-1].code=='STRUCTURAL_REVISION_NO_PROGRESS'
assert licensed(state,proof)
supersede(state,proof['decision_ref'],'replacement')
assert not licensed(state,proof)
print('PASS: rejected split retains owner and limited negative evidence; repeated proposal stops; superseded license rejected')
