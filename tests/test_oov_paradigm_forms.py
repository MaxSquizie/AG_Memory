"""Productive morphology must survive the real native write/query boundary."""
from dataclasses import replace

import pytest

from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.graph_ops import ensure_template
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from test_structural_relation_tasks import Script,relation,run,unary


CONFIG={'provider':'lmstudio','model':'scripted-oov','structure_mode':'region_probes'}


def predicted(word,lemma):
    return ('structural_oov_reading','Source «'+word+'»: predicted inflection; lemma: '+lemma+'; pos: conjugated verb')


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


def test_native_two_observed_forms_extend_one_symbol_without_merging_open_events(tmp_path,monkeypatch):
    first=payload('Иван глоркнул книгу.','first')
    second=payload('Мария глоркнула книгу.','second')
    session=Session([first,second],tmp_path/'journal')
    a,_=execute(session,first,[predicted('глоркнул','глоркнуть')]+relation('LEXICAL'),monkeypatch)
    symbols=session.core.store.find_symbols_by_form('глоркнуть')
    assert len(symbols)==1
    uid=symbols[0].uid
    before=set(session.store.ledger.data['nodes'])
    b,_=execute(session,second,[predicted('глоркнула','глоркнуть')]+relation('LEXICAL'),monkeypatch)
    symbol=session.core.store.get_symbol(uid)
    assert {'глоркнуть','глоркнул','глоркнула'}<=set(symbol.forms)
    assert session.core.store.find_symbol_by_form('глоркнула').uid==uid
    assert before<set(session.store.ledger.data['nodes'])
    assert len(session.core.store.find_templates_by_predicate(uid))==2
    assert a['assertions']['ah'][0]['predicate']=='OPEN:глоркнуть'
    assert len(b['assertions']['ah'])==2
    assert all(x['predicate']=='OPEN:глоркнуть' for x in b['assertions']['ah'])
    assert b['open']['semantic_status']=='UNLINKED'
    assert session.native_ignition.core.store.runtime_state(uid).excitation>0
    ir=b['runtime']['ir']
    token=next(t for t in ir['evidence'] if t['span']=='глоркнула')
    assert token['lemma']=='глоркнула' and token['variants']==[]  # source evidence stays immutable
    assert any(row.get('kind')=='MORPHOLOGY_USE' and row['reading']['lemma']=='глоркнуть'
               for row in ir['syntax_trace'])
    from ah.core.persistence import JsonPersistence
    from ah.config import PersistenceSettings
    persistence=JsonPersistence(tmp_path/'memory.json',PersistenceSettings())
    persistence.save(session.core)
    restored=persistence.load().core
    assert restored.store.get_symbol(uid).forms==symbol.forms
    assert restored.store.find_symbol_by_form('глоркнула').uid==uid
    assert len(restored.store.find_templates_by_predicate(uid))==2


def test_unknown_lemma_remains_valid_even_when_analyzer_has_prediction(tmp_path,monkeypatch):
    item=payload('Иван глоркнул книгу.','unknown-lemma')
    session=Session([item],tmp_path/'journal')
    result,script=execute(session,item,[('structural_oov_reading','Source «глоркнул»: VERB;')]+relation('LEXICAL'),monkeypatch)
    assert result['assertions']['ah'][0]['predicate']=='OPEN:глоркнул'
    assert not session.core.store.find_symbols_by_form('глоркнуть')
    assert session.core.store.find_symbol_by_form('глоркнул')
    p=next(p for slot,p in script.calls if slot=='structural_oov_reading')
    assert 'lemma and all other unsupported features remain unknown' in p
    assert 'predicted inflection; lemma: глоркнуть' in p


def test_oov_morphology_is_not_an_unconditional_lemma_or_sense_selection(tmp_path,monkeypatch):
    # Even a high-score singleton prediction needs a selected reading.
    item=payload('Иван глоркнул книгу.','unresolved')
    session=Session([item],tmp_path/'journal')
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:'?')
    result=execute_native(session,item,CONFIG)
    assert not result['assertions']['ah']
    assert 'OOV_GRAMMAR_UNRESOLVED' in result['diagnostics']['codes']
    assert not session.core.store.find_symbols_by_form('глоркнуть')


def test_predicted_lemma_cannot_assign_a_known_dictionary_sense(tmp_path,monkeypatch):
    original=MorphProvider.analyze
    def analyze(self,word):
        readings=original(self,word)
        return tuple(replace(v,lemma='прочитать') for v in readings) if word=='глоркнул' else readings
    monkeypatch.setattr(MorphProvider,'analyze',analyze)
    result,_=run(tmp_path,monkeypatch,'Иван глоркнул книгу.',
        [predicted('глоркнул','прочитать')]+relation('LEXICAL'))
    assert result['assertions']['ah'][0]['predicate']=='OPEN:прочитать'
    assert result['open']['semantic_status']=='UNLINKED'


