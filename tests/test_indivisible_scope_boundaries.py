from copy import deepcopy
from types import SimpleNamespace
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.composition_tree import reference
from ah.formalizer.scope_assignment import positions
from ah.formalizer.scope_boundaries import retain,validate


def example():
    state=t0('каждый студент читает и пересказывает')
    words=[('q','каждый',0,6),('s','студент',7,14),('p','читает',15,21),('and','и',22,23),('v','пересказывает',24,36)]
    state.evidence=[SimpleNamespace(token_id=i,span=w,start=a,end=b) for i,w,a,b in words]
    frames=[]
    for fid,token in [('R','s'),('P','p'),('Q','v')]:
        sem={'bound_arguments':{'s':1},'proposition_args':{}}
        if fid=='R':sem['quantifier_restriction']={'head_ref':'s'}
        if fid!='P':sem['component_child']='P'
        frames.append(SimpleNamespace(frame_id=fid,semantic=sem,predicate_token_ref=token,argument_token_refs=('s',)))
    body={'operator':'AND','anchor_refs':['and'],'operands':[reference('P'),reference('Q')]}
    tree={'operator':'FORALL','anchor_refs':['q'],'operands':[{'bound_var':1,'sort':'ENTITY'},
        {'operator':'IMPLIES','operands':[reference('R'),body]}]}
    frames[1].semantic['component_scope_tree']=tree
    retain(state,SimpleNamespace(region_id='area'),frames)
    return state,frames,tree


def test_condition_is_one_external_target_with_source_body_bounds():
    state,frames,tree=example()
    assert [p for p,t in positions(tree,{})]==[()]
    implication=tree['operands'][1]
    assert implication['scope_boundary']['operands'][1]['source_range']==[15,36]
    assert tree['scope_boundary']['source_range']==[0,36]
    assert any(r['kind']=='SCOPE_BOUNDARY' for r in state.syntax_trace)
    validate(frames)


def test_parent_coordination_preserves_whole_selected_condition():
    _,frames,tree=example()
    frames[1].semantic['component_scope_tree']={'operator':'AND','operands':[tree,reference('Z')]}
    validate(frames)
    paths=[p for p,t in positions(frames[1].semantic['component_scope_tree'],{})]
    assert paths==[(),(('operand',0),),(('operand',1),)]


@pytest.mark.parametrize('mutation',['shrink','drop','range','inside_time'])
def test_changed_or_lost_scope_cannot_be_resealed(mutation):
    state,frames,tree=example()
    if mutation=='shrink':tree['operands'][1]['operands'][1]['operands'].pop()
    elif mutation=='drop':frames[1].semantic['component_scope_tree']=reference('P')
    elif mutation=='range':tree['scope_boundary']['source_range'][1]=21
    else:tree['operands'][1]['operands'][1]['region']={'point':'invented'}
    with pytest.raises(ValueError,match='COMPOSITION_SCOPE_BOUNDARY'):
        retain(state,SimpleNamespace(region_id='parent'),frames)


def test_whole_condition_time_annotation_is_allowed():
    _,frames,tree=example();tree['region']={'kind':'POINT','point':'2026-01-01'}
    validate(frames)


def test_verified_frame_renaming_preserves_source_boundaries():
    from ah.formalizer.scope_boundaries import rebase
    _,frames,tree=example();bounds=deepcopy(tree['scope_boundary']['source_range'])
    mapping={f.frame_id:'reused:'+f.frame_id for f in frames}
    def remap(value):
        if isinstance(value,str):return mapping.get(value,value)
        if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [remap(v) for v in value]
        return value
    for f in frames:f.frame_id=mapping[f.frame_id];f.semantic=remap(f.semantic)
    rebase(frames,mapping);validate(frames)
    rebased=frames[1].semantic['component_scope_tree']['scope_boundary']
    assert rebased['source_range']==bounds and rebased['rebound_from']==tree['scope_boundary']['boundary_ref']


def test_partial_overlap_of_condition_source_intervals_is_rejected():
    from ah.formalizer.canonical_ledger import digest
    _,frames,tree=example()
    other={'operator':'IMPLIES','operands':[reference('P'),reference('Q')]}
    record={**tree['scope_boundary'],'source_range':[30,45],'content_hash':digest(other),'operator':'IMPLIES'}
    record.pop('boundary_ref');record['boundary_ref']='scope-boundary:'+digest(record)
    other['scope_boundary']=record
    frames[1].semantic['component_scope_tree']={'operator':'AND','operands':[tree,other]}
    with pytest.raises(ValueError,match='COMPOSITION_SCOPE_BOUNDARY_CROSSING'):validate(frames)


