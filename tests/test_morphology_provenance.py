"""P03 producer/consumer contrasts. Scripted evidence, no model claims."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.morphology_provenance import live,original,capture,issue,token_source,normalized
from ah.formalizer.morphology_domain import clean,offer
from ah.formalizer.nominal_readings import attested,variant
from ah.formalizer.state import FrameCandidate,Ground
from test_reading_producers import prepared
from test_derived_reading_liveness import setup


@pytest.mark.parametrize('mutation',['source_text','surface','range','variant','manifest','resource','row','version'])
def test_proposal_full_source_and_output_are_bound(mutation):
    state,token,reading,_=prepared()
    row=next(r for r in state.syntax_trace if r['kind']=='MORPHOLOGY_PROPOSAL')
    assert live(state,row) and attested(state,'t',reading)
    if mutation=='source_text':state.text+='!'
    elif mutation=='surface':token.span+='x'
    elif mutation=='range':token.start+=1
    elif mutation=='variant':token.variants=(replace(token.variants[0],gender='femn'),)
    elif mutation=='manifest':state.morphology_manifest['provider']='changed'
    elif mutation=='resource':state.resource_snapshot={'snapshot_id':'changed'}
    elif mutation=='version':state.interpretation_version+=1
    else:row['reading']['cases']=['dat']
    assert not live(state,row) and not attested(state,'t',reading)


def test_score_changes_do_not_revoke_but_all_linguistic_features_do():
    state,token,reading,_=prepared();token.score=.2
    token.variants=tuple(replace(v,score=.1) for v in token.variants)
    for row in state.syntax_trace:
        if row.get('reading'):row['reading']['score']=.3
    assert attested(state,'t',reading)
    token.variants=tuple(replace(v,features=v.features|{'new'}) for v in token.variants)
    assert not attested(state,'t',reading)


def test_recovery_same_selection_different_basis_is_revoked_before_publication():
    state,token,reading=setup('recovered')
    assert attested(state,'t',reading)
    state.decisions['d'].grounds.append(Ground('M','different context','selected'))
    assert not attested(state,'t',reading)


def test_publication_keeps_original_separate_and_rechecks_recovery():
    from ah.formalizer.composition_morphology import publish_recoveries
    state,token,reading=setup('recovered');source=clean(token.variants[0])
    frame=FrameCandidate('f','FLAT','example',(),semantic={'morph_bindings':{'t':reading}})
    publish_recoveries(state,[frame])
    assert token.lex_status=='RECOVERY_SELECTED'
    assert attested(state,'t',reading) and original(state,'t',source)
    assert not original(state,'t',reading)
    state.decisions['d'].grounds.append(Ground('M','changed premise','selected'))
    assert not attested(state,'t',reading) and not original(state,'t',source)


def test_parent_recovery_revoke_invalidates_substantive_without_source_change():
    from ah.formalizer.contextual_substantives import overlay
    state,token,reading=setup('recovered')
    local=replace(token,variants=(variant(reading),))
    overlay(state,NS(sha256=None),None,NS(region_id='r'),[local],{'substantive_readings':'CONTEXTUAL_SUBSTANTIVE_V1'})
    row=state.syntax_trace[-1]
    assert live(state,row)
    before=token_source(token)
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':'d'})
    assert token_source(token)==before and not live(state,row)


def test_historical_packet_preserves_records_and_current_authority():
    from ah.formalizer.structural_shells import evidence_state
    from ah.formalizer.validation_graph import scope
    state,_,reading,_=prepared();row=next(r for r in state.syntax_trace if r['kind']=='MORPHOLOGY_PROPOSAL')
    packet={'trace':deepcopy(state.syntax_trace),'decisions':{},'probes':{},'morphology_records':dict(state.morphology_records)}
    state.syntax_trace=[];state.morphology_records={}
    local=evidence_state(state,{'evidence':packet},read_only=True)
    assert live(local,row) and not state.morphology_records
    with scope() as graph:
        view=graph.overlay(state,packet)
        assert live(view,row)
        state.morphology_records[row['morphology_ref']]='revoked'
        changed=graph.overlay(state,packet)
        assert changed is not view and not live(changed,row)


def test_nested_parent_refs_and_nonreading_scores_are_not_erased():
    assert normalized({'parent':{'morphology_ref':'p'},'score':2})=={'parent':{'morphology_ref':'p'},'score':2}


def test_nonlexical_is_source_evidence_but_prediction_is_not():
    from ah.formalizer.pipeline import t0
    from ah.formalizer.state import MorphVariant
    state=t0('.')
    state.evidence[0].variants=(MorphVariant('.',None,origin='NONLEXICAL'),)
    capture(state)
    assert original(state,state.evidence[0].token_id,clean(state.evidence[0].variants[0]))
    state=t0('unknown');state.evidence[0].variants=(MorphVariant('guess','NOUN',origin='PREDICTED'),)
    with pytest.raises(ValueError,match='ALREADY_DERIVED'):capture(state)


def test_view_identity_includes_required_trace_not_only_records():
    from ah.formalizer.validation_graph import scope
    state,_,_,_=prepared();row=next(r for r in state.syntax_trace if r['kind']=='MORPHOLOGY_PROPOSAL')
    packet={'trace':deepcopy(state.syntax_trace),'decisions':{},'probes':{},'morphology_records':dict(state.morphology_records)}
    state.syntax_trace=[];state.morphology_records={}
    with scope() as graph:
        good=graph.overlay(state,packet)
        bad=graph.overlay(state,{**packet,'trace':[]})
        assert good is not bad and live(good,row) and not live(bad,row)


def test_parent_chain_has_no_recursive_stack_or_exponential_search(monkeypatch):
    import ah.formalizer.morphology_provenance as provenance
    from ah.formalizer.pipeline import t0
    state=t0('word');token=state.evidence[0]
    from ah.formalizer.state import MorphVariant
    token.variants=(MorphVariant('word','NOUN'),)
    local=token
    for index in range(80):
        values=offer(state,local,local.variants,str(index))
        local=replace(local,variants=values)
    count=0;old=provenance._record_live
    def counted(*args):
        nonlocal count
        count+=1
        return old(*args)
    monkeypatch.setattr(provenance,'_record_live',counted)
    assert live(state,state.syntax_trace[-1]) and count<=160


def test_conditional_availability_requires_explicit_branch_and_live_history(monkeypatch):
    from ah.formalizer.nominal_readings import available
    from ah.formalizer import function_inventory,structural_conditions
    state,token,_,_=prepared()
    condition={'condition_ref':'branch'}
    monkeypatch.setattr(function_inventory,'execution_condition',lambda s:condition)
    value=offer(state,token,token.variants,'conditional')[0];row=state.syntax_trace[-1]
    monkeypatch.setattr(structural_conditions,'historical',lambda s,c:True)
    monkeypatch.setattr(structural_conditions,'allows',lambda s,a,b:a==b)
    assert live(state,row)
    assert available(state,'t',clean(value),condition=condition)
    assert not available(state,'t',clean(value),condition=None)
    monkeypatch.setattr(structural_conditions,'historical',lambda s,c:False)
    assert not live(state,row)


def test_addressed_retirement_includes_derived_parent_but_not_unrelated_decision():
    from ah.formalizer.dispatch_evidence import evidence_probe_refs
    from ah.formalizer.contextual_substantives import overlay
    state,token,reading=setup('recovered')
    overlay(state,NS(sha256=None),None,NS(region_id='r'),[replace(token,variants=(variant(reading),))],
        {'substantive_readings':'CONTEXTUAL_SUBSTANTIVE_V1'})
    refs=evidence_probe_refs(state,'MORPHOLOGY_PROVENANCE',{'row':state.syntax_trace[-1]})
    assert refs=={'d'}


def test_sealed_reading_is_revalidated_before_native_plan(monkeypatch):
    from ah.formalizer.seal import structural_seal,validate_closure
    from ah.formalizer.native_plan import build_plan
    state,token,reading=setup('recovered')
    frame=FrameCandidate('f','FLAT','example',('example',),predicate_token_ref='t',
        semantic={'morph_bindings':{'t':reading}})
    state.frames=[frame]
    assert structural_seal(state).closed
    state.decisions['d'].grounds.append(Ground('M','revoked after seal','selected'))
    assert validate_closure(state)==('MORPHOLOGY_USE_UNGROUNDED',)
    monkeypatch.setattr('ah.formalizer.discourse_scopes.for_tree',lambda s,t:{'speech_act':'ASSERTION'})
    operations,fragments,diagnostics,_=build_plan(state,NS(entries=lambda name:[]),NS())
    assert not operations and not fragments
    assert diagnostics==('MORPHOLOGY_USE_UNGROUNDED:f',)


@pytest.mark.parametrize('location',['morph_bindings','pp_readings','nominal_dependencies','attribute_constraints',
    'dependency_evidence','group_readings','control_binding','quantifier_restriction'])
def test_registered_locations_do_not_allow_a_forged_original(location):
    from ah.formalizer.morphology_domain import validate_uses
    state,token,reading=setup('recovered');raw=clean(token.variants[0])
    bad={**raw,'gender':'impossible'}
    sem={location:{'t':bad}}
    d={'head_ref':'t','host_ref':'q','morph':bad}
    if location in {'nominal_dependencies','attribute_constraints'}:sem={location:[d]}
    elif location=='dependency_evidence':sem={location:d}
    elif location=='group_readings':sem={location:{'t':{'selected_head_reading':bad,'external_reading':bad}}}
    elif location=='control_binding':sem={location:{'frame_ref':'p','role':'SUBJECT','token_ref':'t','morph':bad}}
    elif location=='quantifier_restriction':sem={location:{'head_ref':'t','binding_slot':'x','marker_refs':['q'],'selected_reading':bad}}
    frame=FrameCandidate('f','FLAT','example',(),semantic=sem)
    with pytest.raises(ValueError,match='MORPHOLOGY_USE_UNGROUNDED'):validate_uses(state,[frame])


def test_negative_candidate_query_is_a_dispatch_dependency(monkeypatch):
    from ah.formalizer.nominal_readings import available
    from ah.formalizer.composition_dispatcher import Dispatcher
    state,_,reading,_=prepared();proposal=state.syntax_trace.pop(0)
    assert proposal['kind']=='MORPHOLOGY_PROPOSAL'
    dispatcher=Dispatcher(state);calls=[]
    monkeypatch.setattr('ah.formalizer.composition_session.current',lambda s:NS(dispatcher=dispatcher,release=NS(sha256=None)))
    def compute():calls.append(1);return available(state,'t',reading)
    assert not dispatcher.run('candidate',[],compute,kind='TEST')
    state.syntax_trace.append(proposal)
    assert dispatcher.run('candidate',[],compute,kind='TEST') and len(calls)==2


def test_conditional_group_is_not_an_unconditional_original_group(monkeypatch):
    from ah.formalizer.morphology_provenance import group_live
    from ah.formalizer.morphology_domain import validate_uses
    state,token,reading=setup('quantity');row=state.syntax_trace[-1]
    condition={'condition_ref':'branch'};row['condition']=condition
    issue(state,row,['t','q'])
    monkeypatch.setattr('ah.formalizer.structural_conditions.historical',lambda s,c:True)
    monkeypatch.setattr('ah.formalizer.structural_conditions.allows',lambda s,a,b:a==b)
    assert live(state,row) and group_live(state,row,condition=condition)
    frame=FrameCandidate('f','FLAT','example',(),semantic={'qualitative_groups':[row]})
    with pytest.raises(ValueError,match='MORPHOLOGY_GROUP_UNGROUNDED'):validate_uses(state,[frame],condition=None)
    validate_uses(state,[frame],condition=condition)


def test_compact_condition_is_in_addressed_dependency_projection(monkeypatch):
    from ah.formalizer import dispatch_evidence
    from ah.formalizer.morphology_provenance import probe_refs
    state,_,_,_=prepared();row=state.syntax_trace[0]
    row={**row,'condition':{'condition_ref':'branch'}}
    prior=dispatch_evidence.evidence_probe_refs
    monkeypatch.setattr(dispatch_evidence,'evidence_probe_refs',lambda s,k,v: {'branch-probe'}
        if k=='CONDITIONAL_PROOF' and v.get('condition')==row['condition'] else prior(s,k,v))
    assert 'branch-probe' in probe_refs(state,row)


def test_deep_control_transfer_uses_iterative_walk_with_real_origin_witness():
    from ah.formalizer.reading_producers import frame_bindings,attach,issue as issue_use,location_supported
    from ah.formalizer.reading_locations import locations
    from ah.formalizer.component_probe import _probe
    from ah.formalizer.regions import TextRegion
    from ah.formalizer.control_arguments import controllers,bind
    from test_composition_dispatcher import First
    state,token,reading,_=prepared()
    region=TextRegion('r','SENTENCE',(0,7),('t',),None);release=NS(sha256='test')
    sem={'proposed_roles':{'t':'SUBJECT'},'morph_bindings':{'t':reading,'verb':{'pos':'INFN'}},
        'lexical_units':{'t':{'surface':'example'}}}
    root=FrameCandidate('root','FLAT','example',(),predicate_token_ref='verb',construction='COMPONENTS_V1',semantic=sem)
    entries=frame_bindings(state,release,region,[root],family='BUNDLE')
    option=attach({'candidate_id':'selected','label':'Subject of the infinitive'},entries)
    assert _probe(state,First(),release,'bundle','nominal_attachment',[option],state.text,(0,7),
        question='Choose the attachment',target_refs=('t',))=='selected'
    issue_use(state,'bundle','selected',entries)
    state.frames=[root];parent=root
    for index in range(1050):
        child=deepcopy(root);child.frame_id='child'+str(index)
        alias=next(controllers(parent))[0];bind(child.semantic,alias,'SUBJECT')
        state.frames.append(child);parent=child
    entry=next(e for e in locations(parent) if e.path=='morph_bindings' and e.token_ref=='t')
    assert location_supported(state,parent,entry)
    root.semantic['proposed_roles']['t']='OBJECT'
    assert not location_supported(state,parent,entry)


def test_import_history_uses_complete_provider_maps_and_revokes_cold():
    import json
    from test_reading_witnesses import prepared as domain_prepared
    from ah.formalizer.canonical_ledger import digest
    from ah.formalizer.morphology_provenance import _live
    from ah.formalizer.dispatch_history import valid
    state,token,_,w=domain_prepared(domain=True)
    restriction={'kind':'MORPHOLOGY_FUNCTION_RESTRICTION','token_ref':token.token_id,
        'function_domain':json.loads(w.domain_json)}
    issue(state,restriction,[token.token_id]);state.syntax_trace.append(restriction)
    imported={'kind':'MORPHOLOGY_FUNCTION_IMPORT','token_ref':token.token_id,
        'function_ref':digest(restriction),'parent_task':'provider','parent_revision':1}
    issue(state,imported,[token.token_id]);state.syntax_trace.append(imported)
    state.syntax_trace.extend([
        {'kind':'DISPATCH_COMPLETED','task_ref':'provider','revision':1,'task_kind':'MORPHOLOGY','dependencies':[],'evidence_reads':[]},
        {'kind':'DISPATCH_COMPLETED','task_ref':'consumer','revision':1,'task_kind':'MORPHOLOGY','dependencies':[],
         'evidence_reads':[{'kind':'MORPHOLOGY_PROVENANCE','value':{'row':imported},'expected':True}]}])
    assert valid(state,'consumer',1)
    for _ in range(3):assert _live(state,imported,{('provider',1):True})
    state.syntax_trace.append({'kind':'DISPATCH_INVALIDATED','task_ref':'provider'})
    assert not valid(state,'consumer',1) and not _live(state,imported)
    assert not _live(state,imported,{('provider',1):False})
