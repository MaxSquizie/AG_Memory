"""Native OOV binder path with scripted semantic choices, not live model evidence."""
from tempfile import TemporaryDirectory
from pathlib import Path
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds
steps=[('structural_oov_function','noun:')]+relation('FORALL')+bounds('structural_quantifier','Каждая','Каждая')+[
    ('structural_quantifier_kind','NONNUMERIC'),('quantifier_source_functions','SEPARATE'),
    ('structural_partition','PARTITION'),('structural_binder_head','Bind the participant mention at «флырка»')]+relation('LEXICAL')
with TemporaryDirectory() as temp,MonkeyPatch.context() as patch:
    result,script=run(Path(temp),patch,'Каждая флырка пришла.',steps)
    assert result['diagnostics']['codes']==['OOV_KEEP_AS_IS']
    expected={'operator':'FORALL','operands':[{'bound_var':'x'},
        {'operator':'IMPLIES','operands':[
            {'predicate':'OPEN:флырка','roles':{'AGENT':{'bound_var':'x'}}},
            {'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':'x'}}}]}]}
    assert result['assertions']['ah']==[expected]
    assert result['assertions']['ir']==[expected] and result['assertions']['journal']==[expected]
    restrictions=[f for f in result['runtime']['ir']['frames'] if f['semantic'].get('quantifier_restriction')]
    assert len(restrictions)==1
    sem=restrictions[0]['semantic'];license=sem['quantifier_restriction']
    assert license['selected_reading']==sem['morph_bindings'][license['head_ref']]
    assert license['selected_reading']['origin']=='CONTEXTUAL'
print('PASS: scripted OOV function -> nominal child -> bound restriction -> native AH/journal; open predicate and same variable retained')
