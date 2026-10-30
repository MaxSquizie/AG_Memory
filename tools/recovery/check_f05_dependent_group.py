"""Scenario: source group depends on a selected reference member, then writes."""
from pathlib import Path
from copy import deepcopy
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds

def conjunction(left,right):
    return relation('AND')+bounds('structural_operand_1',*left)+bounds('structural_operand_2',*right)+[('structural_partition','PARTITION')]
def reference(cue,noun):
    return [('nominal_function','An expression points')]+bounds('nominal_function_source',cue,cue)+[
        ('nominal_function_head','Nominal head «'+noun+'»'),('nominal_identity_function','Identify the nominal'),('nominal_function','0')]
def group(second='Мария'):
    return [('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members','человек','человек')+[
        ('nominal_coordination_members_continue','Another piece starts at «'+second+'»'),
        ('nominal_coordination_members_piece_end','End after «'+second+'»'),('nominal_coordination_members_continue','0'),
        ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
        ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0')]
text='Иван пришёл и этот человек и Мария спят и эти люди читают книгу.'
steps=conjunction(('Иван','спят'),('эти','книгу'))+conjunction(('Иван','пришёл'),('этот','спят'))+relation('LEXICAL')+relation('LEXICAL')+group()+reference('этот','человек')+relation('LEXICAL')+reference('эти','люди')+[
    ('reference','Source participant «Иван»'),('reference','The whole established group of source participants')]
cases=[(text,steps),(
    'эти люди читают книгу и Иван пришёл и этот человек и Мария спят.',
    conjunction(('эти','книгу'),('Иван','спят'))+relation('LEXICAL')+reference('эти','люди')+
    conjunction(('Иван','пришёл'),('этот','спят'))+relation('LEXICAL')+relation('LEXICAL')+group()+reference('этот','человек')+[
        ('reference','The whole established group of source participants'),('reference','Source participant «Иван»')])]
cases.append((
    'Иван пришёл и Мария пришла и этот человек и та женщина спят и эти люди читают книгу.',
    conjunction(('Иван','спят'),('эти','книгу'))+
    conjunction(('Иван','пришла'),('этот','спят'))+
    conjunction(('Иван','пришёл'),('Мария','пришла'))+relation('LEXICAL')+relation('LEXICAL')+
    relation('LEXICAL')+group('женщина')+reference('этот','человек')[:-1]+reference('та','женщина')+
    relation('LEXICAL')+reference('эти','люди')+[
        ('reference','Source participant «Иван»'),('reference','Source participant «Мария»'),
        ('reference','The whole established group of source participants')]))
cases.append((cases[0][0],[(slot,'?' if slot=='reference' and label=='Source participant «Иван»' else label) for slot,label in cases[0][1]]))
for text,steps in cases:
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        from ah.formalizer import nominal_reference_chain as chain
        from ah.formalizer import nominal_reference_binding as reference_binding
        durable=[];validate=reference_binding.validate
        def capture_validation(p,ledger,journal,store=None):
            value=validate(p,ledger,journal,store)
            if p.get('local_group_anchor',{}).get('group_dependency'):
                durable.append((deepcopy(p),deepcopy(ledger)))
            return value
        patch.setattr(reference_binding,'validate',capture_validation)
        captured=[];finish=chain.finish
        def capture(state,pending):
            result=finish(state,pending);captured.append(state);return result
        patch.setattr(chain,'finish',capture)
        result,script=run(Path(tmp),patch,text,steps)
        print(result['diagnostics'],result['assertions']['ah'])
        state=captured[-1]
        if ('reference','?') in steps:
            assert not state.observation['nominal_reference_bindings']
            assert 'NOMINAL_REFERENCE_DEPENDENCY_UNRESOLVED' in result['diagnostics']['codes']
            assert not durable
            print('PASS: unknown member leaves selected group ungrounded; no group binding written')
            continue
        assert not result['diagnostics']['codes'],result['diagnostics']
        def atoms(tree):
            if 'predicate' in tree:yield tree
            else:
                for operand in tree.get('operands',[]):yield from atoms(operand)
        for fact in (f for tree in result['assertions']['ah'] for f in atoms(tree)):
            if fact['predicate'] in {'SLEEP','READ'}:
                assert fact['roles']['AGENT']=={'group':[{'entity':'ivan'},{'entity':'maria'}]},fact
        group_binding=next(b for b in state.observation['nominal_reference_bindings'].values() if b.get('local_group_anchor',{}).get('group_dependency'))
        assert group_binding['reference_kind']=='GROUP'
        from ah.formalizer.nominal_reference_binding import payload
        unit=next(u for f in state.frames for u in f.semantic.get('lexical_units',{}).values() if u.get('reference_constraint')==group_binding['reference_constraint'])
        assert payload(state,unit)['target_ref']==group_binding['target_ref']
        assert durable
        saved,ledger=durable[-1]
        anchor_ref=saved['anchor_binding_ref']
        assert ledger.binding_live(anchor_ref,ledger.paths())
        anchor=saved['local_group_anchor']
        dependent_bid=next(b for m,b in zip(anchor['member_anchors'],anchor['member_binding_refs']) if m.get('reference_anchor'))
        ledger.data['bindings'][dependent_bid]['status']='RETIRED'
        assert not ledger.binding_live(anchor_ref,ledger.paths())
        member=next(m for m in group_binding['local_group_anchor']['member_anchors'] if m.get('reference_anchor'))
        state.decisions[member['decision_ref']].outcome='UNRESOLVED'
        try:payload(state,unit)
        except ValueError:pass
        else:raise AssertionError('retired member still licenses group')
        print('PASS: deferred group -> member identity -> K native write; runtime and durable member withdrawal')
