"""Progress inventories retain raw evidence and explicit measurement limits."""
import json
from tools.audit_formalizer_probe_run import analyze_run,main,render,read_run
from ah.diagnostics.probe_catalog import LABEL_PROTOCOL,catalog_snapshot


PROMPT=('Decision slot: structural_partition\nOptions:\n1. One part\n2. Two parts\n'
        'Reply with the number of the supported option. Insufficient context: ?\n'
        'No candidate fits: 0')


def write_run(tmp_path,rows):
    path=tmp_path/'run.jsonl'
    path.write_text('\n'.join(json.dumps(row,ensure_ascii=False) for row in rows),encoding='utf-8')
    return path


def request(cid,rid,response,*,slot='structural_partition',audit=None,**end_fields):
    if audit is None:audit={'protocol':LABEL_PROTOCOL,'slot':slot,'candidates':['one','two']}
    return [{'event':'request_started','case_id':cid,'request_id':rid,'prompt':PROMPT,
             'selection_audit':audit},
            {'event':'request_finished','case_id':cid,'request_id':rid,'response':response,
             'status':'SUCCESS',**end_fields}]


def case(cid,status,*events):
    return [{'event':'case_started','case_id':cid},*events,
            {'event':'case_finished','case_id':cid,'status':status,'errors':[]}]


def test_inventory_exposes_clipped_reply_and_preserves_raw_evidence(tmp_path):
    prefix='The clause has a parent predicate. '+('analysis ' * 40)
    rows=[
        {'event':'step_started','case_id':'case','payload':{'raw_input':{'text':'Мария сказала: «Иван пришёл».'}}},
        {'event':'request_started','case_id':'case','request_id':'request',
         'prompt':'Decision slot: structural_parent_end\nOptions:\n1. End after «сказала»'},
        {'event':'request_finished','case_id':'case','request_id':'request',
         'response':prefix,'response_truncated':True,'response_chars':9000},
        {'event':'step_finished','case_id':'case','actual_truncated':True},
        {'event':'case_finished','case_id':'case','status':'FAIL','errors':[]}]
    path=tmp_path/'run.jsonl';path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows))
    report=render(path)
    assert 'Обрезанных ответов модели: 1' in report
    assert 'Ответ модели обрезан в выгрузке' in report
    assert 'Обрезанный ответ: полный ответ недоступен' in report
    assert 'Ответ не соответствует формату выбора' not in report
    assert prefix not in report
    assert read_run(path)[4]['case'][0]['response']==prefix
    summary=analyze_run(path)['summary']
    assert summary['selection_outcomes']['TRUNCATED']==1
    assert summary['selection_outcomes']['MALFORMED']==0


def test_inventory_separates_valid_choices_sentinels_errors_and_unknown_evidence(tmp_path):
    rows=[]
    for index,raw in enumerate(('1','1,2',' 0\n','\n?\t','999','1,1','0,1')):
        rows+=case(str(index),'PASS',*request(str(index),str(index),raw))
    rows+=case('http','FAIL',*request('http','http',None,status='ERROR',error='HTTP 503'))
    rows+=case('clipped','FAIL',*request('clipped','clipped','1',response_truncated=True))
    rows+=case('unknown','FAIL',*request('unknown','unknown','1',audit={
        'slot':'structural_partition','protocol':LABEL_PROTOCOL,
        'candidates':['one',{'_omitted_items':10}]}))
    report=analyze_run(write_run(tmp_path,rows))
    assert report['summary']['selection_outcomes']=={
        'CHOSEN_ONE':1,'CHOSEN_MULTIPLE':1,'NONE_FIT':1,'INSUFFICIENT_CONTEXT':1,
        'MALFORMED':3,'UNKNOWN_EVIDENCE':1,'TRUNCATED':1,'PROVIDER_ERROR':1,'UNFINISHED':0}
    rate=report['summary']['rates']['chosen_among_valid_label_replies']
    assert rate=={'numerator':2,'denominator':4,'value':0.5}
    multi=report['cases']['1']['request_records'][0]
    assert multi['value']==['one','two'] and multi['response']=='1,2'
    assert multi['label']=='One part; Two parts'
    assert report['cases']['unknown']['request_records'][0]['mapping_complete'] is False


