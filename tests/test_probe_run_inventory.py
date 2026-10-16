"""Audit exports must not present a clipped answer as complete evidence."""
import json
from tools.audit_formalizer_probe_run import render,read_run


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
    assert 'Ответ не соответствует формату выбора' in report
    assert prefix not in report
    assert read_run(path)[4]['case'][0]['response']==prefix
