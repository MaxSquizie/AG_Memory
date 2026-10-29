"""A limited inner producer may request justified outer revision, not fallback."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds

def attempt(answer):
    return relation('LEXICAL')+[
        ('nominal_coordination_discovery','A remaining nominal group contains alternatives'),
        ('structural_revision',answer)]
outer=relation('OR')+bounds('structural_operand_1','Иван','Иван')+bounds('structural_operand_2','Пётр','придёт')+[
    ('structural_shared_material','Some wording')]+bounds('structural_shared_source','придёт','придёт')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')+relation('LEXICAL')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Иван или Пётр придёт.',attempt('REVISE')+outer)
    assert not result['diagnostics']['codes'],result['diagnostics']
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['operator']=='OR',facts
    assert {b['roles']['AGENT']['entity'] for b in facts[0]['operands']}=={'ivan','petr'}
    assert all(b['predicate']=='ARRIVE' for b in facts[0]['operands'])
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Иван или Пётр придёт.',attempt('DEFER'))
    assert not result['assertions']['ah']
    assert 'NOMINAL_COORDINATION_STRUCTURE_UNSUPPORTED' in result['diagnostics']['codes']
print('PASS: COMPLEX -> explicit revision -> source-sharing OR -> native write; DEFER keeps unsupported and writes nothing')

with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Иван или Пётр придёт.',relation('LEXICAL')+[
        ('nominal_coordination_discovery','?')])
    assert not result['assertions']['ah']
    assert all(slot!='structural_revision' for slot,_ in script.calls)
print('PASS: insufficient group evidence does not trigger a compensating guess')
