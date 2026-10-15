"""Legacy released-complement producer; general tasks have separate route tests."""
from types import SimpleNamespace
from copy import deepcopy

import pytest

from ah.formalizer.attitude_composition import complement_options
from ah.core import AHCore
from ah.formalizer.resources.loader import ResourceRelease, ResourceMissing
from tools.formalizer_v7_native_binding import ChatBackend, execute_native, fixture
from tools.formalizer_v7_extended_binding import Session


def run(tmp_path, monkeypatch, text, answer='1'):
    # Exercise this producer directly, even when the GUI's full profile also
    # enables the general relation producer (whose labels are different).
    from tools.formalizer_component_fixture import with_components
    monkeypatch.setattr('tools.formalizer_component_fixture.with_full_composition',
        lambda release,core:with_components(release,core=core,predication=True,relative_time=True,
            omissions=True,modifier_forest=True,nominal_tree=True,dependency_reduction=True,
            refinement=True,document_scopes=True,spatial_references=True,quantified_scopes=True))
    prompts=[]
    def generate(self, prompt, **kwargs):
        prompts.append(prompt)
        return answer
    monkeypatch.setattr(ChatBackend,'generate',generate)
    payload={'raw_input':{'text':text,'source_id':'finite-content','revision':1,
        'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    result=execute_native(Session([payload],tmp_path/'journal.log'),payload,
        {'provider':'lmstudio','model':'test','structure_mode':'region_probes'})
    return result,prompts


def arrival(person):
    return {'predicate':'ARRIVE','roles':{'AGENT':{'entity':person}}}


def content(predicate, person, child):
    return {'predicate':predicate,'roles':{'AGENT':{'entity':person},'CONTENT':child}}


@pytest.mark.parametrize('text,expected',[
    ('Иван сказал, что Пётр пришёл.',content('SAY','ivan',arrival('petr'))),
    ('Иван думал, что Пётр пришёл.',content('THINK','ivan',arrival('petr'))),
    ('Иван сказал, что Пётр не пришёл.',content('SAY','ivan',{'operator':'NOT','operands':[arrival('petr')]})),
    ('Иван не сказал, что Пётр пришёл.',{'operator':'NOT','operands':[content('SAY','ivan',arrival('petr'))]}),
    ('Иван сказал, что Пётр думал, что Мария пришла.',content('SAY','ivan',content('THINK','petr',arrival('maria')))),
    ('Иван сказал: «Пётр пришёл».',content('SAY','ivan',arrival('petr'))),
    ('Иван сказал: «Пётр думал, что Мария пришла».',content('SAY','ivan',content('THINK','petr',arrival('maria')))),
])
def test_recursive_content_has_only_parent_assertion(tmp_path,monkeypatch,text,expected):
    result,prompts=run(tmp_path,monkeypatch,text)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[expected]
    assert not any('Decision slot: clause_boundary ' in p for p in prompts)
    traces=result['runtime']['ir']['syntax_trace']
    rows=[r for r in traces if r.get('kind')=='ATTITUDE_COMPOSITION']
    assert rows and all(r['resolved'] for r in rows)
    assert all(text[slice(*r['content_range'])] for r in rows)
    if 'что' in text:
        row=next(r for r in rows if r['delimiter_scope']['kind']=='RELEASED_COMPLEMENT')
        assert row['delimiter_scope']['marker_reading']=={'lemma':'что','POS':'CONJ'}


@pytest.mark.parametrize('answer',['?','0','ONE_SELECTED'])
def test_unconfirmed_content_never_becomes_an_independent_fact(tmp_path,monkeypatch,answer):
    result,prompts=run(tmp_path,monkeypatch,'Иван сказал, что Пётр пришёл.',answer)
    assert result['assertions']['ah']==[]
    assert 'ATTITUDE_SLOT_UNCLOSED' in result['diagnostics']['codes']
    assert len(prompts)==1 and 'Decision slot: attitude_attachment\n' in prompts[0]


def test_missing_content_does_not_assert_parent_or_child(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван сказал, что.')
    assert result['assertions']['ah']==[]


def test_complement_requires_released_whole_reading_and_obeys_limit():
    rule={'lemma':'сказать','argument_role':'OBJECT','attitude':'QUOTED',
          'complementizers':[{'lemma':'что','POS':'CONJ'}]}
    release=SimpleNamespace(entries=lambda kind:[rule])
    def token(i,lemma,pos,span=None):
        return SimpleNamespace(token_id=str(i),start=i*10,end=i*10+5,span=span or lemma,
            variants=[SimpleNamespace(lemma=lemma,pos=pos,mood=None)])
    owner=token(0,'сказать','VERB');marker=token(1,'что','NPRO')
    tokens=[owner,marker,token(2,'прийти','VERB'),token(3,',','PNCT'),token(4,'спать','VERB')]
    assert not complement_options(None,release,tokens,None,10)
    marker.variants.append(SimpleNamespace(lemma='что',pos='CONJ',mood=None))
    assert len(complement_options(None,release,tokens,None,1))==1
    assert len(complement_options(None,release,tokens,None,10))==2
    rule.pop('complementizers')
    assert not complement_options(None,release,tokens,None,10)


@pytest.mark.parametrize('markers',[[{'lemma':'что','POS':'NPRO'}],[{'lemma':'что'}],None])
def test_release_rejects_invalid_complementizer_readings(markers):
    release,_=fixture(AHCore(),'known')
    manifest=deepcopy(release.manifest)
    next(r for r in manifest['entries'] if r['kind']=='AttitudeMap')['entries'][0]['complementizers']=markers
    manifest.pop('coverage_report');manifest.pop('signed_review_id')
    with pytest.raises(ResourceMissing):
        ResourceRelease(manifest,require_review=False)
