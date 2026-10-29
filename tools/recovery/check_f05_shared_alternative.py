"""Scenario execution of source-sharing OR; no live model."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds
steps=relation('OR')+bounds('structural_operand_1','Иван','Иван')+bounds('structural_operand_2','Пётр','придёт')+[
    ('structural_shared_material','Some wording')]+bounds('structural_shared_source','придёт','придёт')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')+relation('LEXICAL')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Иван или Пётр придёт.',steps)
    assert not result['diagnostics']['codes'],result['diagnostics']
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['operator']=='OR',facts
    branches=facts[0]['operands']
    assert len(branches)==2 and {b['predicate'] for b in branches}=={'ARRIVE'},branches
    assert {b['roles']['AGENT']['entity'] for b in branches}=={'ivan','petr'},branches
    print('PASS: one OR assertion, two distinct participants, shared ARRIVE predicate; no jointly asserted group')

def joint(first,last):
    return [('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members',first,first)+[
        ('nominal_coordination_members_continue','Another piece starts at «'+last+'»'),
        ('nominal_coordination_members_piece_end','End after «'+last+'»'),
        ('nominal_coordination_members_continue','0'),
        ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
        ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0')]
steps=relation('OR')+bounds('structural_operand_1','Иван','Мария')+bounds('structural_operand_2','Пётр','придут')+[
    ('structural_shared_material','Some wording')]+bounds('structural_shared_source','придут','придут')+[
    ('structural_partition','PARTITION')]+relation('LEXICAL')+joint('Иван','Мария')+relation('LEXICAL')+joint('Пётр','Анна')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Иван и Мария или Пётр и Анна придут.',steps)
    assert not result['diagnostics']['codes'],result['diagnostics']
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['operator']=='OR',facts
    assert len(facts[0]['operands'])==2,facts
    assert all(b['predicate']=='ARRIVE' for b in facts[0]['operands']),facts
    groups=[b['roles']['AGENT']['group'] for b in facts[0]['operands']]
    assert all(len(group)==2 for group in groups),groups
    assert {m.get('entity') for m in groups[0]}=={'ivan','maria'},groups
    assert any(m.get('entity')=='petr' for m in groups[1]),groups
    print('PASS: alternatives of coordinated participant groups retain OR above two ARRIVE propositions:',facts)

# Real proofs must license sharing; mere repeated token IDs do not suffice.
from types import SimpleNamespace as NS
from copy import deepcopy
from ah.formalizer.pipeline import t0
from ah.formalizer.regions import TextRegion
from ah.formalizer.shared_proposition_material import propose,validate
from ah.formalizer.component_probe_replay import supersede
s=t0('Иван Пётр придёт');tokens=s.evidence
region=TextRegion('r','SENTENCE',(0,len(s.text)),tuple(t.token_id for t in tokens),None)
answers=iter(['1','3','1','0'])
domain=NS(state=s,release=NS(sha256='release',entries=lambda k:[{'max_rule_steps':100}]),
          selector=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda p:next(answers)),
          region=region,tokens=tokens,cfg={'max_candidates':8,'context_chars':2000},kind='OR')
expanded,witness=propose(domain,[[tokens[0]],[tokens[1],tokens[2]]])
assert validate(s,expanded,witness)
assert not validate(s,expanded,None)
assert not validate(s,[[tokens[2]],expanded[1]],witness)
assert not validate(s,[expanded[0],expanded[1][:-1]],witness)
supersede(s,witness['scope_proof']['decision_ref'],'replacement')
assert not validate(s,expanded,witness)
print('PASS: undeclared overlap, empty distinct branch, lost shared occurrence and revoked sharing are rejected')

# An operator outside the alternatives must keep its original scope.
steps=relation('NOT')+bounds('structural_introducer','Неверно','что')+[('structural_partition','PARTITION')]+relation('OR')+bounds('structural_operand_1','Иван','Иван')+bounds('structural_operand_2','Пётр','придёт')+[('structural_shared_material','Some wording')]+bounds('structural_shared_source','придёт','придёт')+[('structural_partition','PARTITION')]+relation('LEXICAL')+relation('LEXICAL')
with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
    result,script=run(Path(tmp),patch,'Неверно что Иван или Пётр придёт.',steps)
    assert not result['diagnostics']['codes'],result['diagnostics']
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['operator']=='NOT',facts
    alternative=facts[0]['operands'][0]
    assert alternative['operator']=='OR' and len(alternative['operands'])==2,facts
    assert all(b['predicate']=='ARRIVE' for b in alternative['operands']),facts
    print('PASS: outer NOT remains above OR, not duplicated inside the branches')
