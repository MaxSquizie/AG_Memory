"""OOV source forms survive native write/query; analyzer guesses are audit only."""
from dataclasses import replace
import pytest
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.graph_ops import ensure_template
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from test_structural_relation_tasks import Script,relation,run,unary

CONFIG={'provider':'lmstudio','model':'scripted-oov','structure_mode':'region_probes'}


def function(pos='VERB'):
    return ('structural_oov_function',pos+':')


def payload(text,source,kind='ASSERTION'):
    return {'raw_input':{'text':text,'source_id':source,'revision':1,'range':[0,len(text)],
        'language':'ru','request_kind':kind,'batch_kind':'MESSAGE'}}


def execute(session,item,steps,monkeypatch):
    script=Script(steps)
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:script.generate(prompt,**kw))
    result=execute_native(session,item,CONFIG)
    assert not script.errors,script.errors
    assert not script.steps,list(script.steps)
    return result,script


def test_native_unproved_forms_do_not_merge_symbols_or_events(tmp_path,monkeypatch):
    first=payload('Иван глоркнул книгу.','first')
    second=payload('Мария глоркнула книгу.','second')
    session=Session([first,second],tmp_path/'journal')
    a,_=execute(session,first,[function()]+relation('LEXICAL'),monkeypatch)
    symbol=session.core.store.find_symbol_by_form('глоркнул')
    assert symbol is not None and not session.core.store.find_symbols_by_form('глоркнуть')
    before=set(session.store.ledger.data['nodes'])
    b,_=execute(session,second,[function()]+relation('LEXICAL'),monkeypatch)
    other=session.core.store.find_symbol_by_form('глоркнула')
    assert other is not None and other.uid!=symbol.uid
    assert before<set(session.store.ledger.data['nodes'])
    assert a['assertions']['ah'][0]['predicate']=='OPEN:глоркнул'
    assert {x['predicate'] for x in b['assertions']['ah']}=={'OPEN:глоркнул','OPEN:глоркнула'}
    assert b['open']['semantic_status']=='UNLINKED'
    token=next(t for t in b['runtime']['ir']['evidence'] if t['span']=='глоркнула')
    assert token['lemma']=='глоркнула' and token['variants']==[]
    assert not any(r.get('source_reading',{}).get('origin')=='PREDICTED'
                   for r in b['runtime']['ir']['syntax_trace'] if r.get('kind')=='MORPHOLOGY_PROPOSAL')
    from ah.core.persistence import JsonPersistence
    from ah.config import PersistenceSettings
    persistence=JsonPersistence(tmp_path/'memory.json',PersistenceSettings())
    persistence.save(session.core);restored=persistence.load().core
    assert restored.store.find_symbol_by_form('глоркнул').uid==symbol.uid
    assert restored.store.find_symbol_by_form('глоркнула').uid==other.uid
    assert not restored.store.find_symbols_by_form('глоркнуть')


def test_analyzer_predictions_never_enter_semantic_prompts(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Иван глоркнул книгу.',[function()]+relation('LEXICAL'))
    assert result['assertions']['ah'][0]['predicate']=='OPEN:глоркнул'
    evidence=next(t for t in result['runtime']['ir']['evidence'] if t['span']=='глоркнул')
    assert evidence['morph_guesses']  # the diagnostic channel remains available
    assert all('глоркнуть' not in p for _,p in script.calls)
    attachment=next(p for s,p in script.calls if s=='component_attachment')
    assert 'lemma unknown' in attachment


def test_oov_morphology_requires_contextual_function_evidence(tmp_path,monkeypatch):
    item=payload('Иван глоркнул книгу.','unresolved');session=Session([item],tmp_path/'journal')
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:'?')
    result=execute_native(session,item,CONFIG)
    assert not result['assertions']['ah']
    assert 'OOV_GRAMMAR_UNRESOLVED' in result['diagnostics']['codes']
    assert not session.core.store.find_symbols_by_form('глоркнуть')


@pytest.mark.parametrize('change',[{'lemma':'прочитать'},{'gender':'femn','number':'plur'}])
def test_predicted_lemma_and_features_cannot_change_the_interpretation(tmp_path,monkeypatch,change):
    original=MorphProvider.analyze
    def analyze(self,word):
        readings=original(self,word)
        return tuple(replace(v,**change) if v.origin=='PREDICTED' else v for v in readings) if word=='глоркнул' else readings
    monkeypatch.setattr(MorphProvider,'analyze',analyze)
    result,_=run(tmp_path,monkeypatch,'Иван глоркнул книгу.',[function()]+relation('LEXICAL'))
    assert result['assertions']['ah'][0]['predicate']=='OPEN:глоркнул'
    assert result['open']['semantic_status']=='UNLINKED'
    frames=[f for f in result['runtime']['ir']['frames'] if not f['semantic'].get('structural_unresolved')]
    assert frames
    for f in frames:
        reading=f['semantic']['morph_bindings'][f['predicate_token_ref']]
        assert reading['lemma']=='глоркнул' and reading['gender'] is None and reading['number'] is None