def test_embedding_without_prompt_or_text_response_is_not_a_malformed_selection(tmp_path):
    rows=case('case','PASS',
        {'event':'request_started','case_id':'case','request_id':'embedding','role':'lexical_embedding'},
        {'event':'request_finished','case_id':'case','request_id':'embedding','role':'lexical_embedding','status':'SUCCESS'},
        *request('case','http','',http_status=502))
    path=write_run(tmp_path,rows)
    report=analyze_run(path)
    assert report['summary']['non_selection_records']==1
    assert report['summary']['selection_records']==1
    assert report['summary']['selection_outcomes']['MALFORMED']==0
    assert report['summary']['selection_outcomes']['PROVIDER_ERROR']==1
    assert 'Вызов EMBEDDING; SUCCESS' in render(path)


def test_all_steps_are_reported_while_legacy_read_run_returns_the_last_step(tmp_path):
    rows=case('case','FAIL',
        {'event':'step_started','case_id':'case','step_id':'first','payload':{'raw_input':{'text':'Первая фраза.'}}},
        *request('case','first','1'),
        {'event':'step_finished','case_id':'case','step_id':'first','actual_truncated':True},
        {'event':'step_started','case_id':'case','step_id':'second','payload':{'raw_input':{'text':'Вторая фраза.'}}},
        {'event':'step_finished','case_id':'case','step_id':'second','actual_truncated':True})
    path=write_run(tmp_path,rows)
    report=analyze_run(path)
    assert report['summary']['truncated_step_results']==2
    assert len(report['cases']['case']['input_records'])==2
    legacy=read_run(path)
    assert len(legacy)==5 and legacy[1]['case']=='Вторая фраза.'
    assert legacy[3]['case']['step_id']=='second'
    rendered=render(path)
    assert 'Первая фраза.' in rendered and 'Вторая фраза.' in rendered


def test_duplicates_conflicts_unmatched_records_and_reused_ids_do_not_inflate_calls(tmp_path):
    pair=request('case','same','1')
    conflict=request('case','conflict','1')
    other_start={**conflict[0],'selection_audit':{
        'protocol':LABEL_PROTOCOL,'slot':'structural_shared_material','candidates':['one','two']}}
    rows=case('case','FAIL',pair[0],pair[0],pair[1],pair[1],*conflict,other_start,
        {**conflict[1],'response':'?'},request('case','unfinished','1')[0],
        {'event':'request_finished','case_id':'case','request_id':'orphan','response':'?'},
        {'event':'request_started','case_id':'case','prompt':PROMPT},
        {'event':'request_finished','case_id':'case','response':'1'})
    rows+=case('other','PASS',*request('other','same','0'))
    path=write_run(tmp_path,rows)
    report=analyze_run(path)
    summary=report['summary']
    assert summary['request_started_events']==7 and summary['request_finished_events']==7
    assert summary['request_records']==7
    issues=report['completeness']['issue_counts']
    assert issues['duplicate_request_started']==1 and issues['duplicate_request_finished']==1
    assert issues['conflicting_request_started']==1 and issues['conflicting_request_finished']==1
    assert issues['unmatched_starts']==2 and issues['unmatched_finishes']==2
    assert issues['missing_request_ids']==2
    assert report['summary']['selection_outcomes']['CHOSEN_ONE']==1
    conflicting=next(r for r in report['request_records'] if r['request_id']=='conflict')
    assert conflicting['classification']['outcome']=='UNKNOWN_EVIDENCE'
    assert conflicting['classification']['selected_ids'] is None
    assert len(conflicting['start_records'])==2 and len(conflicting['end_records'])==2
    assert 'structural_shared_material' in report['coverage']['unregistered_observed']
    assert report['cases']['case']['conditional_bucket']=='WITHOUT_OBSERVED_QUESTION_INCOMPLETE'
    assert report['cases']['other']['conditional_bucket']=='WITHOUT_OBSERVED_QUESTION_COMPLETE'
    assert 'Нет записи завершения запроса.' in render(path)


