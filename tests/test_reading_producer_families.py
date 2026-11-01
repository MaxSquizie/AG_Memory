"""P02 actual producer paths with controlled model replies and finite inputs."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.state import MorphVariant,FrameCandidate
from ah.formalizer.regions import TextRegion,build_regions
from ah.formalizer.morphology_domain import offer,clean,attested
from ah.formalizer.reading_producers import restore,assessment
from ah.formalizer import reading_witnesses as rw
from test_composition_dispatcher import First,setup_morphology


def base(text):
    s=t0(text);s.budget.llm_limit=100
    r=TextRegion('r','SENTENCE',(0,len(text)),tuple(t.token_id for t in s.evidence),None)
    cfg={'max_candidates':32,'context_chars':10000,'subject_role':'SUBJECT'}
    release=NS(sha256='release',resources={},entries=lambda kind:[{'max_rule_steps':10000,'composition':cfg}] if kind=='ProposalPolicy' else [])
    return s,release,r,cfg


def uses(s):
    rows=[r for r in s.syntax_trace if r.get('kind')=='MORPHOLOGY_USE']
    assert rows
    for row in rows:
        w=restore(row['witness']);assert assessment(s,w).selected_use
        # All family payloads must reject the same class of post-selection mutations.
        for changed in [replace(w,token_ref='foreign'),replace(w,reading_json=rw.freeze({'pos':'VERB'})),
                        replace(w,use_json=rw.freeze({'kind':'OTHER','head_ref':'foreign','role':'OBJECT'})),
                        replace(w,address=replace(w.address,condition_json=rw.freeze({'condition_ref':'foreign'})))]:
            assert not assessment(s,changed).selected_use
    return rows


def child():
    from ah.formalizer.composition_children import select_child
    s,release,r,cfg=base('шмырлик');t=s.evidence[0]
    v=offer(s,t,[MorphVariant(t.span,'NOUN')],'CHILD_TEST')[0]
    frames=[FrameCandidate(fid,'FLAT',t.span,(),predicate_token_ref=t.token_id,semantic={
        'structural_unresolved':True,'morph_bindings':{t.token_id:clean(v)},
        'composition_domain':{'label':label,'decision_ref':'prior','frame_refs':[fid]}})
        for fid,label in [('a','A nominal property'),('b','A nominal event description')]]
    assert select_child(s,release,First(),r,frames,'PROPOSITION','Accepted nominal content') is frames[0]
    return s


def quantity_direct():
    from ah.formalizer.qualitative_quantity import resolve
    s,release,r,cfg=base('два шмырлика');q,t=s.evidence
    q.variants=(MorphVariant('два','NUMR',frozenset({'nom'})),)
    t.variants=offer(s,t,[MorphVariant(t.span,'NOUN',frozenset({'gen'}))],'QUANTITY_TEST')
    projected,groups=resolve(s,release,First(),r,s.evidence,{**cfg,'nominal_host_role':'SUBJECT'})
    assert projected and groups and groups[0]['internal_readings'][0]['cases']==['gen']
    assert projected[1].variants[0].cases=={'nom'}
    return s


def nominal(kind,shared=False):
    from ah.formalizer.nominal_functions import prepare,rows,prepositions,shared_nominal_readings
    from ah.formalizer.qualitative_quantity import general_groups
    s,release,r,cfg=base('двое' if shared else 'два дома')
    if not shared:s.evidence[1].variants=(MorphVariant('дом','NOUN',frozenset({'gen'})),)
    answers=iter(([kind,'1','1']+([] if shared else ['0'])+['1' if shared or kind=='1' else '2']+(['1'] if kind=='3' else [])+['0']))
    selector=NS(selection_reply_format='SELECT_LABELS_V1',select=lambda prompt:next(answers))
    assert prepare(s,release,selector,r,s.evidence,cfg)
    row=rows(s,s.evidence)[0]
    if kind=='1':assert prepositions(s,s.evidence)
    else:
        projected,groups=general_groups(s,release,s.evidence,[row]);assert groups
        if not shared:
            assert groups[0]['internal_readings'][0]['cases']==['gen']
            assert projected[1].variants[0].cases=={'nom'}
    return s


def binder():
    from ah.formalizer.quantifier_composition import bind
    s,release,r,cfg=base('каждый шмырлик');q,t=s.evidence
    q.variants=(MorphVariant('каждый','ADJF',frozenset({'nom'})),)
    v=offer(s,t,[MorphVariant(t.span,'NOUN')],'BINDER_TEST')[0]
    f=FrameCandidate('f','FLAT',s.text,(),argument_token_refs=(t.token_id,),semantic={'morph_bindings':{t.token_id:clean(v)}})
    rule={'operator':'FORALL','variable_sort':'ENTITY','restriction_pattern':{'head_pos':['NOUN'],'agreement':['cases'],'role':'SUBJECT','body_operator':'IMPLIES'}}
    result=bind(s,release,First(),r,[f],{(q.start,q.end,'FORALL'):([q],rule)},cfg)
    assert result
    return s


def dependency():
    from ah.formalizer.component_dependency_reduction import reduce
    s,release,r,cfg=setup_morphology('Книга лежит.')
    t=next(t for t in s.evidence if t.span=='Книга');p=next(t for t in s.evidence if t.span=='лежит')
    t.variants=offer(s,t,[MorphVariant('книга','NOUN',frozenset({'nom'}))],'DEPENDENCY_TEST')
    pv=next(v for v in p.variants if v.pos=='VERB')
    result=reduce(s,release,First(),r,s.evidence,p,pv,[{'role_id':'SUBJECT','allowed_cases':['nom']}],[t],{},cfg)
    assert result is not None
    return s


@pytest.mark.parametrize('producer',[child,quantity_direct,lambda:nominal('1'),lambda:nominal('3'),lambda:nominal('3',True),binder,dependency])
def test_actual_producer_binds_exact_reading_use(producer):
    s=producer();rows=uses(s)
    decision=rows[0]['decision_ref']
    s.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':decision})
    assert not assessment(s,restore(rows[0]['witness'])).selected_use


def test_oov_import_has_pure_receipt_and_negative_cache_tracks_parent_use(monkeypatch):
    from ah.formalizer.composition_session import session
    from ah.formalizer.composition_morphology import prepare
    from ah.formalizer.dispatch_evidence import valid
    s,release,parent,cfg=setup_morphology('Шмырлик лежит.')
    token=next(t for t in s.evidence if t.span=='Шмырлик')
    from ah.formalizer.component_probe import _probe
    from ah.formalizer import contextual_agreement,reading_decisions
    assert _probe(s,First(),release,'independent','nominal_attachment',
        [{'candidate_id':'a','label':'An independently selected context premise'}],s.text,parent.source_range,
        question='Select the context premise.',target_refs=parent.token_refs)=='a'
    original=contextual_agreement.resolve
    def agreement(*args,**kwargs):
        assert reading_decisions.selected(s,'independent')=='a'
        return original(*args,**kwargs)
    monkeypatch.setattr(contextual_agreement,'resolve',agreement)
    with session(s,release,selector=First()) as runtime:
        with runtime.area(parent,s.evidence,None):
            prepare(runtime,parent,s.evidence,None,cfg)
            child=TextRegion('child','RELATION_CHILD',(token.start,token.end),(token.token_id,),parent.region_id)
            with runtime.area(child,[token],None):
                local=prepare(runtime,child,[token],None,cfg)
                row=next(r for r in s.syntax_trace if r.get('kind')=='MORPHOLOGY_USE' and r['token_ref']==token.token_id)
                reading=row['reading'];w=restore(row['witness'])
                assert attested(s,local[0],reading)
                receipts=[r for node in runtime.dispatcher.nodes.values() for r in node.get('evidence_reads',{}).values()
                          if r['kind']=='READING_USE' and r['value'].get('transfer')]
                assert receipts
                receipt=deepcopy(receipts[0]['value'])
                s.syntax_trace.remove(row)
                calls=[]
                def read():calls.append(1);return attested(s,local[0],reading)
                assert not runtime.dispatcher.run('import-consumer',[],read,kind='TEST')
                assert not runtime.dispatcher.run('import-consumer',[],read,kind='TEST') and len(calls)==1
                s.syntax_trace.append(row)
                assert runtime.dispatcher.run('import-consumer',[],read,kind='TEST') and len(calls)==2
    assert valid(s,'READING_USE',receipt)
    uses(s)
    # Lazy evidence retirement: no dispatcher.invalidate event is issued.
    s.decisions['independent'].outcome='UNRESOLVED'
    assert not valid(s,'READING_USE',receipt)
    s.decisions['independent'].outcome=None
    assert valid(s,'READING_USE',receipt)
    imported=receipt['transfer']['import']
    s.syntax_trace[:]=[r for r in s.syntax_trace if r!=imported]
    assert not valid(s,'READING_USE',receipt)


def test_bundle_selection_licenses_its_own_frames_and_reentry_does_not_reuse_old_options(monkeypatch):
    """Constructed clause outputs; actual bundle dispatcher, probe and issuer."""
    from ah.formalizer import component_predication as cp
    import re
    s,release,r,cfg=setup_morphology('Книга лежит.')
    p=next(t for t in s.evidence if t.span=='лежит');n=next(t for t in s.evidence if t.span=='Книга')
    original=next(v for v in p.variants if v.pos=='VERB')
    variants=offer(s,p,[original,replace(original,pos='NOUN',cases=frozenset({'nom'}))],'BUNDLE_TEST')
    def frame(i,v):
        return FrameCandidate('f'+str(i),'FLAT',s.text,(),predicate_token_ref=p.token_id,
            source_range=r.source_range,argument_token_refs=(n.token_id,),semantic={
            'morph_bindings':{p.token_id:clean(v),n.token_id:clean(n.variants[0])},
            'proposed_roles':{n.token_id:'SUBJECT'},'structural_unresolved':False,
            'requires_attachment_probe':True})
    frames=[frame(i,v) for i,v in enumerate(variants)]
    monkeypatch.setattr(cp,'build_clause',lambda *a,**kw:deepcopy(frames))
    def reply(prompt):
        slot=re.search(r'Decision slot: (\S+)',prompt)[1]
        return '0' if slot in {'nominal_function','temporal_function','nominal_coordination_discovery'} else '1'
    selector=NS(selection_reply_format='SELECT_LABELS_V1',select=reply)
    config={**cfg,'modifier_content_role':None,'modifier_composition':None,'nominal_utterance':None}
    result=cp._compose_alternatives(s,release,selector,r,s.evidence,[p],config)
    assert result and any(not f.semantic['structural_unresolved'] for f in result)
    rows=uses(s)
    assert all(__import__('json').loads(row['witness']['use_json'])['frame_ref']=='f0' for row in rows)
    frames[:]=[frame(0,variants[0])];frames[0].semantic['requires_attachment_probe']=False
    before=len(rows)
    result=cp._compose_alternatives(s,release,selector,r,s.evidence,[p],config)
    assert result
    assert len([r for r in s.syntax_trace if r.get('kind')=='MORPHOLOGY_USE'])==before


def test_structural_binder_observes_each_typed_parent_and_keeps_independent_cache():
    from ah.formalizer.composition_session import session
    from ah.formalizer.structural_tasks import choose,licensed
    from ah.formalizer.quantifier_composition import bind
    s,release,r,cfg=base('каждый шмырлик');q,t=s.evidence
    v=offer(s,t,[MorphVariant(t.span,'NOUN')],'STRUCTURAL_BINDER_TEST')[0]
    rule={'operator':'FORALL','variable_sort':'ENTITY','head_ref':t.token_id,
          'restriction_pattern':{'head_pos':['NOUN'],'agreement':['cases'],'role':'SUBJECT','body_operator':'IMPLIES'}}
    with session(s,release,selector=First()) as runtime:
        with runtime.area(r,s.evidence,None):
            for field,slot,payload in [
                ('structural_license','structural_relation',{'candidate_id':'FORALL','relation':'FORALL'}),
                ('head_license','structural_binder_head',{'candidate_id':t.token_id,'head_ref':t.token_id}),
                ('partition_license','structural_partition',{'candidate_id':'partition','groups':[[q.token_id],[t.token_id]]}),
                ('quantifier_kind_license','structural_quantifier_kind',{'candidate_id':'NONNUMERIC'})]:
                from ah.formalizer.task_contracts import required_selection_purpose,SelectionPurpose
                purpose=required_selection_purpose(slot,None) or SelectionPurpose.ALTERNATIVE
                result=choose(s,release,First(),r,cfg,slot,[{**payload,'label':field}],field,purpose=purpose)
                assert result;rule[field]=result[1]
            independent=choose(s,release,First(),r,cfg,'predicate_function',
                [{'candidate_id':'independent','label':'Independent source function'}],'Independent source function')[1]
            f=FrameCandidate('f','FLAT',s.text,(),argument_token_refs=(t.token_id,),semantic={'morph_bindings':{t.token_id:clean(v)}})
            assert bind(s,release,First(),r,[f],{(q.start,q.end,'FORALL'):([q],rule)},cfg)
            row=uses(s)[0];w=restore(row['witness']);chosen=deepcopy(s.decisions[row['decision_ref']].selected)
            calls=[];other=[]
            def consumer():calls.append(1);return assessment(s,w).selected_use
            def unrelated():other.append(1);return licensed(s,independent)
            assert runtime.dispatcher.run('binder-consumer',[],consumer,kind='TEST')
            assert runtime.dispatcher.run('independent-consumer',[],unrelated,kind='TEST')
            for field in ('structural_license','head_license','partition_license','quantifier_kind_license'):
                for kind in ('DEPENDENCY_REJECTED','COMPOSITION_PROBE_SUPERSEDED'):
                    ref=rule[field]['decision_ref']
                    event={'kind':kind,'decision_ref':ref} if kind=='DEPENDENCY_REJECTED' else {'kind':kind,'previous_decision_ref':ref,'decision_ref':'replacement'}
                    s.syntax_trace.append(event)
                    assert s.decisions[row['decision_ref']].selected==chosen
                    assert not assessment(s,w).selected_use
                    assert not runtime.dispatcher.run('binder-consumer',[],consumer,kind='TEST')
                    assert runtime.dispatcher.run('independent-consumer',[],unrelated,kind='TEST') and len(other)==1
                    s.syntax_trace.remove(event)
                    assert runtime.dispatcher.run('binder-consumer',[],consumer,kind='TEST')
            assert len(calls)==17
