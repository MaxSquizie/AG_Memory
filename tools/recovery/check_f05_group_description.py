"""Scripted native group-description projection with original membership proof."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds

def group():
    return [('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members','Иван','Иван')+[
        ('nominal_coordination_members_continue','Another piece starts at «Мария»'),
        ('nominal_coordination_members_piece_end','End after «Мария»'),('nominal_coordination_members_continue','0'),
        ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
        ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0')]
steps=relation('NOMINAL_DESCRIPTION')+bounds('structural_description','Прочитавшие','книгу')+[
    ('structural_description_binding','The nominal host fills')]+relation('LEXICAL')+group()+[
    ('nominal_attachment','WHOLE established group'),('structural_description_role','SUBJECT')]+relation('LEXICAL')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Прочитавшие книгу Иван и Мария спят.',steps)
    print(result['diagnostics'],result['assertions']['ah'])

    assert not result['diagnostics']['codes'],result['diagnostics']
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['predicate']=='SLEEP',facts
    assert {m['entity'] for m in facts[0]['roles']['AGENT']['group']}=={'ivan','maria'},facts
    frames=result['runtime']['ir']['frames']
    projected=[f for f in frames if f['semantic'].get('refinement_binding',{}).get('host_member_refs')]
    assert projected,frames
    import json
    def dictionaries(value):
        if isinstance(value,dict):
            yield value
            for v in value.values():yield from dictionaries(v)
        elif isinstance(value,list):
            for v in value:yield from dictionaries(v)
    records=[json.loads(line) for line in (Path(tmp)/'journal.log').read_text().splitlines()]
    links=[v for r in records for v in dictionaries(r) if v.get('kind')=='NOMINAL' and 'host_ref' in v]
    assert links and all(v['host_ref'].startswith('K:') for v in links),links
    assert all(f['semantic']['nominal_groups'][0]['marker_refs'] for f in projected)
print('PASS: complete group is a bound-description host; original connector proof survives native write')