def test_conditional_question_rates_have_explicit_zero_denominators_and_incomplete_bucket(tmp_path):
    rows=case('positive','PASS',*request('positive','positive','1'))
    rows+=case('orphan','FAIL',{'event':'request_finished','case_id':'orphan','request_id':'orphan','response':'?'})
    rows+=case('truncated','FAIL',*request('truncated','truncated','?',response_truncated=True))
    path=write_run(tmp_path,rows)
    metrics=analyze_run(path)['conditional_question_metrics']
    assert metrics['pass_given_observed_question']=={'numerator':0,'denominator':0,'value':None}
    assert metrics['table']['WITHOUT_OBSERVED_QUESTION_INCOMPLETE']=={'PASS':0,'FAIL':2}
    assert metrics['pass_given_no_observed_question_complete']['denominator']==1
    assert 'NA (0 знаменатель)' in render(path)
    rows+=case('question-pass','PASS',*request('question-pass','question-pass','?\n'))
    rows+=case('question-fail','FAIL',*request('question-fail','question-fail','?'))
    metrics=analyze_run(write_run(tmp_path,rows))['conditional_question_metrics']
    assert metrics['table']['WITH_OBSERVED_QUESTION']=={'PASS':1,'FAIL':1}
    assert metrics['pass_given_observed_question']=={'numerator':1,'denominator':2,'value':0.5}


def test_catalog_normalization_keeps_raw_names_and_separate_declared_contracts(tmp_path):
    catalog=catalog_snapshot()
    old=request('case','old','1',slot='structural_oov_reading')
    generic=request('case','generic','1',slot='structural_quantifier_kind')
    dynamic=request('case','dynamic','1',slot='structural_parent_end')
    dynamic[0]['semantic_contract']=catalog['source_collection']
    clipped=request('case','clipped','1',audit={'protocol':LABEL_PROTOCOL,'candidates':['one','two']})
    clipped[0].update(prompt='Decision slot: structural_group_next\nOptions:\n1. incomplete',prompt_truncated=True)
    report=analyze_run(write_run(tmp_path,case('case','PASS',*old,*generic,*dynamic,*clipped)))
    assert report['slots']['structural_oov_function']['raw_slots']==['structural_oov_reading']
    assert report['coverage']['registry_denominator']==len(catalog['slots'])
    assert report['coverage']['registered_family_denominator']==15
    assert report['coverage']['slots']['reference']['status']=='NOT_OBSERVED_IN_EXPORT'
    assert report['coverage']['unregistered_observed']==['structural_group_next','structural_quantifier_kind']
    assert report['coverage']['dynamic_source_collection']==['structural_parent_end']


def test_missing_case_binding_and_export_gaps_are_visible_and_json_cli_is_reproducible(tmp_path):
    pair=request('case','request','1')
    del pair[1]['case_id']
    rows=[{'event':'run_started'},*case('case','PASS',*pair),{'event':'run_finished'}]
    for n,row in enumerate(rows,1):row['seq']=n
    rows[-1]['seq']+=1
    rows[-1]['requests_finished']=2
    path=write_run(tmp_path,rows)
    path.write_text(path.read_text(encoding='utf-8')+'\n{partial',encoding='utf-8')
    report=analyze_run(path)
    assert len(report['cases']['case']['request_records'])==1
    assert report['cases']['case']['conditional_bucket']=='WITHOUT_OBSERVED_QUESTION_INCOMPLETE'
    issues=report['completeness']['issue_counts']
    assert issues['invalid_json_rows']==1 and issues['sequence_gaps']==1
    assert issues['request_counter_mismatch']==1
    assert 'unmatched_finishes' not in issues
    md=tmp_path/'output'/'report.md';measurements=tmp_path/'output'/'report.json'
    main([str(path),'--out',str(md),'--json-out',str(measurements)])
    saved=json.loads(measurements.read_text(encoding='utf-8'))
    assert saved['summary']==report['summary']
    assert saved['source']==report['source']
    assert saved['catalog']==report['catalog']
    assert saved['request_records'][0]['response']=='1'
    assert 'NOT_OBSERVED_IN_EXPORT' in md.read_text(encoding='utf-8')
