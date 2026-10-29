"""Scripted source mention edges followed by native identity propagation."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds


def conjunction(left,right):
    return relation('AND')+bounds('structural_operand_1',*left)+bounds('structural_operand_2',*right)+[('structural_partition','PARTITION')]


def reference(cue,noun='человек'):
    return [('nominal_function','An expression points')]+bounds('nominal_function_source',cue,cue)+[
        ('nominal_function_head','Nominal head «'+noun+'»'),
        ('nominal_identity_function','Identify the nominal'),('nominal_function','0')]

cases=[
    ('Иван пришёл и этот человек спит и тот человек читает книгу.',
     conjunction(('Иван','спит'),('тот','книгу'))+
     conjunction(('Иван','пришёл'),('этот','спит'))+relation('LEXICAL')+relation('LEXICAL')+reference('этот')+
     relation('LEXICAL')+reference('тот')+[
         ('reference','Source participant «Иван»'),('reference','Referent of source expression «этот человек»')]),
    ('тот человек читает книгу и Иван пришёл и этот человек спит.',
     conjunction(('тот','книгу'),('Иван','спит'))+relation('LEXICAL')+reference('тот')+
     conjunction(('Иван','пришёл'),('этот','спит'))+relation('LEXICAL')+relation('LEXICAL')+reference('этот')+[
         ('reference','Referent of source expression «этот человек»'),('reference','Source participant «Иван»')])]
group=[('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members','Иван','Иван')+[
    ('nominal_coordination_members_continue','Another piece starts at «Мария»'),
    ('nominal_coordination_members_piece_end','End after «Мария»'),('nominal_coordination_members_continue','0'),
    ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
    ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0'),
    ('component_attachment','прийти [conjugated verb]')]
cases.append(('Иван и Мария пришли и эти люди спят и те люди читают книгу.',
    conjunction(('Иван','спят'),('те','книгу'))+conjunction(('Иван','пришли'),('эти','спят'))+
    relation('LEXICAL')+group+relation('LEXICAL')+reference('эти','люди')+
    relation('LEXICAL')+reference('те','люди')+[
        ('reference','The whole established group:'),('reference','Referent of source expression «эти люди»')]))
for text,steps in cases:
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        from ah.formalizer import nominal_reference_chain as chain
        captured=[];finish=chain.finish
        def capture(state,pending):
            value=finish(state,pending);captured.append(state);return value
        patch.setattr(chain,'finish',capture)
        result,script=run(Path(tmp),patch,text,steps)
        print(text,result['diagnostics'],result['assertions']['ah'])
        assert not result['diagnostics']['codes'],result['diagnostics']
        def atoms(tree):
            if 'predicate' in tree:yield tree
            else:
                assert tree['operator']=='AND'
                for child in tree['operands']:yield from atoms(child)
        facts={f['predicate']:f for tree in result['assertions']['ah'] for f in atoms(tree)}
        assert set(facts)=={'ARRIVE','SLEEP','READ'},facts
        expected={'group':[{'entity':'ivan'},{'entity':'maria'}]} if 'Иван и Мария' in text else {'entity':'ivan'}
        assert all(f['roles']['AGENT']==expected for f in facts.values()),facts
        state=captured[-1];bindings=state.observation['nominal_reference_bindings']
        assert len(bindings)==2 and sum('local_reference_anchor' in b for b in bindings.values())==1
        derived=next(b for b in bindings.values() if 'local_reference_anchor' in b)
        parent=bindings[derived['local_reference_anchor']['mention_ref']]
        from ah.formalizer.nominal_reference_binding import payload
        unit=next(u for f in state.frames for u in f.semantic.get('lexical_units',{}).values()
                  if u.get('reference_constraint')==derived['reference_constraint'])
        assert payload(state,unit)['target_ref']==parent['target_ref']
        state.decisions[parent['interpretation_decision_ref']].outcome='UNRESOLVED'
        try:payload(state,unit)
        except ValueError as e:assert str(e)=='NOMINAL_REFERENCE_SELECTION_STALE'
        else:raise AssertionError('retired parent selection retained dependent identity')
print('PASS: source mention chain before/after dependency, native write, parent selection withdrawal')
for first_answer,code in [('Referent of source expression «тот человек»','NOMINAL_REFERENCE_DEPENDENCY_CYCLE'),
                          ('?','NOMINAL_REFERENCE_DEPENDENCY_UNRESOLVED')]:
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        from ah.formalizer import nominal_reference_chain as chain
        captured=[];finish=chain.finish
        def capture(state,pending):
            value=finish(state,pending);captured.append(state);return value
        patch.setattr(chain,'finish',capture)
        text='этот человек спит и тот человек читает книгу.'
        steps=conjunction(('этот','спит'),('тот','книгу'))+relation('LEXICAL')+reference('этот')+relation('LEXICAL')+reference('тот')+[
            ('reference',first_answer),('reference','Referent of source expression «этот человек»')]
        result,script=run(Path(tmp),patch,text,steps)
        assert code in result['diagnostics']['codes'],result['diagnostics']
        assert not captured[-1].observation['nominal_reference_bindings']
print('PASS: native mutual cycle and insufficient parent produce no grounded nominal identities')
