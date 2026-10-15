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


SLOTS={
    'structural_relation':'Внешняя связь', 'structural_revision':'Пересмотр разбора',
    'child_slot':'Дочерняя интерпретация', 'structural_partition':'Проверка разбиения',
    'structural_governor':'Управление модальным содержанием',
    'structural_function_owner':'Принадлежность служебного слова',
    'structural_event_head':'Главное слово названия события',
    'nominal_dependency':'Именная зависимость', 'nominal_coordination':'Однородные участники',
    'nominal_attachment':'Присоединение именной группы',
    'component_attachment':'Состав и чтение конструкции',
    'modifier_scope':'Область модификатора', 'source_assertion':'Утверждаемость содержания',
}
for key,label in [('structural_introducer','Вводящее выражение'),('structural_content','Вложенное содержание'),
                  ('structural_operand_1','Первая часть'),('structural_operand_2','Вторая часть')]:
    SLOTS[key+'_start']=label+': начало'
    SLOTS[key+'_end']=label+': конец'

RELATIONS={'LEXICAL':'Одна предикация / именное описание','NOT':'Отрицание','POSSIBLE':'Возможность',
    'NECESSARY':'Необходимость','AND':'Совместное выполнение','OR':'Включающее «или»',
    'XOR':'Исключающее «или»','IMPLIES':'Условие → следствие','COUNTERFACTUAL':'Контрфактическое условие',
    'BEFORE':'Раньше','AFTER':'Позже','DURING':'Во время','CONTENT':'Пропозициональное содержание',
    'FORALL':'Всеобщность','EXISTS':'Существование','QUERY':'Вопрос','GROUP':'Группа в скобках'}


def escape(value):
    return str(value).replace('|','\\|').replace('\n',' ')


def read_run(path):
    starts={};case_inputs={};finished={};steps={};requests=defaultdict(list);rows=[]
    for lineno,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        row=json.loads(line);row['_line']=lineno;rows.append(row)
        kind=row['event'];cid=row.get('case_id')
        if kind=='request_started':starts[row['request_id']]=row
        elif kind=='step_started':case_inputs[cid]=row['payload'].get('raw_input',{}).get('text','')
        elif kind=='step_finished':steps[cid]=row
        elif kind=='case_finished':finished[cid]=row
        elif kind=='request_finished':
            start=starts[row['request_id']];prompt=start['prompt']
            audit=start.get('selection_audit',{})
            matched=re.search(r'Decision slot: (\S+)',prompt)
            slot=audit.get('slot') or (matched.group(1) if matched else 'OTHER_PROVIDER_CALL')
            mapping={str(n):v for n,v in enumerate(audit.get('candidates',()),1)}
            if not mapping:mapping={n:json.loads(v) for n,v in re.findall(r'^(\d+) = (".*")$',prompt,re.M)}
            labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M));response=row.get('response','')
            requests[cid].append({'slot':slot,'value':mapping.get(response,response),
                'label':labels.get(response,response),'response':response,'start':start,'end':row,
                'mapping_complete':not start.get('prompt_truncated',False) or bool(audit)})
    return rows,case_inputs,finished,steps,requests


def selected_text(request):
    response=request['response'];value=request['value'];label=request['label']
    if response=='?':return 'Недостаточно контекста (?)'
    if response=='0':return 'Ни один показанный вариант не подошёл (0)'
    if request['slot']=='structural_relation':return RELATIONS.get(value,label)
    if request['slot'].endswith('_start'):
        return label.replace('Start at','Начать с')
    if request['slot'].endswith('_end'):
        return label.replace('End after','Закончить после').replace('full content','выбранный фрагмент').replace('selected words','выбранные слова')
    if request['slot']=='child_slot':return label.split('; linked morphology=')[0]
    if request['slot'] in {'nominal_dependency','component_attachment'}:
        return label.split('; whole reading=')[0].split('; linked morphology=')[0]
    return label