def test_surface_lexeme_keeps_negation_and_query_anchor(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван не глоркнул книгу.',
        [function()]+unary('NOT','не','не')+[function()]+relation('LEXICAL'))
    tree=result['assertions']['ah'][0]
    assert tree['operator']=='NOT' and tree['operands'][0]['predicate']=='OPEN:глоркнул'
    item=payload('Иван глоркнул книгу?','query','QUERY');session=Session([item],tmp_path/'query-journal')
    from tools import formalizer_v7_native_binding as binding
    from ah.formalizer.native_queries import project_native_queries
    interpret=binding.interpret_full;states=[]
    def capture(*args,**kwargs):
        result=interpret(*args,**kwargs);states.append(result[0]);return result
    monkeypatch.setattr(binding,'interpret_full',capture)
    answer,_=execute(session,item,[function()]+unary('QUERY','?','?')+[function()]+relation('LEXICAL'),monkeypatch)
    assert not answer['assertions']['ah'] and not session.core.store.find_symbols_by_form('глоркнуть')
    roots=project_native_queries(states[0],session.release)
    assert roots and {a['lexical_anchor'] for r in roots for a in r.atoms.values()}=={'глоркнул'}
    from types import SimpleNamespace
    from ah.formalizer.runtime_adapter import FormalizerAdapter
    state=states[0];frame=next(f for f in state.frames if not f.semantic.get('structural_unresolved'))
    value=state.decisions[frame.frame_id+'|predicate_value'].selected[0]
    projected=FormalizerAdapter._build_predicate(SimpleNamespace(_release=session.release),frame,state,value)
    assert projected.surface=='глоркнул' and projected.normalized_hint is None


def test_nominal_oov_preserves_mention_without_inventing_a_paradigm(tmp_path,monkeypatch):
    item=payload('Флырка пришла.','noun');session=Session([item],tmp_path/'nominal-journal')
    result,_=execute(session,item,[function('NOUN')]+relation('LEXICAL'),monkeypatch)
    assert result['assertions']['ah'][0]['predicate']=='ARRIVE'
    token=next(t for t in result['runtime']['ir']['evidence'] if t['span']=='Флырка')
    assert token['variants']==[] and token['lemma']=='флырка'
    symbol=session.core.store.find_symbol_by_form('флырка')
    assert symbol is not None and not session.core.store.find_symbols_by_form('флырке')
    bindings=list(session.store.ledger.data['bindings'].values())
    assert any(b.get('mention_ref')==token['token_id'] for b in bindings)


def test_surface_homograph_does_not_merge_distinct_paradigms(tmp_path):
    session=Session([],tmp_path/'journal')
    core=session.core
    def add(uid,surface,lemma=None):
        ensure_template(core,{'uid':uid,'predicate_form':surface,'predicate_lemma':lemma,
            'roles':['SUBJECT'],'semantic_status':'UNLINKED'})
        return core.store.get_template(uid).predicate.uid
    first=add('T:test:one','флырки','флырка')
    second=add('T:test:two','флырки','флырок')
    assert first!=second
    assert {s.uid for s in core.store.find_symbols_by_form('флырки')}=={first,second}
    third=add('T:test:three','флырке','флырка')
    assert third==first
    with pytest.raises(ValueError,match='Ambiguous wordform'):
        add('T:test:ambiguous','флырки')


def test_gui_distinguishes_predicted_lemma_from_unknown_lemma():
    from test_formalization_readable import sample,visible
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    data=sample()
    data['state']['syntax_trace']=[{'kind':'MORPHOLOGY_DOMAIN_RESTRICTION','token_ref':'read',
        'reading':{'lemma':'глоркнуть','pos':'VERB','gender':'femn','number':'sing','tense':'past'},
        'predicted_lemma':True}]
    inspection=Inspection(data);reader=ReadableInspection(inspection)
    explanation=visible(reader.explain(inspection.by_ref['trace:0']))
    assert 'Начальная форма «глоркнуть» (морфологическая гипотеза)' in explanation
    assert 'женский род' in explanation and 'прошедшее время' in explanation
    assert 'не устанавливает значение слова' in explanation
    unknown=reader.task_choice({'reading':{'lemma':'глоркнул','pos':'VERB'},'predicted_lemma':False})
    assert 'Лемма не установлена' in unknown and 'Начальная форма «глоркнул»' not in unknown