def test_selected_prediction_still_has_to_satisfy_agreement(tmp_path,monkeypatch):
    original=MorphProvider.analyze
    def analyze(self,word):
        readings=original(self,word)
        return tuple(replace(v,gender='femn') for v in readings) if word=='глоркнул' else readings
    monkeypatch.setattr(MorphProvider,'analyze',analyze)
    item=payload('Иван глоркнул книгу.','wrong-agreement')
    session=Session([item],tmp_path/'journal')
    script=Script([predicted('глоркнул','глоркнуть')]+relation('LEXICAL'))
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:
        script.generate(prompt,**kw) if script.steps else '?')
    result=execute_native(session,item,CONFIG)
    assert not script.steps and not script.errors
    assert not result['assertions']['ah']
    assert not session.core.store.find_symbols_by_form('глоркнуть')


def test_selected_lemma_keeps_negation_and_query_anchor(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Иван не глоркнул книгу.',
        [predicted('глоркнул','глоркнуть')]+unary('NOT','не','не')+relation('LEXICAL'))
    tree=result['assertions']['ah'][0]
    assert tree['operator']=='NOT' and tree['operands'][0]['predicate']=='OPEN:глоркнуть'
    item=payload('Иван глоркнул книгу?','query','QUERY')
    session=Session([item],tmp_path/'query-journal')
    from tools import formalizer_v7_native_binding as binding
    from ah.formalizer.native_queries import project_native_queries
    interpret=binding.interpret_full
    states=[]
    def capture(*args,**kwargs):
        result=interpret(*args,**kwargs)
        states.append(result[0])
        return result
    monkeypatch.setattr(binding,'interpret_full',capture)
    answer,_=execute(session,item,[predicted('глоркнул','глоркнуть')]+unary('QUERY','?','?')+relation('LEXICAL'),monkeypatch)
    assert not answer['assertions']['ah']
    # The real query compiler sees the selected lemma, but never writes its S.
    assert not session.core.store.find_symbols_by_form('глоркнуть')
    roots=project_native_queries(states[0],session.release)
    assert roots and {a['lexical_anchor'] for r in roots for a in r.atoms.values()}=={'глоркнуть'}
    assert answer['generation']['observed_candidate_patterns'][0]['predicate']=='OPEN:глоркнуть'
    from types import SimpleNamespace
    from ah.formalizer.runtime_adapter import FormalizerAdapter
    state=states[0];frame=state.frames[0]
    value=state.decisions[frame.frame_id+'|predicate_value'].selected[0]
    projected=FormalizerAdapter._build_predicate(SimpleNamespace(_release=session.release),frame,state,value)
    assert projected.surface=='глоркнул' and projected.normalized_hint=='глоркнуть'


def test_nominal_oov_adds_case_forms_without_equating_entities(tmp_path,monkeypatch):
    first=payload('Флырка читает книгу.','noun-first')
    second=payload('Иван передал книгу флырке.','noun-second')
    session=Session([first,second],tmp_path/'nominal-journal')
    a,_=execute(session,first,[('structural_oov_reading',
        'Source «Флырка»: predicted inflection; lemma: флырка; pos: noun; cases: nominative; number: singular; gender: feminine')]+relation('LEXICAL'),monkeypatch)
    symbol=session.core.store.find_symbol_by_form('флырка')
    assert symbol is not None
    b,_=execute(session,second,[('structural_oov_reading',
        'Source «флырке»: predicted inflection; lemma: флырка; pos: noun; cases: dative')]+relation('LEXICAL'),monkeypatch)
    assert session.core.store.find_symbol_by_form('флырке').uid==symbol.uid
    assert a['assertions']['ah'] and b['assertions']['ah']
    # Lexical identity of a noun does not decide reference identity of its mentions.
    bindings=list(session.store.ledger.data['bindings'].values())
    targets=[]
    for result,word in ((a,'Флырка'),(b,'флырке')):
        ir=result['runtime']['ir']
        tid=next(t['token_id'] for t in ir['evidence'] if t['span']==word)
        targets.append(next(row['target_ref'] for row in bindings
            if row.get('mention_ref')==tid and row['source_tag'][0]==ir['source_uid']))
    assert targets[0]!=targets[1]


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
