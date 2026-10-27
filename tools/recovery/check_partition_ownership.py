"""Native controlled ownership repair, including abstention and unchanged prefix.

Replies are scripted to check algorithm contracts, not model understanding.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds
from ah.formalizer.partial_readings import retired_refs


def execute(text,steps):
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        result,script=run(Path(tmp),patch,text,steps)
    return result,script,result['runtime']['ir']['syntax_trace']


bad=relation('AND')+bounds('structural_operand_1','Иван','пришёл')+[
    ('structural_operand_1_continue','Another piece starts at «Мария»'),
    ('structural_operand_1_piece_end','End after «спит»'),('structural_operand_1_continue','0')]
repair=[('structural_operand_2_start','0'),('structural_ownership_revision','Reconsider first proposition')]
finish=bounds('structural_operand_1','Иван','пришёл')+[('structural_operand_1_continue','0')]+bounds(
    'structural_operand_2','Мария','спит')+[('structural_partition','PARTITION')]+relation('LEXICAL')*2
r,s,trace=execute('Иван пришёл и Мария спит.',bad+repair+finish)
assert r['assertions']['ah'] and not r['diagnostics']['codes']
revisions=[x for x in trace if x.get('kind')=='PARTITION_OWNERSHIP_REVISED']
assert len(revisions)==1
outer=next(x for x in trace if x.get('kind')=='STRUCTURAL_TASK' and x.get('slot')=='structural_relation' and x.get('domain_ref'))
assert outer['decision_ref'] not in retired_refs(trace)
assert sum(slot=='structural_relation' for slot,_ in s.calls)==3

for answer in ('?','0'):
    steps=bad+[('structural_operand_2_start','?')] if answer=='?' else bad+[
        ('structural_operand_2_start','0'),('structural_ownership_revision','0')]
    r,s,trace=execute('Иван пришёл и Мария спит.',steps)
    assert not r['assertions']['ah']
    assert not any(x.get('kind')=='PARTITION_OWNERSHIP_REVISED' for x in trace)
    if answer=='?':assert not any(slot=='structural_ownership_revision' for slot,_ in s.calls)

r,s,trace=execute('Иван пришёл и Мария спит.',bad+repair+bad[1:]+[('structural_operand_2_start','0')])
assert not r['assertions']['ah']
assert 'STRUCTURAL_REVISION_NO_PROGRESS' in r['diagnostics']['codes']
assert sum(slot=='structural_ownership_revision' for slot,_ in s.calls)==1

steps=relation('IF_ELSE')+bounds('structural_operand_1','Иван','пришёл')+bounds(
    'structural_operand_2','Мария','спит')+[
    ('structural_operand_2_continue','Another piece starts at «Пётр»'),
    ('structural_operand_2_piece_end','End after «ушёл»'),('structural_operand_2_continue','0'),
    ('structural_operand_3_start','0'),
    ('structural_ownership_revision','Reconsider outcome when that condition holds')]+bounds(
    'structural_operand_2','Мария','спит')+bounds('structural_operand_3','Пётр','ушёл')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')*3
r,s,trace=execute('Если Иван пришёл, Мария спит, иначе Пётр ушёл.',steps)
assert r['assertions']['ah'] and not r['diagnostics']['codes']
assert sum(slot=='structural_operand_1_start' for slot,_ in s.calls)==1
revision=next(x for x in trace if x.get('kind')=='PARTITION_OWNERSHIP_REVISED')
assert revision['preserved_roles']==['condition being checked']
prefix={x['decision_ref'] for x in trace if x.get('kind')=='STRUCTURAL_TASK'
        and x.get('slot','').startswith('structural_operand_1') and x.get('decision_ref')}
assert not prefix.intersection(retired_refs(trace))
steps=relation('AND')+bounds('structural_operand_1','Иван','пришёл')+bounds(
    'structural_operand_2','спит','спит')+[
    ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','«Мария» belongs inside')]+bounds(
    'structural_operand_1','Иван','пришёл')+bounds('structural_operand_2','Мария','спит')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')*2
r,s,trace=execute('Иван пришёл и Мария спит.',steps)
assert r['assertions']['ah'] and not r['diagnostics']['codes']
questions=[p for slot,p in s.calls if slot=='structural_operand_1_end']
assert 'SOME content part' in questions[-1]
steps=relation('CONTENT')+bounds('structural_content','Мария','спит')+[
    ('structural_content_continue','Another piece starts at «Иван»'),
    ('structural_content_piece_end','End after «сказал»'),('structural_content_continue','0'),
    ('structural_parent_start','0'),('structural_ownership_revision','Reconsider dependent content')]+bounds(
    'structural_content','Мария','спит')+bounds('structural_parent','Иван','сказал')+[
    ('structural_owner','Content belongs to predicate «сказал»'),('structural_partition','PARTITION'),
    ('structural_content_role','OBJECT:QUOTED')]+relation('LEXICAL')*2
r,s,trace=execute('Иван сказал что Мария спит.',steps)
assert len(r['assertions']['ah'])==1 and not r['diagnostics']['codes']
assert r['assertions']['ah'][0].get('predicate')!='SLEEP'
assert any(x.get('kind')=='PARTITION_OWNERSHIP_REVISED' for x in trace)

# A complete rejected assignment informs its own boundary retry. The source
# start may stay unchanged; neither every boundary nor the relation is false.
steps=relation('AND')+bounds('structural_operand_1','Иван','Мария')+bounds(
    'structural_operand_2','спит','спит')+[
    ('structural_function_owner','Outer relation owns «и»'),('structural_partition','0'),
    ('structural_revision','The text supports a different')]+relation('AND')+bounds(
    'structural_operand_1','Иван','пришёл')+bounds('structural_operand_2','Мария','спит')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')*2
r,s,trace=execute('Иван пришёл и Мария спит.',steps)
assert r['assertions']['ah'] and not r['diagnostics']['codes']
starts=[p for slot,p in s.calls if slot=='structural_operand_1_start']
assert len(starts)==2 and 'Previously rejected COMBINATION' not in starts[0]
assert 'Previously rejected COMBINATION' in starts[1] and 'Start at «Иван»' in starts[1]
assert all('Previously rejected COMBINATION' not in p for slot,p in s.calls
           if slot in {'predicate_function','predicate_argument_role','component_attachment'})

from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.structural_tasks import choose,licensed
from ah.formalizer.selection_labels import PROTOCOL_VERSION
from ah.formalizer.component_probe_replay import supersede
state=t0('Иван пришёл');seen=[]
selector=SimpleNamespace(selection_reply_format=PROTOCOL_VERSION,select=lambda p:seen.append(str(p)) or '1')
release=SimpleNamespace(sha256='contract',entries=lambda k:[{}])
region=SimpleNamespace(region_id='r',source_range=(0,len(state.text)),token_refs=tuple(t.token_id for t in state.evidence),grounds=())
cfg={'context_chars':1000,'max_candidates':10,'_task_constraints':'old hypothesis','_task_constraints_text':'OLD REJECTED PARTITION'}
options=[{'candidate_id':'start','label':'Start at Иван'}]
_,old=choose(state,release,selector,region,cfg,'structural_operand_1_start',options,'Choose this boundary.')
supersede(state,old['decision_ref'],'revision-authority')
_,new=choose(state,release,selector,region,{**cfg,'_task_constraints':'new hypothesis'},'structural_operand_1_start',options,'Choose this boundary.')
assert seen[0]==seen[1] and 'OLD REJECTED PARTITION' not in seen[0]
assert old['decision_ref']!=new['decision_ref'] and not licensed(state,old) and licensed(state,new)
print('PASS: repair, abstention, no-progress, preserved prefix, global ownership, content scope and isolated revision evidence')