def test_final_seal_rejects_a_shrunk_condition():
    from ah.formalizer.seal import validate_closure
    state,frames,tree=example();state.frames=frames
    tree['operands'][1]['operands'][1]['operands'].pop()
    assert validate_closure(state)==('COMPOSITION_SCOPE_BOUNDARY_CHANGED',)


def test_real_coordination_constructor_keeps_binder_literals(monkeypatch):
    from ah.formalizer.coordination_assignment import compose
    from ah.formalizer.composition_tree import expression
    state,frames,tree=example();root=frames[1]
    other=SimpleNamespace(frame_id='Z',semantic={},anchor_span='z',arguments=())
    for f in frames:f.anchor_span=f.frame_id;f.arguments=()
    monkeypatch.setattr('ah.formalizer.temporal_attachment.attach',lambda state,release,selector,region,selected,frames,tree,cfg:tree)
    result=compose(state,None,None,SimpleNamespace(region_id='parent'),[root,other],[*frames,other],[],{})
    assert result['operands'][0]['operands'][0]=={'bound_var':1,'sort':'ENTITY'}
    validate([*frames,other])


def test_bound_implicit_role_emits_variable_without_entity_or_binding():
    from ah.formalizer.implicit_plan import emit_implicit_roles
    state,frames,tree=example();frame=frames[2];frame.semantic['implicit_arguments']={'SUBJECT':{'gap_id':'gap'}}
    state.observation['implicit_bindings']={'gap':{'bound_var':1,'decision_ref':'choice'}}
    state.decisions['choice']=SimpleNamespace(outcome='RESOLVED')
    roles={};operations=[]
    emit_implicit_roles(state,object(),frame,{'implicit_roles':['SUBJECT']},'tag','fragment',roles,{},
                        lambda *args:operations.append(args),{f.frame_id:f for f in frames})
    assert roles=={'SUBJECT':{'bound_var':1,'sort':'ENTITY'}} and operations==[]


@pytest.mark.parametrize('failure',['outside_scope','unresolved_choice'])
def test_implicit_variable_requires_scope_dominance_and_positive_choice(failure):
    from ah.formalizer.implicit_plan import emit_implicit_roles
    state,frames,tree=example();frame=frames[2];frame.semantic['implicit_arguments']={'SUBJECT':{'gap_id':'gap'}}
    state.observation['implicit_bindings']={'gap':{'bound_var':1,'decision_ref':'choice'}}
    state.decisions['choice']=SimpleNamespace(outcome='RESOLVED' if failure=='outside_scope' else 'UNRESOLVED')
    if failure=='outside_scope':
        tree['operands'][1]['operands'][1]['operands'].pop()
        frame.semantic.pop('component_child')
    with pytest.raises(ValueError,match='QUANTIFIED_CONTROL_UNRESOLVED'):
        emit_implicit_roles(state,object(),frame,{'implicit_roles':['SUBJECT']},'tag','fragment',{}, {},
            lambda *args:pytest.fail('must not emit an entity'),{f.frame_id:f for f in frames})


def test_implicit_options_do_not_turn_quantified_head_into_entity():
    from ah.formalizer.component_participants import prepare_implicit
    from ah.formalizer.state import MorphVariant
    state,frames,tree=example();state.frames=frames
    for token in state.evidence:
        token.variants=(MorphVariant(lemma=token.span,pos='NOUN',cases=frozenset({'nom'}),number='sing',gender='masc',features=frozenset({'anim'})),)
    for f,bounds in zip(frames,[(7,14),(15,21),(24,36)]):
        f.source_range=bounds;f.anchor_span=f.frame_id
        f.semantic['structural_unresolved']=False
    frames[2].argument_token_refs=()
    frames[2].semantic['implicit_arguments']={'SUBJECT':{'gap_id':'gap','features':{'number':'sing'},'license':'SUBJECT_AGREEMENT'}}
    release=SimpleNamespace(entries=lambda kind:[{'composition':{'context_chars':2048,'max_candidates':16}}])
    prepare_implicit(state,release)
    options=frames[2].semantic['implicit_arguments']['SUBJECT']['options']
    bound=[o for o in options if o['kind']=='BOUND_VARIABLE']
    assert bound and all('entity_ref' not in o for o in bound)
    assert not any(o['kind']=='MENTION' and o.get('mention_ref')=='s' for o in options)
