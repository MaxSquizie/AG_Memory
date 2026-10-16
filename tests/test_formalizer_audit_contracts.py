"""Small regressions for audit invariants; model replies are controlled evidence.

These are not language-quality/holdout claims. They exercise competing pages,
source scopes, references and provider limits without a running LLM.
"""
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.pipeline import t0,t1
from ah.formalizer.regions import build_regions


@pytest.mark.parametrize('order',[('A','B','C'),('C','B','A')])
def test_two_supported_pages_never_license_a_first_winner(monkeypatch,order):
    from test_structural_task_frontier import setup
    from ah.formalizer.structural_tasks import choose,licensed
    s,release,region,cfg,calls=setup(monkeypatch,['first','first'])
    assert choose(s,release,None,region,cfg,'pick',[{'candidate_id':c,'label':c} for c in order],'Choose') is None
    domain=next(r for r in s.syntax_trace if r.get('kind')=='TASK_DOMAIN')
    assert domain['supported_ids']==['A','C'] and domain['task_outcome']=='MULTIPLE'
    assert len(calls)==2
    assert all(not licensed(s,{'decision_ref':r['decision_ref'],'candidate_id':r['selected']})
               for r in s.syntax_trace if r.get('kind')=='STRUCTURAL_TASK')


def test_positive_page_with_unknown_remainder_is_not_a_complete_selection(monkeypatch):
    from test_structural_task_frontier import setup
    from ah.formalizer.structural_tasks import choose,licensed
    s,release,region,cfg,calls=setup(monkeypatch,['first','INSUFFICIENT_CONTEXT'])
    assert choose(s,release,None,region,cfg,'pick',[{'candidate_id':str(i),'label':str(i)} for i in range(3)],'Choose') is None
    selected=next(r for r in s.syntax_trace if r.get('selected'))
    assert not licensed(s,{'decision_ref':selected['decision_ref'],'candidate_id':selected['selected']})
    assert len(calls)==2


def test_multisentence_quote_is_one_composition_area():
    from ah.formalizer.source_areas import areas
    s=t1(t0('Иван сказал: «Мария спит. Пётр читает».'))
    s.region_forest=build_regions(s.text,s.evidence,s.source_uid)
    result=areas(s,None,None,{'max_candidates':32,'context_chars':2000})
    assert len(result)==1 and not result[0][1]
    assert set(result[0][0].token_refs)=={t.token_id for t in s.evidence}


def reference_state(text):
    s=t1(t0(text))
    args=tuple(t.token_id for t in s.evidence if any(v.pos in {'NOUN','NPRO'} for v in t.variants))
    s.frames=[NS(frame_id='f',argument_token_refs=args,semantic={},source_range=(0,len(text)))]
    policy={'window_size':100,'event_anaphora_rules':[],'hard_features':['number','gender'],'ranking_criteria':[]}
    release=NS(resources={'CorefPolicy':{'entries':[policy]}},sha256='fixture',version=lambda k:'fixture')
    return s,release


def test_unresolved_quoted_speaker_does_not_capture_chat_user():
    from ah.formalizer.coreference import prepare_references,resolve_references
    s,release=reference_state('Иван сказал: «Я сплю».')
    s.observation['context_snapshot']={'user_ref':'CURRENT_CHAT_USER'}
    slots=prepare_references(s,release);resolve_references(s,slots,None,release)
    tid=next(t.token_id for t in s.evidence if t.span=='Я')
    assert slots[tid]=={} and tid in s.observation['unresolved_references']
    assert tid not in s.observation['entity_bindings']


def test_single_antecedent_still_needs_source_evidence():
    from ah.formalizer.coreference import prepare_references,resolve_references
    s,release=reference_state('Иван пришёл. Он спит.')
    class Unknown:
        selection_reply_format='SELECT_LABELS_V1'
        calls=0
        def select(self,prompt):self.calls+=1;return '?'
    executor=Unknown();slots=prepare_references(s,release)
    assert len(next(iter(slots.values())))==1
    resolve_references(s,slots,executor,release)
    assert executor.calls==1 and s.observation['unresolved_references']
    assert s.observation['entity_bindings']=={}


