from copy import deepcopy
import re

from ah.gui.formalization_inspection import Inspection
from ah.gui.formalization_readable import ReadableInspection


def sample():
    return {'source_text':'Каждый студент читает книгу.',
        'state':{'evidence':[{'token_id':'student','span':'студент','start':7,'end':14},
            {'token_id':'read','span':'читает','start':15,'end':21}],
            'frames':[{'frame_id':'action','anchor_span':'читает','predicate_token_ref':'read','source_range':[15,21],
                'semantic':{'bound_arguments':{'student':2},'implicit_arguments':{'SUBJECT':{'gap_id':'gap'}}}}],
            'observation':{'implicit_bindings':{'gap':{'bound_var':2}}},
            'decisions':{'gap':{'frame_id':'gap','slot_id':'implicit_argument','outcome':'RESOLVED','candidates':['a','b'],'selected':['b'],
                'last_prompt':'1. Unidentified referent for SUBJECT\n2. Same bound variable v2 as студент; reuse\n1 = "a"\n2 = "b"',
                'raw_response':'2'}},'syntax_trace':[]},
        'commit_receipt':{'terminal':'APPLIED','committed_fragments':['root']},
        'committed_graph':{'receipt_refs':['root'],'entities':{'M:book':{'name':'книгу'}},'nodes':{
            'root':{'function_id':'NOT','operands':['quantifier']},
            'quantifier':{'function_id':'FORALL','operands':[{'bound_var':2},'action-node']},
            'action-node':{'source_ref':'read','semantic_status':'UNLINKED',
                'actants':{'SUBJECT':{'bound_var':2},'OBJECT':'M:book'}}}}}


def visible(html):
    return re.sub('<[^>]+>',' ',html)


def test_nominal_predication_choices_are_explained_in_russian():
    reader=ReadableInspection(Inspection(sample()))
    clause=reader.task_choice({'candidate_id':'PROPOSITION','label':
        'A complete clause: a predicate describes a participant, possibly without an explicit verb'})
    assert 'Полное высказывание' in clause and 'глагол может отсутствовать' in clause
    candidate=reader.choice_text('врач [NOUN]; SUBJECT=Мария; noun predicate: «врач» describes what «Мария» is')
    assert 'Именное сказуемое «врач» характеризует «Мария»' in candidate
    assert 'предложенный разбор' in candidate and 'NOUN' not in candidate


def test_lost_parent_and_impersonal_state_are_explained_without_machine_fields():
    data=sample();data['state']['syntax_trace']=[
        {'kind':'STRUCTURAL_PARTITION_COVERAGE','uncovered_token_refs':['student','read']},
        {'kind':'DEPENDENCY_REJECTED','predicate_ref':'read','empty_domains':['student']}]
    idx=Inspection(data);reader=ReadableInspection(idx)
    html=reader.explain(idx.by_ref['trace:0'])
    assert 'Разбиение потеряло значимые слова: «студент читает»' in html
    assert 'запись вложенной части отдельно заблокирована' in html
    assert 'uncovered_token_refs' not in html
    rejected=reader.explain(idx.by_ref['trace:1'])
    assert 'грамматические ограничения' in rejected and 'отдельного варианта' in rejected
    label=reader.choice_text('холодно [ADVB]; EXPERIENCER=Мне; impersonal state; dative participant experiences it; no separate grammatical subject')
    assert 'Безличное состояние' in label and 'дательном падеже' in label
    assert 'ADVB' not in label and 'impersonal' not in label


def test_structural_tasks_explain_frontier_parts_and_limit_without_json():
    data=sample();data['state']['syntax_trace']=[
        {'kind':'STRUCTURAL_TASK','slot':'structural_partition','decision_ref':'partition',
         'source_range':[0,26],'page':1,'examined':18,'status':'SELECTED','selected':'p',
         'alternatives':[{'candidate_id':'p','relation':'IMPLIES','operands':[['student'],['read']],
            'marker_refs':[],'label':'machine wording'}]},
        {'kind':'STRUCTURAL_TASK','slot':'structural_relation','source_range':[0,26],
         'status':'BLOCKED','reason':'CONTEXT_LIMIT','examined':0}]
    idx=Inspection(data);reader=ReadableInspection(idx)
    chosen=visible(reader.explain(idx.by_ref['trace:0']))
    assert 'Части по порядку: «студент»; «читает»' in chosen
    assert 'Локальный выбор подтверждён' in chosen and 'Порция: 2' in chosen
    assert 'machine wording' not in chosen and 'marker_refs' not in chosen
    blocked=visible(reader.explain(idx.by_ref['trace:1']))
    assert 'Проба не вызывалась' in blocked
    assert 'Проба не вызывалась' in reader.report([])


