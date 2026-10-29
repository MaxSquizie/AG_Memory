"""Scripted native write of source nominal identity, not a live language oracle."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds

def reference():
    return [('nominal_function','An expression points')]+bounds('nominal_function_source','этот','этот')+[
        ('nominal_function_head','Nominal head «человек»'),
        ('nominal_identity_function','Identify the nominal'),('nominal_function','0')]
for text,first,second,children in [
    ('Иван пришёл и этот человек спит.',('Иван','пришёл'),('этот','спит'),relation('LEXICAL')+relation('LEXICAL')+reference()),
    ('студент пришёл и этот человек спит.',('студент','пришёл'),('этот','спит'),relation('LEXICAL')+relation('LEXICAL')+reference()),
    ('этот человек спит и Иван пришёл.',('этот','спит'),('Иван','пришёл'),relation('LEXICAL')+reference()+relation('LEXICAL'))]:
    steps=relation('AND')+bounds('structural_operand_1',*first)+bounds('structural_operand_2',*second)+[('structural_partition','PARTITION')]+children
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        result,script=run(Path(tmp),patch,text,steps)
        print(text,result['diagnostics'],result['assertions']['ah'])
        assert not result['diagnostics']['codes'],result['diagnostics']
        facts=result['assertions']['ah']
        atom={f['predicate']:f for f in facts if 'predicate' in f}
        assert set(atom)=={'ARRIVE','SLEEP'},facts
        assert atom['ARRIVE']['roles']['AGENT']==atom['SLEEP']['roles']['AGENT'],facts
        if 'Иван' in text:assert atom['ARRIVE']['roles']['AGENT']=={'entity':'ivan'},facts
        prompt=next(p for slot,p in script.calls if slot=='reference')
        assert 'Source participant «'+('Иван' if 'Иван' in text else 'студент')+'»' in prompt
print('PASS: earlier and later ordinary source mention produce the same identity through native write')
