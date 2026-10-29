"""Controlled recovery and abstention for addressed occurrence functions."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run, relation, bounds
from ah.formalizer.partial_readings import retired_refs


def execute(steps,text='Иван не пришёл.'):
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        result,script=run(Path(tmp),patch,text,steps)
    return result,script,result['runtime']['ir']['syntax_trace']


bad=relation('NOT')+bounds('structural_introducer','не','пришёл')+[
    ('structural_introducer_continue','0'),('relation_marker_role','«не» belongs inside')]
repair=[('structural_introducer_start','0'),('structural_marker_revision','Revise «не»')]
finish=bounds('structural_introducer','не','не')+[
    ('structural_introducer_continue','0'),('structural_partition','PARTITION')]+relation('LEXICAL')
r,s,trace=execute(bad+repair+finish)
assert r['assertions']['ah']==[{'operator':'NOT','operands':[{'predicate':'ARRIVE','roles':{'AGENT':{'entity':'ivan'}}}]}]
assert not r['diagnostics']['codes'],r['diagnostics']
revision=next(x for x in trace if x.get('kind')=='PARTITION_FUNCTION_REVISED')
assert revision['replaced_proof']['decision_ref'] in retired_refs(trace)
assert revision['revision_proof']['decision_ref'] not in retired_refs(trace)
assert sum(slot=='relation_marker_role' for slot,_ in s.calls)==1
assert any(x.get('kind')=='DISPATCH_INVALIDATED' and x.get('reason')=='PARTITION_FUNCTION_REVISED' for x in trace)
assert any(x.get('kind')=='DISPATCH_SOURCE_READ' and x.get('task_kind')=='PROBE' for x in trace)
domain=next(x for x in trace if x.get('kind')=='TASK_DOMAIN'
            and x.get('task_ref')==revision['revision_proof']['domain_ref'])
partition_reads=[{d['task_ref'] for d in x.get('dependencies',())} for x in trace
                 if x.get('kind')=='DISPATCH_COMPLETED' and x.get('task_kind')=='PARTITION']
assert any({'probe:'+ref for ref in domain['page_refs']} <= reads for reads in partition_reads)
assert not {'probe:'+ref for ref in revision['retired_refs']} & partition_reads[-1]

for answer in ('0','?'):
    r,s,trace=execute(bad+[('structural_introducer_start','0'),('structural_marker_revision',answer)])
    assert not r['assertions']['ah'] and not any(x.get('kind')=='PARTITION_FUNCTION_REVISED' for x in trace)
r,s,trace=execute(bad+[('structural_introducer_start','?')])
assert not r['assertions']['ah'] and not any(slot=='structural_marker_revision' for slot,_ in s.calls)

# Positive marker evidence survives repair of a neighbouring swallowed word.
steps=relation('NOT')+bounds('structural_introducer','не','пришёл')+[
    ('structural_introducer_continue','0'),('relation_marker_role','RELATION_ONLY'),
    ('relation_marker_role','«пришёл» belongs inside')]+finish
r,s,trace=execute(steps)
assert r['assertions']['ah'] and not r['diagnostics']['codes']
assert sum(slot=='relation_marker_role' for slot,_ in s.calls)==2
assert not any(x.get('kind')=='PARTITION_FUNCTION_REVISED' for x in trace)

# All established marker occurrences are required only at completion, not in
# each individual interval of a discontinuous source set.
steps=relation('NOT')+bounds('structural_introducer','Неверно','пришёл')+[
    ('structural_introducer_continue','0'),('relation_marker_role','RELATION_ONLY'),
    ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','«Иван» belongs inside')]+bounds(
    'structural_introducer','Неверно','Неверно')+[
    ('structural_introducer_continue','Another piece starts at «что»'),
    ('structural_introducer_piece_end','End after «что»'),('structural_introducer_continue','0'),
    ('structural_partition','PARTITION')]+relation('LEXICAL')
r,s,trace=execute(steps,'Неверно что Иван пришёл.')
assert r['assertions']['ah'] and not r['diagnostics']['codes'],r['diagnostics']
steps=relation('NOT')+bounds('structural_introducer','что','что')+[
    ('structural_introducer_continue','Another piece starts at «Неверно»'),
    ('structural_introducer_piece_end','End after «Неверно»'),('structural_introducer_continue','0'),
    ('structural_partition','PARTITION')]+relation('LEXICAL')
r,s,trace=execute(steps,'Неверно что Иван пришёл.')
assert r['assertions']['ah'] and not r['diagnostics']['codes']
continuations=[p for slot,p in s.calls if slot=='structural_introducer_continue']
assert 'Already included: «Неверно что»' in continuations[-1]
assert 'Already included: «что Неверно»' not in continuations[-1]

# A parent conjunction is not the introducer of its predicate's content.
# Repair must preserve that predicate owner, the real introducer and scope.
steps=relation('CONTENT')+[('structural_owner','Content belongs to predicate «сказал»')]+bounds('structural_content','Мария','спит')+bounds(
    'structural_parent','Иван','сказал')+[
    ('structural_parent_continue','Another piece starts at «Пётр»'),
    ('structural_parent_piece_end','End after «пришёл»'),('structural_parent_continue','0'),
    ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','«и» belongs inside')]+bounds(
    'structural_content','Мария','спит')+bounds('structural_parent','Иван','сказал')+[
    ('structural_parent_continue','Another piece starts at «и»'),
    ('structural_parent_piece_end','End after «пришёл»'),('structural_parent_continue','0'),
    ('structural_partition','PARTITION'),('structural_content_role','OBJECT:QUOTED')]+relation('AND')+bounds(
    'structural_operand_1','Иван','сказал')+bounds('structural_operand_2','Пётр','пришёл')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')*3
r,s,trace=execute(steps,'Иван сказал что Мария спит и Пётр пришёл.')
assert r['assertions']['ah'] and not r['diagnostics']['codes'],r['diagnostics']
assert sum(slot=='structural_owner' for slot,_ in s.calls)==1
assert not any(f.get('predicate')=='SLEEP' for f in r['assertions']['ah'])
questions=[p for slot,p in s.calls if slot=='relation_marker_role' and '«и»' in p and 'Outer relation: CONTENT' in p]
assert questions and all('selected content owner is «сказал»' in p and 'PARENT part' in p for p in questions)
print('PASS: addressed role revision, dependent retirement, unknown/refusal, retained positives and multi-piece markers')