def test_actual_graph_preserves_negation_scope_variables_and_unknown_meaning():
    data=sample();before=deepcopy(data);r=ReadableInspection(Inspection(data));html=r.overview()
    assert html.index('Неверно, что')<html.index('Для каждого')<html.index('«читает»')
    assert '«студент», переменная 2' in html and 'книгу' in html
    assert 'Словарный смысл этого слова не установлен' in html
    assert 'M:book' not in visible(html) and 'bound_var' not in visible(html)
    assert data==before
    data['committed_graph']['nodes']['root']={'function_id':'FORALL','operands':[{'bound_var':2},'quantifier']}
    data['committed_graph']['nodes']['quantifier']={'function_id':'NOT','operands':['action-node']}
    changed=ReadableInspection(Inspection(data)).overview()
    assert changed.index('Для каждого')<changed.index('Неверно, что')


def test_choices_use_recorded_mapping_and_never_invent_reasoning():
    data=sample();idx=Inspection(data);r=ReadableInspection(idx);d=data['state']['decisions']['gap']
    rows=r.choices(d)
    assert 'Неустановленный' in rows[0][1] and rows[0][2]=='Не выбран'
    assert 'Тот же связанный участник' in rows[1][1] and rows[1][2]=='Выбран'
    assert 'Объяснение её рассуждений не записано' in r.decision(d)
    assert idx.by_ref['gap'].source_range==[15,21]
    d['last_prompt']='1. text without a label map'
    assert all('Описание варианта не сохранено' in row[1] for row in r.choices(d))


def test_proposition_content_trace_is_readable_and_preserves_confirmation():
    data=sample()
    data['state']['syntax_trace']=[{'kind':'ATTITUDE_COMPOSITION','parent_anchor':'read',
        'content_range':[7,14],'resolved':True,'delimiter_scope':{'marker_ref':'student'}}]
    idx=Inspection(data);reader=ReadableInspection(idx)
    html=reader.explain(idx.by_ref['trace:0'])
    assert 'Вложенное содержание связано' in html and 'читает' in html and 'студент' in html
    assert 'не утверждается как самостоятельный факт' in html
    data['state']['syntax_trace'][0]['resolved']=False
    assert 'завершение связи не подтверждено' in reader.explain(idx.by_ref['trace:0'])
    label='Proposition content «Пётр пришёл» fills OBJECT of «сказал»; holder role SUBJECT; attitude=QUOTED; remaining parent «Иван сказал»; the content is NOT independently asserted'
    assert reader.choice_text(label).startswith('Содержание «Пётр пришёл» относится к «сказал»')


def test_invalid_model_reply_is_explained_without_confirming_choice():
    data=sample();d=data['state']['decisions']['gap']
    d.update(outcome='UNRESOLVED',selected=[],raw_response='ONE_SELECTED',
             history=[{'kind':'PROBE_FAILURE','error_type':'ProtocolError',
                       'message':'malformed SELECT_LABELS_V1 reply'}])
    html=ReadableInspection(Inspection(data)).decision(d)
    assert 'Ответ модели: ONE_SELECTED' in html
    assert 'Ответ отклонён из-за нарушения формата протокола' in html
    assert 'Выбор не подтверждён' in html


def test_report_escapes_source_comments_and_has_no_app_links():
    data=sample();data['source_text']='<script>alert(1)</script>'
    report=ReadableInspection(Inspection(data)).report([{'comment':'<img src=x>','verdict':'Ошибка'}])
    assert '<script>' not in report and '<img src=x>' not in report
    assert '&lt;script&gt;' in report and '&lt;img src=x&gt;' in report
    assert 'href="review:' not in report and 'Замечания проверяющего' in report


def test_missing_graph_is_explicit_and_cycles_are_bounded():
    data=sample();data.pop('committed_graph')
    assert 'Записанный граф отсутствует' in ReadableInspection(Inspection(data)).overview()
    data=sample();data['committed_graph']['nodes']['root']['operands']=['root']
    assert 'Повторная ссылка' in ReadableInspection(Inspection(data)).overview()


def test_constraint_exclusions_show_recorded_reason_and_alternative():
    data=sample();trace={'kind':'SCOPE_DOMAIN','constraint_state':{'domains':{'slot':['a']},
        'removals':[{'variable_ref':'slot','removed':['b'],'reason':'RESOLVED_SCOPE_EDGE'}]},
        'values':{'slot':{'a':{'label':'NOT «не» applies to «читает»'},'b':{'label':'NOT «не» applies to «книгу»'}}}}
    data['state']['syntax_trace']=[trace];idx=Inspection(data);r=ReadableInspection(idx)
    html=r.explain(idx.by_ref['trace:0'])
    assert 'область' in html.lower() and '«книгу»' in html and 'предыдущим решением' in html


def test_graph_observer_captures_names_only_for_addressed_entities():
    from types import SimpleNamespace
    from ah.formalizer.diagnostic_graph import capture
    looked_up=[]
    def get(ref):
        looked_up.append(ref)
        return SimpleNamespace(properties={'name':SimpleNamespace(value='книга')},meta={'mention_ref':'book'})
    store=SimpleNamespace(ledger=SimpleNamespace(data={'nodes':{'root':{'actants':{'OBJECT':'M:book'}}}}),
        _store=SimpleNamespace(get_element_any_domain=get))
    result=capture(store,['root'])
    assert looked_up==['M:book'] and result['entities']['M:book']['name']=='книга'
    assert set(result['nodes'])=={'root'}
