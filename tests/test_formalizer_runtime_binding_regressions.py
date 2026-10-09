"""Regression checks for defects found by native/oracle integration."""
from dataclasses import replace
from copy import deepcopy
import pytest
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.rx_observability import lexical_keys
from ah.formalizer.speech_act import detect_negation
from ah.formalizer.temporal_license import point,cont,exist,or_elimination_license,forall_inst_license
from ah.formalizer.canonical_ledger import simultaneity_result
from tools.formalizer_v7_test_support import test_release,sign_test_release,FixtureMorph
from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.formalizer.resources.loader import ResourceRelease,ResourceMissing
from ah.formalizer.state import FormalizationState,FrameCandidate,Decision,TokenEvidence,MorphVariant
from ah.formalizer.runtime_adapter import FormalizerAdapter


def test_morph_pos_plain_string():
    variants=MorphProvider().analyze('есть')
    assert all(v.pos is None or type(v.pos) is str for v in variants)
    assert any(v.pos in {'VERB'} for v in variants)

def test_custom_morph_rx_keys():assert 'иван' in lexical_keys('Ивана',FixtureMorph())

@pytest.mark.parametrize('text,expected',[('не пришёл',True),('небо',False),('ни один',False),('не.',True)])
def test_not_word_boundary(text,expected):assert detect_negation(text)==expected

def test_continuous_singleton_covered_by_point():
    assert or_elimination_license(cont(5,5),point(5)).status=='LICENSED'
    assert or_elimination_license(cont(5,6),point(5)).status=='UNKNOWN'

def test_degenerate_existential_normalizes():
    assert or_elimination_license(exist(5),point(5)).derived_region==point(5)

def test_unknown_points_not_equal():
    assert or_elimination_license(point(None),point(None)).diagnostic=='INTERVAL_BOUNDARY_UNKNOWN'
    assert forall_inst_license(point(None),point(None)).diagnostic=='INTERVAL_BOUNDARY_UNKNOWN'

def test_possible_overlap_not_guaranteed():
    assert simultaneity_result(exist(1,2),exist(2,3))=={'guaranteed':False,'diagnostic':'SIMULTANEITY_NOT_ESTABLISHED'}
    assert simultaneity_result(cont(0,3),exist(1,2))['guaranteed']

def native_state():
    st=FormalizationState(source_uid='test',interpretation_version=1,context_version=0,text='Иван не пришёл, Мария спит.')
    st.observation={'observation_id':'test','text':st.text,'interpretation_version':1}
    for fid,word,lemma,start in [('F1','пришёл','прийти',8),('F2','спит','спать',23)]:
        tid=fid+':p';st.evidence.append(TokenEvidence(span=word,token_id=tid,start=start,end=start+len(word),variants=(MorphVariant(lemma=lemma,pos='VERB'),)))
        st.frames.append(FrameCandidate(fid,'FLAT',word,(),predicate_token_ref=tid,source_range=(0,len(st.text))))
        st.decisions[fid+'|predicate_value']=Decision('predicate_value',fid,('V',),selected=('V',),outcome='RESOLVED')
    return st

def test_native_negation_only_scoped_frame():
    st=native_state();st.logical_roots=[{'operator':'NOT','operands':[{'frame_ref':'F1'}]},{'frame_ref':'F2'}]
    result=FormalizerAdapter(object())._to_perception_result(st)
    assert [a.negated for a in result.assertions]==[True,False]

def test_or_branches_not_projected_as_asserted_facts():
    st=native_state();st.logical_roots=[{'operator':'OR','operands':[{'frame_ref':'F1'},{'frame_ref':'F2'}]}]
    result=FormalizerAdapter(object())._to_perception_result(st)
    assert not result.assertions and any('NATIVE_ASSERTION_SCOPE_OWNED' in d for d in result.diagnostics)

def test_invalid_signature_even_if_pinned():
    release=test_release(AHCore(AHStore()))
    signed,trusted=sign_test_release(release.manifest)
    bad=deepcopy(signed.manifest);bad['signed_review_id']['signature']='A'*88
    trusted['reviews'][signed.sha256]=bad['signed_review_id']
    with pytest.raises(ResourceMissing,match='signature'):ResourceRelease(bad,trusted_reviews=trusted)

def test_template_map_requires_actual_ah():
    from tools.formalizer_v7_test_support import role
    core=AHCore(AHStore());release=test_release(core,[('TEST','test','VERB',[role('SUBJECT')],'STATE')])
    with pytest.raises(ResourceMissing):release.validate_store(AHStore())