def test_inline_retains_prior_header_unknown_ends_it(monkeypatch):
    from ah.formalizer import document_scopes
    text='01.01.2026\nИван спит.\n02.01.2026\nНазвание.\n03.01.2026\nПётр читает.'
    s=t1(t0(text));s.observation['batch_kind']='DOCUMENT'
    rule={'rule_id':'numeric','pattern':r'(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})',
          'days':{'01':1,'02':2,'03':3},'months':{'01':1}}
    release=NS(entries=lambda k:[{'document_scopes':{'rules':[rule],'context_chars':200}}])
    answers=iter(['HEADER','INLINE',None])
    monkeypatch.setattr(document_scopes,'_probe',lambda *a,**kw:next(answers))
    document_scopes.prepare(s,release,None)
    assert len(s.document_scopes)==1
    assert s.document_scopes[0]['scope_range']==[0,text.index('03.01.2026')]
    assert [d.code for d in s.diagnostics]==['DOCUMENT_SCOPE_UNRESOLVED']


def test_calendar_spelling_does_not_own_a_word_mention():
    from ah.formalizer.temporal_token_ownership import reject_entity_overlap
    s=t1(t0('Слово «вчера» короткое.'));word=next(t for t in s.evidence if t.span=='вчера')
    frame=NS(frame_id='word',source_range=(0,len(s.text)),argument_token_refs=(word.token_id,),semantic={})
    release=NS(entries=lambda k:[{'pattern':r'\bвчера\b','kind':'DAY'}])
    reject_entity_overlap(s,release,[frame])
    assert not frame.semantic.get('structural_unresolved') and not s.diagnostics


def test_budget_counts_system_text_and_prevents_extra_transport():
    from ah.formalizer.kernel import BoundedExecutor,ProbeLimits
    from ah.formalizer.provider_adapter import BudgetExceeded
    class Executor:
        calls=0
        def prompt_size(self,prompt):return len(prompt)+10
        def select(self,prompt):self.calls+=1;return '1'
    executor=Executor();bounded=BoundedExecutor(executor,ProbeLimits(max_calls=1,max_prompt_chars=12))
    with pytest.raises(BudgetExceeded):bounded.select('too long')
    assert executor.calls==0
    assert bounded.select('ok')=='1'
    with pytest.raises(BudgetExceeded):bounded.select('ok')
    assert executor.calls==1 and bounded.input_chars==12


def test_multiword_relation_reaches_native_plan_with_exact_source(tmp_path,monkeypatch):
    from test_structural_relation_tasks import run,relation,bounds
    steps=relation('LEXICAL')+[
        ('nominal_function','An adposition')]
    steps+=bounds('nominal_function_source','рядом','с')+[('nominal_function_head','Nominal head «домом»'),('nominal_function','No further')]
    result,_=run(tmp_path,monkeypatch,'Иван спит рядом с домом.',steps)
    assert result['diagnostics']['codes']==[] and result['assertions']['ah']
    units=[u for f in result['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved')
           for u in f['semantic'].get('lexical_units',{}).values()]
    unit=next(u for u in units if u['surface']=='рядом с')
    assert unit['anchor_refs']==['tok:10:15','tok:16:17']


def test_ordinary_passive_reaches_same_typed_roles(tmp_path,monkeypatch):
    from test_structural_relation_tasks import run,relation
    result,_=run(tmp_path,monkeypatch,'Книга прочитана Иваном.',relation('LEXICAL')+[
        ('predicate_function','Predicate occurrence «прочитана»')])
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'READ','roles':{
        'THEME':{'entity':'book'},'AGENT':{'entity':'ivan'}}}]
