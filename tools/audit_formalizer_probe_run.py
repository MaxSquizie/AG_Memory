"""Inventory a progress export without treating abstention as a root cause.

Supports the historical inline label map and the separate selection_audit.
Never calls a model, repairs an answer, or infers omitted runtime state.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
from ah.diagnostics.probe_catalog import (
    OUTCOMES, VALID_OUTCOMES, catalog_snapshot, classify_reply,
    displayed_choices, evidence_clipped, resolve_slot,
)


SLOTS={
    'structural_relation':'Внешняя связь', 'structural_revision':'Пересмотр разбора',
    'child_slot':'Дочерняя интерпретация', 'structural_partition':'Проверка разбиения',
    'structural_governor':'Управление модальным содержанием',
    'structural_function_owner':'Принадлежность служебного слова',
    'structural_event_head':'Высказывание или название события',
    'nominal_dependency':'Именная зависимость', 'nominal_coordination':'Однородные участники',
    'nominal_attachment':'Присоединение именной группы',
    'component_attachment':'Состав и чтение конструкции',
    'modifier_scope':'Область модификатора', 'source_assertion':'Утверждаемость содержания',
    'structural_owner':'Предикат — владелец содержания',
    'structural_content_role':'Роль и статус вложенного содержания',
    'structural_oov_reading':'Грамматическое чтение неизвестного слова',
    'structural_oov_function':'Грамматическая функция неизвестного слова',
    'relation_marker_role':'Слова связи или содержимое действия',
}
for key,label in [('structural_introducer','Вводящее выражение'),('structural_content','Вложенное содержание'),
                  ('structural_operand_1','Первая часть'),('structural_operand_2','Вторая часть'),
                  ('structural_parent','Родительская часть'),('structural_quantifier','Квантор')]:
    SLOTS[key+'_start']=label+': начало'
    SLOTS[key+'_end']=label+': конец'

RELATIONS={'LEXICAL':'Одна предикация / именное описание','NOT':'Отрицание','POSSIBLE':'Возможность',
    'NECESSARY':'Необходимость','AND':'Совместное выполнение','OR':'Включающее «или»',
    'XOR':'Исключающее «или»','IMPLIES':'Условие → следствие','COUNTERFACTUAL':'Контрфактическое условие',
    'BEFORE':'Раньше','AFTER':'Позже','DURING':'Во время','CONTENT':'Пропозициональное содержание',
    'FORALL':'Всеобщность','EXISTS':'Существование','QUERY':'Вопрос','GROUP':'Группа в скобках'}


def escape(value):
    return str(value).replace('|','\\|').replace('\n',' ')


def _unique_rows(rows):
    unique=[];seen=set()
    for row in rows:
        encoded=json.dumps({k:v for k,v in row.items() if k!='_line'},sort_keys=True)
        if encoded not in seen:unique.append(row);seen.add(encoded)
    return unique


def _request(start,end,*,case_id,catalog,identity_ambiguous=False):
    beginning=start or {};ending=end or {}
    prompt=beginning.get('prompt');audit=beginning.get('selection_audit',{})
    audit=audit if isinstance(audit,dict) else {}
    if beginning.get('selection_audit_truncated') or 'selection_audit' in (beginning.get('_omitted_progress_fields') or ()):
        audit={**audit,'_omitted_fields':True}
    prompt_complete=isinstance(prompt,str) and not beginning.get('prompt_truncated',False)
    # A clipped prompt can still contain a complete first-line slot address.
    matched=re.search(r'(?m)^Decision slot: ([^\s]+)(?=\r?\n'+('|$' if prompt_complete else '')+')',prompt) if isinstance(prompt,str) else None
    slot=audit.get('slot')
    raw_slot=(slot if isinstance(slot,str) and not audit.get('slot_truncated') else None) or (matched.group(1) if matched else None)
    names=resolve_slot(raw_slot,catalog,beginning.get('semantic_contract') or audit.get('semantic_contract'))
    role=beginning.get('role',ending.get('role'))
    kind='EMBEDDING' if role=='lexical_embedding' else 'SELECTION' if raw_slot or audit.get('protocol') else 'OTHER_PROVIDER_CALL'
    error=ending.get('error')
    if ending.get('status')=='ERROR' and not error:error='provider reported ERROR'
    if type(ending.get('http_status')) is int and ending['http_status']>=400 and not error:
        error='HTTP '+str(ending['http_status'])
    response=ending.get('response')
    classified=classify_reply(response,audit=audit,prompt=prompt,prompt_complete=prompt_complete,
        response_present='response' in ending,response_truncated=bool(ending.get('response_truncated')),
        provider_error=error,unfinished=end is None)
    if identity_ambiguous:
        classified.update(outcome='UNKNOWN_EVIDENCE',reason='CONFLICTING_REQUEST_ID_RECORDS',
                          selected_ids=None,mapping_complete=False)
    labels,inline=displayed_choices(prompt)
    candidates=audit.get('candidates')
    mapping=({str(n):v for n,v in enumerate(candidates,1)}
        if isinstance(candidates,(list,tuple)) and all(isinstance(v,str) for v in candidates) else inline)
    normalized=classified['normalized_response']
    values=classified['selected_ids']
    value=values[0] if values and len(values)==1 else values if values else normalized
    chosen_labels=[labels.get(n,n) for n in classified['selected_labels']]
    label='; '.join(chosen_labels) if chosen_labels else normalized
    return {**names,'case_id':case_id,'request_id':beginning.get('request_id',ending.get('request_id')),
        'step_id':beginning.get('step_id',ending.get('step_id')),'record_kind':kind,
        'transport_status':'UNFINISHED' if end is None else 'ERROR' if error else ending.get('status','NOT_RECORDED'),
        'slot':names['canonical_slot'] or 'OTHER_PROVIDER_CALL','value':value,'label':label,
        'response':response,'start':start,'end':end,'labels':labels,'mapping':mapping,
        'mapping_complete':classified['mapping_complete'],'classification':classified}


def _stream_gaps(rows,issues):
    """Check recorded sequence/counters, without inventing missing operations."""
    sequenced=[r for r in rows if type(r.get('seq')) is int]
    if sequenced:
        previous=0
        for row in sequenced:
            current=row['seq']
            if current>previous+1:
                issues['sequence_gaps'].append({'line':row['_line'],'first_missing':previous+1,'last_missing':current-1})
            elif current<=previous:
                issues['sequence_not_increasing'].append({'line':row['_line'],'previous':previous,'seq':current})
            previous=max(previous,current)
        if len(sequenced)!=len(rows):
            issues['sequence_missing'].append({'count':len(rows)-len(sequenced)})
    for event,counter in (('request_started','requests_started'),('request_finished','requests_finished')):
        declared=[r[counter] for r in rows if type(r.get(counter)) is int]
        observed=len(_unique_rows([r for r in rows if r['event']==event]))
        if declared and max(declared)!=observed:
            issues['request_counter_mismatch'].append({'counter':counter,'max_recorded':max(declared),'observed_unique_events':observed})


def _read(path,catalog):
    rows=[];inputs={};finished={};steps={};requests=defaultdict(list)
    input_records=[];step_records=[];case_finishes=defaultdict(list);request_events=[]
    issues=defaultdict(list)
    source_bytes=path.read_bytes()
    for lineno,line in enumerate(source_bytes.decode('utf-8').splitlines(),1):
        if not line.strip():continue
        try:row=json.loads(line)
        except ValueError as exc:
            issues['invalid_json_rows'].append({'line':lineno,'reason':str(exc)});continue
        if not isinstance(row,dict) or not isinstance(row.get('event'),str):
            issues['invalid_event_rows'].append({'line':lineno});continue
        row={**row,'_line':lineno};rows.append(row);kind=row['event'];cid=row.get('case_id')
        if kind in {'request_started','request_finished'}:request_events.append(row)
        elif kind=='step_started':
            payload=row.get('payload');raw=payload.get('raw_input',{}) if isinstance(payload,dict) else {}
            text=raw.get('text','') if isinstance(raw,dict) else ''
            inputs[cid]=text
            input_records.append({'case_id':cid,'step_id':row.get('step_id'),'line':lineno,'text':text})
        elif kind=='step_finished':steps[cid]=row;step_records.append(row)
        elif kind=='case_finished':case_finishes[cid].append(row)
    _stream_gaps(rows,issues)
    request_cases=defaultdict(set)
    for row in request_events:
        if isinstance(row.get('request_id'),str) and row.get('case_id') is not None:
            request_cases[row['request_id']].add(row['case_id'])
    buckets=defaultdict(lambda:{'request_started':[],'request_finished':[]})
    for row in request_events:
        rid=row.get('request_id');cid=row.get('case_id')
        if cid is None and isinstance(rid,str) and len(request_cases[rid])==1:
            cid=next(iter(request_cases[rid]))
        elif cid is None and isinstance(rid,str) and len(request_cases[rid])>1:
            issues['ambiguous_request_case'].append({'request_id':rid,'line':row['_line']})
        if not isinstance(rid,str) or not rid:
            issues['missing_request_ids'].append({'line':row['_line'],'event':row['event']})
            key=(cid,('missing',row['_line']))
        else:key=(cid,rid)
        buckets[key][row['event']].append(row)
    for (cid,rid),events in buckets.items():
        unique={kind:_unique_rows(values) for kind,values in events.items()}
        for kind,values in events.items():
            duplicate_count=len(values)-len(unique[kind])
            if duplicate_count:
                issues['duplicate_'+kind].append({'case_id':cid,'request_id':rid,
                    'count':duplicate_count,'lines':[r['_line'] for r in values]})
            if len(unique[kind])>1:
                issues['conflicting_'+kind].append({'case_id':cid,'request_id':rid,
                    'lines':[r['_line'] for r in values]})
        starts=unique['request_started'];ends=unique['request_finished']
        start=starts[0] if starts else None;end=ends[0] if ends else None
        if not start:issues['unmatched_finishes'].append({'case_id':cid,'request_id':rid,'line':end['_line']})
        if not end:issues['unmatched_starts'].append({'case_id':cid,'request_id':rid,'line':start['_line']})
        if cid is None:issues['unattributed_requests'].append({'request_id':rid,'line':(start or end)['_line']})
        record=_request(start,end,case_id=cid,catalog=catalog,identity_ambiguous=len(starts)>1 or len(ends)>1)
        record['identity_ambiguous']=len(starts)>1 or len(ends)>1
        record['start_records']=starts
        record['end_records']=ends
        names=('raw_slot','canonical_slot','registry_status','family')
        views=[record]+[_request(row,None,case_id=cid,catalog=catalog) for row in starts[1:]]
        record['observed_slots']=[{name:view[name] for name in names} for view in views if view['raw_slot']]
        requests[cid].append(record)
    for cid,records in requests.items():
        records.sort(key=lambda r:min(row['_line'] for row in (r['start'],r['end']) if row))
    for cid,records in case_finishes.items():
        unique=_unique_rows(records);finished[cid]=unique[0]
        if len(records)>len(unique):issues['duplicate_case_finished'].append({'case_id':cid,'count':len(records)-len(unique)})
        if len({row.get('status') for row in unique})>1:
            issues['conflicting_case_finished'].append({'case_id':cid,'lines':[r['_line'] for r in records]})
            finished[cid]={**finished[cid],'status':'UNKNOWN_EVIDENCE'}
    return {'source_sha256':hashlib.sha256(source_bytes).hexdigest(),
            'rows':rows,'inputs':inputs,'finished':finished,'steps':steps,'requests':requests,
            'input_records':input_records,'step_records':step_records,'issues':dict(issues)}


def read_run(path):
    """Keep the original five-item API; enriched request records retain raw bytes.

    The legacy input/step dictionaries still expose the last step per case.
    analyze_run/render use all input_records/step_records for their counts.
    """
    result=_read(path,catalog_snapshot())
    return tuple(result[key] for key in ('rows','inputs','finished','steps','requests'))


def selected_text(request):
    response=request['response'];value=request['value'];label=request['label'] or ''
    status=request['classification']['outcome'];reason=request['classification']['reason']
    preview=str(response or '')[:180].replace('\n',' ').replace('\r',' ').rstrip()
    if request['record_kind']!='SELECTION':return 'Вызов '+request['record_kind']+'; '+request['transport_status']
    if status=='INSUFFICIENT_CONTEXT':return 'Недостаточно контекста (?)'
    if status=='NONE_FIT':return 'Ни один показанный вариант не подошёл (0)'
    if status=='TRUNCATED':return 'Обрезанный ответ: полный ответ недоступен. Сохранённое начало: '+preview
    if status=='PROVIDER_ERROR':return 'Ошибка провайдера: '+str(request['classification'].get('provider_error',''))
    if status=='UNFINISHED':return 'Нет записи завершения запроса.'
    if status=='UNKNOWN_EVIDENCE':return 'Недостаточно записанного evidence для проверки ('+reason+'). Ответ: '+preview
    if status=='MALFORMED':return 'Ответ не соответствует формату выбора ('+reason+'). Начало ответа: '+preview
    if request['slot']=='structural_relation':
        values=value if isinstance(value,list) else [value]
        return '; '.join(RELATIONS.get(v,str(v)) for v in values)
    if request['slot'].endswith('_start'):
        return label.replace('Start at','Начать с')
    if request['slot'].endswith('_end'):
        return label.replace('End after','Закончить после').replace('full content','выбранный фрагмент').replace('selected words','выбранные слова')
    if request['slot']=='child_slot':return label.split('; linked morphology=')[0]
    if request['slot'] in {'nominal_dependency','component_attachment'}:
        return label.split('; whole reading=')[0].split('; linked morphology=')[0]
    return label


def differs_only_in_open_labels(expected,observed):
    """Audit classification only: never changes gold checks or memory identity."""
    def structure(value):
        if isinstance(value,list):return [structure(v) for v in value]
        if isinstance(value,dict):return {k:('OPEN:<label>' if k=='predicate' and
            isinstance(v,str) and v.startswith('OPEN:') else structure(v)) for k,v in value.items()}
        return value
    return expected!=observed and structure(expected)==structure(observed)


def _rate(numerator,denominator):
    return {'numerator':numerator,'denominator':denominator,
            'value':numerator/denominator if denominator else None}


def _outcomes(records):
    counts=Counter(r['classification']['outcome'] for r in records)
    return {name:counts[name] for name in OUTCOMES}


def _rates(counts):
    valid=sum(counts[name] for name in VALID_OUTCOMES)
    return {'chosen_among_valid_label_replies':_rate(counts['CHOSEN_ONE']+counts['CHOSEN_MULTIPLE'],valid),
            'question_mark_among_valid_label_replies':_rate(counts['INSUFFICIENT_CONTEXT'],valid)}


def analyze_run(path,*,catalog=None):
    """Machine-readable measurements, explicitly separate from model correctness."""
    path=Path(path);supplied=catalog is not None;catalog=catalog_snapshot() if catalog is None else catalog
    run=_read(path,catalog);cases=run['finished'];requests=run['requests']
    records=sorted((r for rr in requests.values() for r in rr),
        key=lambda r:min(row['_line'] for row in (r['start'],r['end']) if row))
    selection=[r for r in records if r['record_kind']=='SELECTION']
    slot_records=defaultdict(list)
    for record in selection:slot_records[record['slot']].append(record)
    slots={}
    for slot,rr in sorted(slot_records.items()):
        counts=_outcomes(rr)
        slots[slot]={'canonical_slot':slot,'raw_slots':sorted({r['raw_slot'] for r in rr if r['raw_slot']}),
            'records':len(rr),'completed_records':sum(r['end'] is not None for r in rr),
            'outcomes':counts,'rates':_rates(counts),
            'families':sorted({r['family'] for r in rr if r['family']}),
            'registry_statuses':sorted({r['registry_status'] for r in rr})}
    coverage={}
    for slot,spec in sorted(catalog['slots'].items()):
        rr=[r for r in records if any(view['canonical_slot']==slot and view['registry_status']=='REGISTERED'
                                     for view in r['observed_slots'])]
        coverage[slot]={'family':spec['family'],'level':spec['level'],'records':len(rr),
            'status':'OBSERVED_COMPLETED' if any(r['end'] is not None and not r['identity_ambiguous'] for r in rr) else
                     'OBSERVED_CONFLICTING_ID' if any(r['identity_ambiguous'] for r in rr) else
                     'STARTED_NO_FINISH' if rr else 'NOT_OBSERVED_IN_EXPORT'}
    table={name:{'PASS':0,'FAIL':0} for name in
           ('WITH_OBSERVED_QUESTION','WITHOUT_OBSERVED_QUESTION_COMPLETE','WITHOUT_OBSERVED_QUESTION_INCOMPLETE')}
    case_rows={};first_unknown=Counter();unknown_pass=[];nonempty=[];open_labels=[];genonly=[]
    global_gaps=any(run['issues'].get(name) for name in ('invalid_json_rows','invalid_event_rows',
        'sequence_gaps','sequence_missing','request_counter_mismatch','unattributed_requests'))
    case_starts={row.get('case_id') for row in run['rows'] if row['event']=='case_started'}
    for cid,case in cases.items():
        rr=[r for r in requests.get(cid,[]) if r['record_kind']=='SELECTION']
        has_question=any(r['classification']['outcome']=='INSUFFICIENT_CONTEXT' for r in rr)
        uncertain=any(r['classification']['outcome'] in {'UNKNOWN_EVIDENCE','TRUNCATED','UNFINISHED'}
                      for r in requests.get(cid,[]) if r['record_kind']!='EMBEDDING')
        uncertain=uncertain or global_gaps or cid not in case_starts
        bucket=('WITH_OBSERVED_QUESTION' if has_question else
                'WITHOUT_OBSERVED_QUESTION_INCOMPLETE' if uncertain else 'WITHOUT_OBSERVED_QUESTION_COMPLETE')
        status=case.get('status','UNKNOWN_EVIDENCE')
        if status in {'PASS','FAIL'}:table[bucket][status]+=1
        if status=='PASS' and has_question:unknown_pass.append(cid)
        if status=='FAIL':
            first_unknown[next((r['slot'] for r in rr if r['classification']['outcome']=='INSUFFICIENT_CONTEXT'),
                               'NOT_OBSERVED')]+=1
        errors=_case_errors(case)
        mismatch=any(e.get('path')=='/assertions/ah' and e.get('observed') for e in errors)
        if mismatch:nonempty.append(cid)
        if mismatch and any(e.get('path')=='/assertions/ah' and e.get('observed') and
            differs_only_in_open_labels(e.get('expected'),e['observed']) for e in errors):open_labels.append(cid)
        if {e.get('path') for e in errors}=={'/generation/gold_patterns'}:genonly.append(cid)
        case_rows[cid]={'status':status,'has_observed_valid_question':has_question,
            'abstention_evidence_incomplete':uncertain,'conditional_bucket':bucket,
            'input_records':[r for r in run['input_records'] if r['case_id']==cid],
            'step_records':[r for r in run['step_records'] if r.get('case_id')==cid],
            'request_records':requests.get(cid,[]),'case_finished':case}
    outcome_counts=_outcomes(selection)
    summary={'completed_cases':len(cases),'case_status_counts':dict(Counter(c.get('status','UNKNOWN_EVIDENCE') for c in cases.values())),
        'request_started_events':sum(r['event']=='request_started' for r in run['rows']),
        'request_finished_events':sum(r['event']=='request_finished' for r in run['rows']),
        'request_records':len(records),'completed_request_records':sum(r['end'] is not None for r in records),
        'paired_completed_request_records':sum(r['start'] is not None and r['end'] is not None for r in records),
        'text_replies':sum(r['end'] is not None and isinstance(r['response'],str) for r in records),
        'selection_records':len(selection),'non_selection_records':len(records)-len(selection),
        'selection_outcomes':outcome_counts,'rates':_rates(outcome_counts),
        'truncated_prompts':sum(bool((r['start'] or {}).get('prompt_truncated')) for r in records),
        'truncated_replies':sum(bool((r['end'] or {}).get('response_truncated')) for r in records),
        'clipped_selection_audits':sum(r['classification']['audit_clipped'] for r in selection),
        'step_result_events':len(run['step_records']),
        'truncated_step_results':sum(bool(r.get('actual_truncated')) for r in run['step_records'])}
    with_question=table['WITH_OBSERVED_QUESTION'];without=table['WITHOUT_OBSERVED_QUESTION_COMPLETE']
    issues=run['issues']
    views=[view for r in records for view in r['observed_slots']]
    family_names=sorted({row['family'] for row in coverage.values()})
    families={family:{'registered_slots':sum(row['family']==family for row in coverage.values()),
        'observed_slots':sum(row['family']==family and row['records']>0 for row in coverage.values())}
        for family in family_names}
    return {'schema_version':'probe-run-inventory-2','source':{'filename':path.name,
            'sha256':run['source_sha256']},'catalog':catalog,
        'catalog_role':'SUPPLIED_REPORTING_CATALOG' if supplied else 'CURRENT_CODE_REPORTING_CATALOG_NOT_HISTORICAL_RUNTIME',
        'summary':summary,'slots':slots,
        'coverage':{'denominator_scope':'DECLARED_STATIC_SLOTS_ONLY_NOT_LANGUAGE_OR_CALLSITE_COVERAGE',
            'registry_denominator':len(catalog['slots']),
            'registered_family_denominator':len(families),'families':families,
            'observed_registered_slots':sum(row['records']>0 for row in coverage.values()),
            'completed_registered_slots':sum(row['status']=='OBSERVED_COMPLETED' for row in coverage.values()),
            'slots':coverage,
            'unregistered_observed':sorted({r['raw_slot'] for r in views if r['registry_status']=='UNREGISTERED_OBSERVED'}),
            'dynamic_source_collection':sorted({r['raw_slot'] for r in views if r['registry_status']=='DYNAMIC_SOURCE_COLLECTION'})},
        'conditional_question_metrics':{'eligible_case_statuses':['PASS','FAIL'],'table':table,
            'pass_given_observed_question':_rate(with_question['PASS'],sum(with_question.values())),
            'pass_given_no_observed_question_complete':_rate(without['PASS'],sum(without.values())),
            'interpretation':'Descriptive conditional counts in this export; no confidence, correctness calibration or causality.'},
        'completeness':{'run_started_observed':any(r['event']=='run_started' for r in run['rows']),
            'run_finished_observed':any(r['event']=='run_finished' for r in run['rows']),
            'completed_cases_without_start':sorted(cid for cid in cases if cid not in case_starts),
            'sequence_recorded':any(type(r.get('seq')) is int for r in run['rows']),
            'issues':issues,'issue_counts':{name:sum(r.get('count',1) for r in rows) for name,rows in issues.items()}},
        'first_observed_question_in_failed_cases':dict(first_unknown),
        'comparison_categories':{'pass_with_observed_question':unknown_pass,'nonempty_mismatch':nonempty,
            'open_label_only_mismatch':open_labels,'generation_only_mismatch':genonly},
        'cases':case_rows,'request_records':records,
        'unfinished_case_ids':list(dict.fromkeys(cid for cid in (*run['inputs'],*requests) if cid not in cases))}


def _case_errors(case):
    errors=case.get('errors')
    return [e for e in errors if isinstance(e,dict)] if isinstance(errors,(list,tuple)) else []


def _rate_text(rate):
    return 'NA (0 знаменатель)' if rate['value'] is None else f"{rate['numerator']}/{rate['denominator']} ({rate['value']:.2%})"


def render_report(report):
    summary=report['summary'];categories=report['comparison_categories'];conditional=report['conditional_question_metrics']
    lines=['# Инвентаризация проб','',
        'Измерены только записи этой выгрузки. Валидный выбор номера не доказывает правильность смысла '
        'или последующее принятие разбиения. «Первый ?» не является доказанной первопричиной.','',
        f"Источник: `{report['source']['filename']}`. SHA-256: `{report['source']['sha256']}`.",
        f"Каталог: `{report['catalog']['schema_version']}`, registry SHA-256: `{report['catalog']['registry_sha256']}`, "
        f"catalog SHA-256: `{report['catalog'].get('catalog_sha256','NOT_RECORDED')}`. "
        f"Основание: `{report['catalog_role']}`.",'',
        f"Завершённых случаев: {summary['completed_cases']}; "+', '.join(f'{k}: {v}' for k,v in summary['case_status_counts'].items())+'.',
        f"Полученных текстовых ответов: {summary['text_replies']}. Записей запросов: {summary['request_records']}; "
        f"завершённых пар start/finish: {summary['paired_completed_request_records']}; "
        f"вызовов вне выбора (включая embeddings): {summary['non_selection_records']}.",
        f"Обрезанных промптов: {summary['truncated_prompts']}. Обрезанных ответов модели: {summary['truncated_replies']}. "
        f"Обрезанных результатов шагов: {summary['truncated_step_results']} из {summary['step_result_events']} записанных результатов.",
        'Обрезанный ответ сохраняется как TRUNCATED. Его полный текст и протокольный результат не восстанавливаются.','',
        '## Исходы проб выбора','',
        '| Канонический слот (исходные имена сохранены) | Записей | Один | Несколько | 0 | ? | Malformed | Unknown evidence | Truncated | Provider error | Unfinished |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for slot,row in report['slots'].items():
        counts=row['outcomes'];ordered=('CHOSEN_ONE','CHOSEN_MULTIPLE','NONE_FIT','INSUFFICIENT_CONTEXT',
                                       'MALFORMED','UNKNOWN_EVIDENCE','TRUNCATED','PROVIDER_ERROR','UNFINISHED')
        lines.append('| '+escape(slot)+' ← '+escape(', '.join(row['raw_slots']))+' | '+str(row['records'])+' | '+
                     ' | '.join(str(counts[k]) for k in ordered)+' |')
    lines+=['','Доля выбранных вариантов среди проверенных label-ответов: '+
            _rate_text(summary['rates']['chosen_among_valid_label_replies'])+'.',
            'Доля ? среди проверенных label-ответов: '+_rate_text(summary['rates']['question_mark_among_valid_label_replies'])+'.',
            'Знаменатель этих долей: CHOSEN_ONE + CHOSEN_MULTIPLE + NONE_FIT + INSUFFICIENT_CONTEXT. '
            'Ошибки, неизвестное evidence, clipping и незавершённые запросы показаны отдельно.','',
            '## Условные показатели ?','',
            '| Наблюдение в завершённом кейсе | PASS | FAIL |','|---|---:|---:|']
    for bucket,counts in conditional['table'].items():lines.append(f"| {bucket} | {counts['PASS']} | {counts['FAIL']} |")
    lines+=['','P(PASS | наблюдался валидный ?): '+_rate_text(conditional['pass_given_observed_question'])+'.',
        'P(PASS | ? не наблюдался, evidence ответа не помечено неполным): '+
        _rate_text(conditional['pass_given_no_observed_question_complete'])+'.',
        'Это описательные доли для PASS/FAIL; прочие статусы не входят в знаменатель. '
        'COMPLETE требует записанного начала кейса и отсутствия обнаруженных пропусков и непроверяемых ответов; '
        'это проверка доступного evidence, а не гарантия записи всех операций. '
        'Ни уверенность модели, ни причинность из них не выводятся.','',
        '## Объявленные слоты и наблюдавшиеся вызовы','',
        f"Знаменатель: {report['coverage']['registry_denominator']} статических слотов каталога; "
        f"наблюдались {report['coverage']['observed_registered_slots']}. "
        f"Семейств в этом каталоге: {report['coverage']['registered_family_denominator']}. Это не полнота языка и не число мест вызова.",
        'NOT_OBSERVED_IN_EXPORT означает отсутствие записи в этой выгрузке, а не неподдерживаемый механизм. '
        'Исторический alias меняет имя в отчёте, но не уравнивает семантику контрактов.','',
        '| Слот | Семейство | Наблюдение |','|---|---|---|']
    for slot,row in report['coverage']['slots'].items():lines.append(f"| {slot} | {row['family']} | {row['status']} |")
    lines+=['','UNREGISTERED_OBSERVED: '+(', '.join(report['coverage']['unregistered_observed']) or 'нет')+'.',
        'SOURCE_COLLECTION с записанным контрактом: '+(', '.join(report['coverage']['dynamic_source_collection']) or 'нет')+'.','',
        '## Полнота evidence','',
        f"run_started записан: {report['completeness']['run_started_observed']}; run_finished записан: {report['completeness']['run_finished_observed']}.",
        'Завершённые кейсы без записи начала: '+(', '.join(map(str,report['completeness']['completed_cases_without_start'])) or 'нет')+'.','']
    for name,count in report['completeness']['issue_counts'].items():lines.append(f'- {name}: {count}.')
    if not report['completeness']['issue_counts']:lines.append('Непарные, конфликтующие или повреждённые записи не обнаружены.')
    lines+=['','## Отдельно проверяемые результаты','',
        f"PASS с наблюдавшимся ?: {len(categories['pass_with_observed_question'])}. "
        f"Непустое несовпадение формулы: {len(categories['nonempty_mismatch'])}. "
        f"Из них только OPEN-метки: {len(categories['open_label_only_mismatch'])}. "
        f"Несовпадение только генерации: {len(categories['generation_only_mismatch'])}.",
        'Это категории записанного сравнения, а не исправление эталона или доказательство тождества неизвестных слов.','',
        '## Каждый завершённый случай','',
        'Строки относятся к исходному JSONL. Показаны все шаги и все уникальные request-ID записи; '
        'непарные и конфликтующие записи не выдаются за законченные вызовы.','']
    for cid,case in report['cases'].items():
        lines += [f"### {cid} — {case['status']}",'']
        for source in case['input_records']:
            lines += [f"Шаг `{source['step_id'] or 'не указан'}` (строка {source['line']}):",str(source['text']),'']
        if not case['input_records']:lines+=['Исходный текст не записан.','']
        for step in case['step_records']:
            if step.get('actual_truncated'):lines.append(f"Результат шага `{step.get('step_id','не указан')}` в строке {step['_line']} обрезан.")
        if case['status']=='PASS' and case['has_observed_valid_question']:
            lines+=['**Оракул прошёл при наблюдавшемся ?; полнота разбора этим не доказана.**','']
        for r in case['request_records']:
            begin=r['start'] or {};end=r['end'] or {}
            lines.append(f"- Строки {begin.get('_line','нет')} → {end.get('_line','нет')}. "
                f"{SLOTS.get(r['slot'],r['slot'])}: {selected_text(r)}"+
                (' **Промпт обрезан.**' if begin.get('prompt_truncated') else '')+
                (' **Ответ модели обрезан в выгрузке.**' if end.get('response_truncated') else ''))
        original=case['case_finished'];issue=original.get('first_observed_issue') or {}
        lines+=['','Первая записанная диагностика: '+(issue.get('code') or issue.get('kind') or 'нет')+'.']
        paths=list(dict.fromkeys(str(e.get('path','не указан')) for e in _case_errors(original)))
        if paths:lines+=['Несовпавшие проверки: '+', '.join('`'+p+'`' for p in paths)+'.']
        lines.append('')
    lines+=['## Незавершённые случаи','',', '.join(str(cid) for cid in report['unfinished_case_ids']) or 'Нет.','']
    return '\n'.join(lines)


def render(path):
    return render_report(analyze_run(path))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('progress',type=Path);parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--json-out',type=Path,help='also save normalized measurements and evidence references as JSON')
    args=parser.parse_args(argv);report=analyze_run(args.progress)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(render_report(report),encoding='utf-8')
    if args.json_out:
        args.json_out.parent.mkdir(parents=True,exist_ok=True)
        args.json_out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
