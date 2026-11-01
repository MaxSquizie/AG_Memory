"""Decision revocation across derived-reading families; no model claims."""
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.state import MorphVariant,Decision,Ground,FrameCandidate
from ah.formalizer.morphology_domain import clean,offer,license_use,validate_uses
from ah.formalizer.nominal_readings import attested
from ah.formalizer.reading_decisions import selected,receipt
from ah.formalizer.dispatch_evidence import valid,evidence_probe_refs


def setup(kind):
    if kind=='proposed':
        from test_reading_producers import prepared
        state,token,reading,_=prepared()
        return state,token,reading
    from ah.formalizer.morphology_provenance import capture,issue
    from ah.formalizer.nominal_readings import clean as cleaned
    state=t0('example quantity');token=state.evidence[0];token.token_id='t'
    marker=state.evidence[1];marker.token_id='q'
    base=MorphVariant('example','ADJF' if kind!='quantity' else 'NOUN',frozenset({'nom'}),origin='DICTIONARY')
    token.variants=(base,);marker.variants=(MorphVariant('quantity','NUMR',origin='DICTIONARY'),)
    capture(state)
    cid='selected'
    state.decisions['d']=Decision('nominal_attachment','f',(cid,),selected=(cid,),
        grounds=[Ground('M','scripted choice',cid)])
    if kind=='recovered':
        value=replace(base,origin='RECOVERED',evidence_refs=('q','d'))
        row=dict(kind='AGREEMENT_RECOVERY',token_ref='t',head_ref='q',selected=cid,
            original_variants=[clean(base)],recovered_reading=clean(value),
            options=[dict(candidate_id=cid,head_ref='q',replacement_reading=clean(base),replacement_surface='example')],
            lexical_recovery={'decision_ref':'d','surface':'example'},selection_receipt=receipt(state,'d'))
        issue(state,row,['t','q']);state.syntax_trace.append(row)
    elif kind=='substantive':
        from ah.formalizer.contextual_substantives import overlay
        from ah.formalizer.regions import TextRegion
        from ah.formalizer.reading_producers import binding,attach,from_selection
        from ah.formalizer.component_probe import _probe
        from test_composition_dispatcher import First
        release=NS(sha256='test');region=TextRegion('r','SENTENCE',(0,len(state.text)),('t','q'),None)
        # Source adapters bind their release before issuing a transformation.
        state.resource_snapshot={'snapshot_id':'test'}
        projected=overlay(state,release,First(),region,[token],{'substantive_readings':'CONTEXTUAL_SUBSTANTIVE_V1'})
        value=projected[0].variants[-1]
        entry=binding(state,release,region,'t',value,{'kind':'ARGUMENT','role':'SUBJECT'})
        assert _probe(state,First(),release,'d','nominal_attachment',
            [attach({'candidate_id':cid,'label':'Nominal use'},[entry])],state.text,region.source_range,
            question='Which function does this occurrence have?',target_refs=('t','q'))==cid
        license_use(state,'t',clean(value),'d',cid,witness=from_selection(state,'d',cid,entry))
    else:
        value=MorphVariant(base.lemma,'NOUN',frozenset({'nom'}),features=frozenset({'NOUN','QUALITATIVE_GROUP'}),
                          origin='CONTEXTUAL',evidence_refs=('d','q','t'))
        row=dict(kind='QUANTITY_COMPOSITION',head_ref='t',decision_ref='d',
            marker_ref='q',internal_readings=[clean(base)],external_cases=['nom'],selection_receipt=receipt(state,'d'))
        issue(state,row,['t','q']);state.syntax_trace.append(row)
    return state,token,clean(value)


@pytest.mark.parametrize('kind',['proposed','recovered','substantive','quantity'])
@pytest.mark.parametrize('event',['DEPENDENCY_REJECTED','COMPOSITION_PROBE_SUPERSEDED'])
def test_retired_ground_invalidates_every_derived_family(kind,event):
    state,token,reading=setup(kind)
    assert attested(state,'t',reading)
    state.syntax_trace.append({'kind':event, 'decision_ref':'d' if event=='DEPENDENCY_REJECTED' else 'replacement',
                               'previous_decision_ref':'d'})
    assert not attested(state,'t',reading)
    frame=FrameCandidate('f','FLAT','example',(),semantic={'morph_bindings':{'t':reading}})
    with pytest.raises(ValueError,match='MORPHOLOGY_USE_UNGROUNDED'):validate_uses(state,[frame])


def test_published_recovery_cannot_become_original_evidence():
    from ah.formalizer.nominal_readings import variant
    state,token,reading=setup('recovered');token.variants=(variant(reading),)
    state.syntax_trace.append(dict(kind='DEPENDENCY_REJECTED',decision_ref='d'))
    assert not attested(state,'t',reading)


def test_decision_outcome_and_exact_support_changes_invalidate_reads_and_uses():
    state,_,reading=setup('proposed');saved=receipt(state,'d')
    assert valid(state,'READING_DECISION',saved)
    state.decisions['d'].outcome='UNRESOLVED'
    assert not valid(state,'READING_DECISION',saved)
    state.decisions['d'].outcome=None
    state.decisions['d'].grounds.append(Ground('D','new basis','selected'))
    assert not attested(state,'t',reading)
    assert evidence_probe_refs(state,'READING_DECISION',saved)=={'d'}


def test_cached_consumer_without_reexecuting_probe_observes_retirement(monkeypatch):
    from ah.formalizer.composition_dispatcher import Dispatcher
    from ah.formalizer import composition_session
    state,_,reading=setup('recovered');dispatcher=Dispatcher(state)
    monkeypatch.setattr(composition_session,'current',lambda _:NS(dispatcher=dispatcher,release=NS(sha256=state.resource_snapshot.get('snapshot_id'))))
    calls=[]
    def compute():calls.append(1);return attested(state,'t',reading)
    assert dispatcher.run('use',[],compute,kind='TEST')
    assert dispatcher.run('use',[],compute,kind='TEST') and len(calls)==1
    state.syntax_trace.append(dict(kind='DEPENDENCY_REJECTED',decision_ref='d'))
    assert not dispatcher.run('use',[],compute,kind='TEST')
    assert len(calls)==2


def test_raw_probe_branch_cannot_be_used_as_global_ground(monkeypatch):
    from ah.formalizer.reading_decisions import inspect
    state,_,_=setup('recovered')
    state.component_probe_records['d']={'branch_condition':{'condition_ref':'branch'}}
    assert inspect(state,'d')['selected'] is None
    monkeypatch.setattr('ah.formalizer.structural_conditions.historical',lambda s,c:True)
    monkeypatch.setattr('ah.formalizer.structural_conditions.allows',lambda s,a,b:a==b)
    assert inspect(state,'d',{'condition_ref':'branch'})['selected']=='selected'
    assert inspect(state,'d',{'condition_ref':'sibling'})['selected'] is None


def test_source_revision_invalidates_existing_use():
    state,_,reading=setup('proposed')
    assert attested(state,'t',reading)
    state.interpretation_version+=1
    assert not attested(state,'t',reading)


def test_semantic_promotion_does_not_replace_the_selected_ground():
    state,_,reading=setup('proposed')
    state.decisions['d'].outcome='RESOLVED'
    assert attested(state,'t',reading)


def test_recovery_confidence_is_not_a_different_whole_reading():
    state,_,reading=setup('recovered');reading['score']=0.3
    assert attested(state,'t',reading)