def render(path):
    rows,inputs,cases,steps,requests=read_run(path)
    completed=[r for rr in requests.values() for r in rr]
    slots=defaultdict(list)
    for r in completed:slots[r['slot']].append(r)
    unknown_pass=[cid for cid,c in cases.items() if c['status']=='PASS' and any(r['response']=='?' for r in requests[cid])]
    nonempty=[cid for cid,c in cases.items() if any(e['path']=='/assertions/ah' and e.get('observed') for e in c.get('errors',()))]
    genonly=[cid for cid,c in cases.items() if {e['path'] for e in c.get('errors',())}=={'/generation/gold_patterns'}]
    truncated=[r for r in completed if r['start'].get('prompt_truncated')]
    first_unknown=Counter(next((r['slot'] for r in requests[cid] if r['response']=='?'),'none')
        for cid,c in cases.items() if c['status']=='FAIL')
    lines=['# Инвентаризация проб: 15 октября 2026','',
        'Получено из всех доступных записей выгрузки. «Первый ?» — наблюдаемая остановка, **не доказанная первопричина**. '
        'Этот документ не восстанавливает обрезанные части и не оценивает качество новых промптов.','',
        f'Источник: `{path.name}`. SHA-256: `{hashlib.sha256(path.read_bytes()).hexdigest()}`.','',
        f'Завершённых случаев: {len(cases)}; '+', '.join(f'{k}: {v}' for k,v in Counter(c['status'] for c in cases.values()).items())+'.',
        f'Полученных ответов: {len(completed)}. Обрезанных промптов: {len(truncated)}. '
        f'Обрезанных результатов шагов: {sum(bool(s.get("actual_truncated")) for s in steps.values())}.',
        f'PASS при наличии ответа ?: {len(unknown_pass)}. Непустая формула, не совпавшая с эталоном: {len(nonempty)}. '
        f'Несовпадение только генерации: {len(genonly)}.','',
        '## Все типы вызванных проб','',
        '| Вопрос | Вызовов | ? | 0 | Средняя длина промпта, символов | Обрезано |',
        '|---|---:|---:|---:|---:|---:|']
    for slot,rr in slots.items():
        lines.append(f'| {SLOTS.get(slot,slot)} (`{slot}`) | {len(rr)} | {sum(r["response"]=="?" for r in rr)} | '
            f'{sum(r["response"]=="0" for r in rr)} | {round(sum(r["start"].get("prompt_chars",len(r["start"]["prompt"])) for r in rr)/len(rr))} | '
            f'{sum(bool(r["start"].get("prompt_truncated")) for r in rr)} |')
    lines+=['','## Первый ответ ? в неуспешных случаях','',
        '| Вопрос | Случаев |','|---|---:|']
    for slot,n in first_unknown.most_common():lines.append(f'| {SLOTS.get(slot,"Без ответа ?" if slot=="none" else slot)} | {n} |')
    lines+=['','## Отдельно проверяемые результаты','',
        'PASS с неотвеченными вопросами: '+', '.join(unknown_pass)+'.','',
        'Непустое несовпадение формулы: '+', '.join(nonempty)+'.','',
        '## Каждый завершённый случай','',
        'Номера строк относятся к исходному JSONL. Последовательность содержит **все** записанные ответы случая. '
        'Подробные поля морфологии здесь сокращены для чтения; исходные варианты находятся в промпте указанной строки.','']
    for cid,c in cases.items():
        lines += [f'### {cid} — {c["status"]}','',inputs.get(cid,'Исходный текст не записан.'),'']
        if c['status']=='PASS' and cid in unknown_pass:lines+=['**Проверка оракула прошла при неразрешённых пробах; полнота разбора этим не доказана.**','']
        if steps.get(cid,{}).get('actual_truncated'):lines+=['Результат шага обрезан в выгрузке.','']
        for r in requests[cid]:
            lines.append(f'- Строки {r["start"]["_line"]} → {r["end"]["_line"]}. '
                f'{SLOTS.get(r["slot"],r["slot"])}: {selected_text(r)}'+
                (' **Промпт обрезан.**' if r['start'].get('prompt_truncated') else ''))
        issue=c.get('first_observed_issue') or {}
        lines+=['','Первая записанная диагностика: '+(issue.get('code') or issue.get('kind') or 'нет')+'.']
        paths=list(dict.fromkeys(e['path'] for e in c.get('errors',())))
        if paths:lines+=['Несовпавшие проверки: '+', '.join('`'+p+'`' for p in paths)+'.']
        if cid in nonempty:lines+=['**Формула непустая, но отличается от эталона; это не простой отказ модели.**']
        lines.append('')
    unfinished=[cid for cid in inputs if cid not in cases]
    lines+=['## Незавершённые случаи','',', '.join(unfinished) or 'Нет.','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('progress',type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(render(args.progress),encoding='utf-8')


if __name__=='__main__':main()
