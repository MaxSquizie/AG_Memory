"""Deterministic Russian explanations of recorded data, never a second parser."""
from html import escape
import ast
import re
from urllib.parse import quote

OPERATORS = {
    'LEXICAL':'Действие или описание без внешней логической связи',
    'CONTENT':'Вложенное содержание высказывания', 'QUERY':'Вопрос к содержанию',
    'GROUP':'Скобки объединяют выражение',
    'BEFORE':'Первое событие раньше второго', 'AFTER':'Первое событие позже второго',
    'DURING':'Первое событие во время второго',
    'NOT': 'Неверно, что', 'FORALL': 'Для каждого', 'EXISTS': 'Существует',
    'AND': 'Выполняются все условия', 'OR': 'Выполняется хотя бы одно условие',
    'XOR': 'Выполняется ровно одно условие', 'IMPLIES': 'Если …, то …',
    'POSSIBLE': 'Возможно, что', 'NECESSARY': 'Необходимо, что',
    'COUNTERFACTUAL': 'Контрфактическое условие', 'GOAL': 'Требуется установить',
}
ROLES = {'SUBJECT': 'Кто / что', 'OBJECT': 'Объект действия', 'RECIPIENT': 'Получатель',
    'LOCATION': 'Место', 'LOCATIVE': 'Место', 'INSTRUMENT': 'Инструмент',
    'SOURCE': 'Откуда', 'DESTINATION': 'Куда', 'TIME': 'Время', 'AGENT': 'Действующее лицо',
    'EXPERIENCER':'Кто испытывает состояние'}
STATUS = {'APPLIED': 'Записано в память', 'RESOLVED': 'Выбор подтверждён',
    'UNRESOLVED': 'Не разрешено', 'CANDIDATE': 'Вариант разбора',
    'SUPERSEDED': 'Заменено последующим решением', 'ONE_SELECTED': 'Выбран один вариант',
    'MULTIPLE_ADMISSIBLE': 'Осталось несколько вариантов', 'INSUFFICIENT_CONTEXT': 'Недостаточно контекста',
    'NONE_FIT': 'Ни один вариант не подошёл', 'RECEIPT': 'Записанный корень',
    'STRUCTURAL DESCENDANT': 'Часть записанного выражения', 'STRUCTURE ≠ FACT': 'Промежуточная структура',
    'RESOLVED REFERENCE ≠ FACT': 'Привязка участника', 'UNANCHORED ≠ ERROR': 'Нет привязки к фрейму',
    'SELECTED': 'Граница выбрана', 'CONFIGURATION': 'Параметры запуска',
    'ERROR': 'Ошибка', 'TRUNCATED': 'Показана часть данных', 'STOPPED': 'Разбор остановлен',
    'KNOWN': 'Словарное значение известно', 'UNLINKED': 'Словарный смысл не установлен',
    'OPEN_LEXICAL': 'Словарный смысл не установлен', 'UNKNOWN': 'Не установлено'}
QUESTIONS = {'composition_boundary': 'Что охватывает всё выражение?',
    'structural_relation':'Какая связь охватывает весь фрагмент?',
    'structural_revision':'Можно ли пересмотреть выбор с учётом противоречия во вложенных частях?',
    'structural_partition':'Согласованы ли тип связи, порядок частей и всё исходное содержание?',
    'relation_marker_role':'Это слова внешней связи или часть описываемого действия?',
    'structural_owner':'Какому слову принадлежит вложенное содержание?',
    'structural_content_role':'Какую роль играет содержание и как к нему относится говорящий?',
    'structural_control':'Кто выполняет действие в инфинитиве?',
    'structural_governor':'Какой глагол задаёт согласование вложенного действия?',
    'structural_function_owner':'К внешней связи или к вложенной части относится служебное слово?',
    'structural_binder_head':'Какое имя связывает квантор?',
    'structural_event_head':'Это высказывание о предмете или название события?',
    'structural_refinement':'Где начинается и заканчивается описание имени?',
    'structural_marker_reading':'Какое целое морфологическое чтение имеет связующее слово?',
    'structural_oov_reading':'Какое морфологическое чтение подходит неизвестному слову?',
    'child_slot':'Какой из разборов подходит к требованиям родительской части?',
    'attitude_attachment':'К какому высказыванию относится вложенное содержание и где его границы?',
    'nominal_dependency': 'К какому слову относится участник и в какой роли?',
    'component_attachment': 'Как связаны действие и его участники?',
    'nominal_attachment': 'К какому имени относится определение или квантор?',
    'modifier_scope': 'На какую часть выражения действует оператор?',
    'implicit_argument': 'Кто подразумевается в пропущенной роли?',
    'predicate_value': 'Какое значение слова выбрано?', 'composition': 'Как объединены части выражения?'}
MORPH = {'NOUN':'существительное','VERB':'глагол','INFN':'инфинитив','ADJF':'прилагательное',
    'ADJS':'краткое прилагательное','PRTF':'причастие','PRTS':'краткое причастие',
    'GRND':'деепричастие','ADVB':'наречие','NPRO':'местоимение','PREP':'предлог',
    'CONJ':'союз','PRCL':'частица','NUMR':'числительное','PNCT':'пунктуация',
    'nom':'именительный','gen':'родительный','dat':'дательный','acc':'винительный',
    'ins':'творительный','loc':'предложный','sing':'единственное число','plur':'множественное число',
    'masc':'мужской род','femn':'женский род','neut':'средний род','past':'прошедшее время',
    'pres':'настоящее время','futr':'будущее время','1st':'1-е лицо','2nd':'2-е лицо','3rd':'3-е лицо',
    'perf':'совершенный вид','impf':'несовершенный вид','anim':'одушевлённое','inan':'неодушевлённое',
    'tran':'переходный','intr':'непереходный','indc':'изъявительное наклонение','impr':'повелительное наклонение',
    'abl':'творительный','present':'настоящее время','future':'будущее время',
    'indicative':'изъявительное наклонение','imperative':'повелительное наклонение'}
TRACE = {'FEATURE_CHECK_BATCH':'Проверка грамматических признаков',
    'SEMANTIC_PRIOR_EXCLUDED':'Прежний разбор не подходит текущей форме слова',
    'CONTENT_SEPARATOR_OWNERSHIP':'Пунктуация, связывающая родителя с содержанием',
    'STRUCTURAL_PARTITION_COVERAGE':'Слова, оставшиеся без содержательной роли',
    'STRUCTURAL_BOUNDARY_DOMAIN':'Согласование границ с принадлежностью слов',
    'MORPHOLOGY_DOMAIN_RESTRICTION':'Выбранное морфологическое чтение слова',
    'DISPATCH_COMPLETED':'Диспетчер: задача пересчитана',
    'DISPATCH_REUSED':'Диспетчер: результат сохранён',
    'DISPATCH_INVALIDATED':'Диспетчер: требуется пересмотр',
    'DISPATCH_RECHECK':'Диспетчер: зависимости изменились во время расчёта',
    'DISPATCH_MORPHOLOGY':'Диспетчер: морфология текущей области',
    'STRUCTURAL_TASK':'Выбор связи или границы по исходному тексту',
    'STRUCTURAL_RELATION_COMPOSED':'Связь собрана из согласованных частей',
    'COMPOSITION_PRODUCERS':'Проверка всех источников разбора',
    'COMPOSITION_EQUIVALENT_SOURCES':'Совпадающие результаты источников',
    'STRUCTURAL_REVISION_STALLED':'Пересмотр повторил тот же разбор',
    'TEMPORAL_PREDICATE_EXCLUDED':'Слово временного выражения исключено из предикатов',
    'ATTITUDE_COMPOSITION':'Вложенное содержание высказывания',
    'DEFERRED_CLAUSE_BOUNDARY':'Разбиение отложено до проверки вложенности',
    'COMPOSITION_SOURCE_DOMAIN':'Источники вариантов разбора', 'SCOPE_DOMAIN':'Варианты области действия',
    'SCOPE_SLOT':'Выбор области действия','GRAMMAR_CHILD_PROJECTED':'Перенос дочернего разбора',
    'COMPOSITION_BOUNDARY':'Выбор границы выражения','DEPENDENCY_CONSTRAINT_CLOSURE':'Согласование зависимостей',
    'COORDINATION_TREE':'Группировка однородных частей','COORDINATION':'Связь однородных частей',
    'QUANTIFIER_BINDING_DOMAIN':'Варианты связывания квантора','OPERATOR_COMPOSITION':'Вложенность операторов',
    'COMPOSITION_CLOSED':'Объединение частей завершено','COMPOSITION_EMPTY':'Допустимый разбор не построен'}
DIAGNOSTICS = {'COMPOSITION_SCOPE_BOUNDARY_CHANGED':'При объединении изменилось содержимое цельного условия.',
    'ACTION_DESCRIPTION_WITHOUT_SCOPE':'Описание действия не утверждает его совершения. Для записи нужна внешняя модальность или вложенное содержание.',
    'COMPOSITION_DEPENDENCY_NO_PROGRESS':'Зависимости повторяют те же несовместимые состояния. Разбор остановлен без принудительного выбора.',
    'COMPOSITION_DEPENDENCY_STALE':'Связанный результат изменился после расчёта. Устаревший разбор не допущен к записи.',
    'COMPOSITION_DISPATCH_INCOMPLETE':'Диспетчер достиг предела согласования зависимостей. Разбор не завершён.',
    'COMPOSITION_CYCLE':'Задача требует собственный ещё не рассчитанный результат. Цикл не разрешает выбрать ответ.',
    'STRUCTURAL_TASK_UNRESOLVED':'Тип связи, границы или вложенные части ещё не согласованы. Отдельные части не записаны как самостоятельные факты.',
    'STRUCTURAL_CONTENT_UNCOVERED':'Вне частей сообщения остались значимые слова. Они не имеют служебного чтения и не могут быть отброшены как вводящее выражение.',
    'STRUCTURAL_MARKER_CONTENT':'Проба нашла слово описываемого действия внутри внешнего связующего выражения. Его нужно вернуть в содержание и пересмотреть границы.',
    'STRUCTURAL_TASK_SEARCH_INCOMPLETE':'Достигнут предел поиска или размера контекста. Это не означает отсутствия подходящего разбора.',
    'STRUCTURAL_REVISION_NO_PROGRESS':'Пересмотр повторил те же варианты и ту же ошибку. Повторный поиск остановлен; разбор остаётся неразрешённым.',
    'COMPOSITION_PRODUCER_PENDING':'Один из источников разбора ещё не разрешён. Готовый вариант другого источника не признан единственным.',
    'ARITHMETIC_QUANTIFIER_DEFERRED':'Числовой квантор отложен: арифметический движок не включён.',
    'ATTITUDE_SLOT_UNCLOSED':'Не подтверждены границы или владелец вложенного высказывания. Его содержание не записано как самостоятельный факт.',
    'ATTITUDE_PARENT_UNRESOLVED':'Вложенное содержание разобрано, но не удалось собрать высказывание, которому оно принадлежит.',
    'COMPOSITION_SCOPE_BOUNDARY_LOST':'При объединении потерялась ранее выбранная граница условия.',
    'COMPOSITION_SCOPE_BOUNDARY_CROSSING':'Области условий пересекаются, но не вложены друг в друга.',
    'QUANTIFIED_CONTROL_UNRESOLVED':'Не подтверждено, что пропущенный участник находится внутри области своего квантора.',
    'IMPLICIT_ARGUMENT_UNRESOLVED':'Не удалось определить пропущенного участника.',
    'RUN_WITHOUT_IR':'Разбор остановился до сохранения структуры.'}

for _slot,_name in {'structural_operand_1':'первой части', 'structural_operand_2':'второй части',
    'structural_introducer':'выражения внешней связи','structural_content':'вложенного содержания',
    'structural_parent':'главного высказывания','structural_quantifier':'выражения квантора',
    'structural_group':'выражения в скобках'}.items():
    QUESTIONS[_slot+'_start']='Где начало '+_name+'?'
    QUESTIONS[_slot+'_end']='Где конец '+_name+'?'


def esc(value):
    return escape(str(value))


def paragraph(text):
    return '<p>'+esc(text)+'</p>'


def table(headers, rows):
    return '<table cellspacing="0" cellpadding="7" border="1"><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr>'+''.join(
        '<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</table>'


def document(body):
    return '<!doctype html><html lang="ru"><meta charset="utf-8"><style>body{font-family:Segoe UI,Arial,sans-serif;line-height:1.5} table{border-collapse:collapse} td,th{border-color:#88958c;text-align:left} li{margin:7px 0} blockquote{border-left:3px solid #708f79;padding-left:12px} a{color:#4e9470} .muted{color:#858e88}</style><body>'+body+'</body></html>'


class ReadableInspection:
    def __init__(self, inspection):
        self.index=inspection; self.state=inspection.state
        self.tokens={e['token_id']:e for e in self.state.get('evidence',())}
        self.frames={f['frame_id']:f for f in self.state.get('frames',())}
        self.graph=inspection.snapshot.get('committed_graph',{}); self.nodes=self.graph.get('nodes',{})
        self.entities={};self.variables={};self.aliases={};self.gaps={};self.specs={}
        self.option_labels={};self.domain_names={};self.task_options={}
        self.dispatch_tasks={};self.dispatch_versions={}
        for entry in self.index.entries:
            row=entry.record
            if entry.category=='Трасса' and row.get('kind','').startswith('DISPATCH_') and row.get('task_kind'):
                self.dispatch_tasks[row.get('task_ref')]=entry
                if row.get('revision'):self.dispatch_versions[(row.get('task_ref'),row['revision'])]=entry
        observation=self.state.get('observation',{})
        self.implicit=observation.get('implicit_bindings',{})
        for mention,ref in observation.get('entity_bindings',{}).items():
            if isinstance(ref,str):self.entities.setdefault(ref,[]).append(self.word(mention))
        for f in self.frames.values():
            sem=f.get('semantic',{});self.specs.update(sem.get('candidate_specs',{}))
            for token,var in sem.get('bound_arguments',{}).items():self.variables.setdefault(var,self.word(token))
            for role,gap in sem.get('implicit_arguments',{}).items():self.gaps[gap['gap_id']]=(f,role,gap)
        for ref,entity in self.graph.get('entities',{}).items():
            if entity.get('name'):self.entities[ref]=[entity['name']]
        for e in self.index.entries:
            gapref=e.record.get('decision',e.record).get('frame_id') if e.category in {'Решения','Пробы'} else e.ref.removesuffix('|binding')
            if gapref in self.gaps:
                f,role,gap=self.gaps[gapref];token=self.tokens.get(f.get('predicate_token_ref'),{})
                e.source_range=[token['start'],token['end']] if 'start' in token else f.get('source_range')
        for trace in self.state.get('syntax_trace',()):
            for domain,options in trace.get('values',{}).items():
                if not isinstance(options,dict):continue
                for ref,value in options.items():
                    if isinstance(value,dict) and value.get('label'):
                        self.option_labels[ref]=value['label']
                        self.domain_names.setdefault(domain,value['label'].split(' applies to ')[0])
            for option in trace.get('alternatives',()):
                if isinstance(option,dict) and option.get('candidate_id') and option.get('label'):self.option_labels[option['candidate_id']]=option['label']
                if trace.get('kind')=='STRUCTURAL_TASK' and isinstance(option,dict):
                    self.task_options[(trace.get('decision_ref'),option.get('candidate_id'))]=option

    def word(self,ref):
        token=self.tokens.get(ref)
        if token:return token.get('span',token.get('lemma','слово'))
        return self.alias(ref)

    def alias(self,ref):
        if not isinstance(ref,str):return 'объект без названия'
        if ref in self.frames:return self.frames[ref].get('anchor_span') or 'фрейм'
        if ref in self.entities:return ' / '.join(self.entities[ref])
        if ref in self.index.by_ref:
            e=self.index.by_ref[ref]
            if e.source_range:return self.excerpt(e.source_range,100)
        if not re.search(r'[a-f0-9]{16,}|^(?:tok|region|gap|M|N|G):',ref):return ref
        if ref not in self.aliases:self.aliases[ref]='объект №'+str(len(self.aliases)+1)+' (название не сохранено)'
        return self.aliases[ref]

    def excerpt(self,bounds,limit=400):
        if not bounds or len(bounds)!=2:return 'фрагмент источника не указан'
        text=self.index.text[max(0,bounds[0]):bounds[1]]
        return text[:limit]+('…' if len(text)>limit else '')

    def variable(self,var):
        name=self.variables.get(var)
        return ('«'+name+'», ' if name else '')+'переменная '+str(var)

    def target(self,value):
        if isinstance(value,dict):
            if 'bound_var' in value:return self.variable(value['bound_var'])+' (связана квантором)'
            if 'entity_ref' in value:return self.alias(value['entity_ref'])+(' (личность не установлена)' if value.get('anonymous') else '')
            if 'frame_ref' in value:return self.alias(value['frame_ref'])
            return 'структурированный участник; подробности в технических данных'
        return self.word(value) if isinstance(value,str) and value in self.tokens else self.alias(value)

    def link(self,ref,label=None):
        return '<a href="review:'+quote(str(ref),safe='')+'">'+esc(label or self.alias(ref))+'</a>'

    def morphology(self,v):
        values=[v.get('pos'),*v.get('cases',()),v.get('number'),v.get('gender'),v.get('person'),v.get('tense'),v.get('mood')]
        values += [x for x in v.get('features',()) if x in MORPH and x not in values]
        return ', '.join(MORPH.get(x,x) for x in values if x) or 'признаки не сохранены'

    def title(self,e):
        r=e.record;c=e.category
        if c in {'Решения','Пробы'}:
            d=r.get('decision',r);return QUESTIONS.get(d.get('slot_id'),'Выбор интерпретации')+' · '+self.excerpt(e.source_range,60)
        if c=='Граф AH':return OPERATORS.get(r.get('function_id')) or self.word(r.get('source_ref','')) or 'Узел памяти'
        if c in {'Формулы','Подформула'}:return self.node_label(r)
        if c=='Трасса':return TRACE.get(r.get('kind',r.get('event')),'Шаг разбора')
        if c=='Границы условий':return OPERATORS.get(r.get('operator'),'Условие')+' · «'+self.excerpt(e.source_range,70)+'»'
        if c=='Привязки':
            ref=e.ref.removesuffix('|binding');gap=self.gaps.get(ref)
            label=('Пропущенный участник «'+gap[0].get('anchor_span','')+'»') if gap else self.word(ref)
            return label+' → '+self.target(r.get('target'))
        if c=='Области':return {'DOCUMENT':'Документ','PARAGRAPH':'Абзац','SENTENCE':'Предложение','CLAUSE':'Клауза','TOKEN':'Слово','CLAUSE_WINDOW':'Окно разбора'}.get(r.get('kind'),'Область')+' · '+self.excerpt(e.source_range,60)
        if c=='Диагностика':return DIAGNOSTICS.get(r.get('code'), 'Сообщение о разборе')
        if c=='Контекст':return 'Обращение к памяти · '+self.excerpt(r.get('request',{}).get('source_range'),60)
        if e.ref=='receipt':return 'Что записано в память'
        return e.label

    def node_label(self,node):
        if isinstance(node,str):node=self.nodes.get(node,{})
        if not isinstance(node,dict):return 'Значение'
        if 'bound_var' in node:return self.variable(node['bound_var'])
        if 'frame_ref' in node:return self.alias(node['frame_ref'])
        return OPERATORS.get(node.get('operator',node.get('function_id')), 'Оператор '+str(node.get('operator',node.get('function_id','без названия'))))

    def frame_roles(self,f):
        sem=f.get('semantic',{});rows=[]
        for token,role in sem.get('proposed_roles',{}).items():
            var=sem.get('bound_arguments',{}).get(token)
            target=self.variable(var)+' (связана квантором)' if var is not None else self.word(token)
            rows.append([esc(ROLES.get(role,role)),esc(target),self.link(token,'«'+self.word(token)+'»'),esc(self.morphology(sem.get('morph_bindings',{}).get(token,{})))])
        for role,gap in sem.get('implicit_arguments',{}).items():
            binding=self.implicit.get(gap['gap_id'])
            rows.append([esc(ROLES.get(role,role)),esc(self.target(binding) if binding else 'Не определён'),self.link(gap['gap_id'],'Пропущен в тексте; открыть выбор') if gap['gap_id'] in self.index.by_ref else 'Пропущен в тексте',esc(self.morphology(gap.get('features',{})))])
        for role in sem.get('action_description',{}).get('unassigned_roles',()):
            rows.append([esc(ROLES.get(role,role)),'Не указан в описании действия','Сущность не создаётся','Признаки не заданы'])
        return rows

    def formula(self,node,depth=0,seen=frozenset(),budget=None):
        if budget is None:budget=[400]
        if depth>24 or budget[0]<=0:return paragraph('Продолжение скрыто из-за размера; откройте нужную часть отдельно.')
        budget[0]-=1
        ref=node if isinstance(node,str) else None
        if ref:
            if ref in seen:return paragraph('Повторная ссылка на '+self.alias(ref))
            seen=seen|{ref};node=self.nodes.get(ref)
            if node is None:return paragraph('Данные для '+self.alias(ref)+' отсутствуют в снимке.')
        if not isinstance(node,dict):return paragraph('Структура узла не сохранена.')
        if 'bound_var' in node:return esc(self.variable(node['bound_var']))
        fid=node.get('frame_ref');f=self.frames.get(fid)
        if f:
            roles=self.frame_roles(f);out=self.link(fid,'«'+f.get('anchor_span','')+'»')
            return out+(table(['Роль','Участник','В тексте','Морфология'],roles) if roles else '')
        if 'actants' in node:
            label=self.word(node.get('source_ref',''))
            out=self.link(ref,'«'+label+'»') if ref else esc(label)
            if node.get('polarity') is False:out='Неверно, что: '+out
            out+=table(['Роль','Участник'],[[esc(ROLES.get(k,k)),esc(self.target(v))] for k,v in node['actants'].items()])
            if node.get('action_description'):
                out+=paragraph('Описание действия: его совершение отдельно не утверждается. Не указаны: '+
                    ', '.join(ROLES.get(r,r) for r in node['action_description']['unassigned_roles'])+'.')
            if node.get('semantic_status') in {'UNLINKED','OPEN_LEXICAL'}:out+=paragraph('Словарный смысл этого слова не установлен. Сохранены исходное слово и связи.')
            return out
        op=node.get('operator',node.get('function_id'));children=list(node.get('operands',()))
        label=self.node_label(node)
        if op in {'FORALL','EXISTS'} and children and isinstance(children[0],dict) and 'bound_var' in children[0]:
            label+=': '+self.variable(children.pop(0)['bound_var'])
        out='<b>'+(self.link(ref,label) if ref else esc(label))+'</b>'
        if not children:return out+paragraph('Операнды не сохранены.')
        items=[]
        for i,child in enumerate(children):
            prefix=('Условие: ' if i==0 else 'Следствие: ') if op=='IMPLIES' else ''
            items.append('<li>'+esc(prefix)+self.formula(child,depth+1,seen,budget)+'</li>')
            if budget[0]<=0:
                if i+1<len(children):items.append('<li>Остальные части скрыты из-за размера.</li>')
                break
        return out+'<ul>'+''.join(items)+'</ul>'

    def task_choice(self,value):
        if value.get('boundary_end_ref') and 'remainder_refs' in value:
            return ('Конец после «'+self.word(value['boundary_end_ref'])+'». Слова связи: «'+
                    ' '.join(self.word(t) for t in value.get('selected_refs',()))+
                    '». Во вложенном содержании останется: «'+' '.join(self.word(t) for t in value['remainder_refs'])+'».')
        content=(' Содержание: «'+' '.join(self.word(t) for t in value['content_refs'])+'».'
                 if value.get('content_refs') else '')
        if value.get('independent_content'):
            return 'Вложенное содержание самостоятельно определяет участников. Участник родительского действия не переносится в инфинитив.'+content
        if value.get('marker_relation_ref'):
            return '«'+self.word(value['marker_relation_ref'])+'» выражает только внешнюю связь; описываемое действие или состояние остаётся в содержании.'
        if value.get('marker_content_ref'):
            return '«'+self.word(value['marker_content_ref'])+'» называет часть описываемого действия, состояния или участника. Это значение нужно сохранить в содержании.'
        if value.get('frame_refs'):
            parts=[]
            for fid in value['frame_refs']:
                frame=self.frames.get(fid,{})
                sem=frame.get('semantic',{})
                roles=[ROLES.get(role,role)+': «'+self.word(tid)+'» ('+
                       self.morphology(sem.get('morph_bindings',{}).get(tid,{}))+')' for tid,role in sem.get('proposed_roles',{}).items()]
                source='грамматика' if sem.get('composition_source')=='GRAMMAR' else 'компонентная композиция'
                reading=self.morphology(sem.get('morph_bindings',{}).get(frame.get('predicate_token_ref'),{}))
                parts.append('«'+frame.get('anchor_span','часть разбора')+'» ('+source+'; '+reading+'). '+ '; '.join(roles))
            return ' '.join(parts)
        if value.get('controller'):
            alias=value['controller']
            token=alias.get('token_ref') or alias.get('head_ref') or alias.get('host_token_ref')
            return 'Тот же участник управляющего действия'+(': «'+self.word(token)+'».' if token else '; отдельный участник не создаётся.')+content
        if value.get('operands'):
            parts=['«'+' '.join(self.word(t) for t in part)+'»' for part in value['operands']]
            markers=' '.join(self.word(t) for t in value.get('marker_refs',()))
            return OPERATORS.get(value['relation'],value['relation'])+'. Части по порядку: '+ '; '.join(parts)+'. Служебное выражение: «'+markers+'». Остальное содержание не опущено.'
        if value.get('relation'):return OPERATORS.get(value['relation'],value['relation'])
        if value.get('reading'):
            reading=value['reading']
            lemma=('Лемма не установлена; сохраняется исходная форма. ' if value.get('predicted_lemma') is False else
                'Начальная форма «'+str(reading.get('lemma') or 'не установлена')+'»'+
                (' (морфологическая гипотеза). ' if value.get('predicted_lemma') else '. '))
            return lemma+'Чтение слова: '+self.morphology(reading)+'. Словарный смысл и неизвестные признаки не додумываются.'
        if value.get('attitude'):
            attitudes={'QUOTED':'пересказ','EMBEDDED':'мысленное содержание','HYPOTHETICAL':'предполагаемое или желаемое содержание','UNKNOWN':'отношение не уточнено'}
            return ROLES.get(value['role'],value['role'])+' слова «'+self.word(value['owner_ref'])+'»: '+attitudes[value['attitude']]+'. Вложенное содержание отдельно не утверждается.'+content
        if value.get('owner_ref'):return 'Владелец содержания: «'+self.word(value['owner_ref'])+'».'+content
        if value.get('head_ref'):return 'Связанное квантором имя: «'+self.word(value['head_ref'])+'».'
        if value.get('head'):return 'Имя события: «'+self.word(value['head'])+'».'
        return self.choice_text(value.get('label','Описание варианта не сохранено'))

    def choice_text(self,text):
        # Translate known protocol labels only. Never infer a model rationale.
        if text.startswith('Whole target is one infinitive action description'):
            return 'Весь фрагмент описывает одно действие в инфинитиве с его участниками и определениями; отдельного родительского сказуемого нет.'
        text=re.sub(r'; action description; occurrence is NOT asserted; unassigned roles=([^;]*); no participant identity is supplied for them',
            lambda m:'; Описание действия без утверждения о совершении; не указаны: '+
            (', '.join(ROLES.get(r.strip(),r.strip()) for r in m[1].split(',') if r.strip()) or 'нет таких ролей')+'; сущности не создаются',text)
        text=text.replace('; passive: the nominative participant receives the action, not performs it',
            '; Страдательный залог: участник в именительном падеже является объектом действия')
        boundary=re.fullmatch(r'End after «(.*?)» @(\d+); selected words «(.*?)»; content left for this relation: «(.*?)»',text,re.S)
        if boundary:return ('Конец после «'+boundary[1]+'», позиция '+boundary[2]+'. Слова связи: «'+boundary[3]+
                            '». Во вложенном содержании останется: «'+boundary[4]+'».')
        if text.startswith('A complete clause:'):return 'Полное высказывание: сказуемое описывает участника; явный глагол может отсутствовать.'
        if text.startswith('All these words only express the outer relation;'):
            return 'Эти слова выражают только внешнюю связь. Описываемое событие или состояние полностью сохранено во вложенном содержании.'
        marker=re.match(r'«(.*?)» @\d+ names part of the event/state being related,',text)
        if marker:return 'Слово «'+marker[1]+'» относится к самому описываемому событию или состоянию. Нужно вернуть его в содержание и пересмотреть границы.'
        nominal=re.search(r'noun predicate: «(.*?)» describes what «(.*?)» is',text)
        if nominal:return 'Именное сказуемое «'+nominal[1]+'» характеризует «'+nominal[2]+'». Это предложенный разбор; его соответствие тексту проверяется пробой.'
        if '; impersonal state;' in text:
            head=text.split('; impersonal state;')[0]
            for k,v in ROLES.items():head=head.replace(k+'=',v+': ')
            head=re.sub(r'\[(\w+)\]',lambda m:'('+MORPH.get(m[1],m[1])+')',head)
            return head+'. Безличное состояние: участник в дательном падеже испытывает его. Отдельное подлежащее не добавляется. Это вариант для проверки пробой.'
        if text.startswith('Revise the provisional'):return 'Пересмотреть предварительный тип связи и границы с учётом требований вложенных частей.'
        if text.startswith('Keep the whole area unresolved'):return 'Оставить весь фрагмент неразрешённым: подтверждённого исправления нет.'
        if text.startswith('No agreement governor'):return 'Согласование с внешним словом не переносится. Вложенная часть сама определяет участников; безличное описание может не называть исполнителя.'
        match=re.match(r'Start at «(.*?)» @(\d+)',text)
        if match:return 'Начало перед «'+match[1]+'», позиция '+match[2]+'.'
        match=re.match(r'End after «(.*?)» @(\d+); full content «(.*)»',text,re.S)
        if match:return 'Конец после «'+match[1]+'», позиция '+match[2]+'. Вся выбранная часть: «'+match[3]+'».'
        if text.startswith('Every listed function token'):return 'Все перечисленные служебные слова остаются внутри своих частей.'
        match=re.match(r'Outer relation owns «(.*?)» @(\d+)',text)
        if match:return 'Слово «'+match[1]+'» на позиции '+match[2]+' относится к внешней связи.'
        match=re.match(r'Agreement/controller anchor «(.*?)»',text)
        if match:return 'Согласование задаёт «'+match[1]+'».'
        match=re.match(r'(?:RELATIVE|PARTICIPLE) description «(.*?)»; parent «(.*?)»',text,re.S)
        if match:return 'Описание: «'+match[1]+'». Главная часть: «'+match[2]+'».'
        match=re.fullmatch(r'Proposition content «(.*)» fills (\w+) of «(.*?)»; holder role (\w+); attitude=(\w+); remaining parent «(.*)»; the content is NOT independently asserted',text,re.S)
        if match:
            return ('Содержание «'+match[1]+'» относится к «'+match[3]+'». Роль: '+ROLES.get(match[2],match[2])+
                    '. Оставшаяся часть: «'+match[6]+'». Содержание не утверждается как самостоятельный факт.')
        text=re.sub(r'tok:\d+:\d+',lambda m:'«'+self.word(m[0])+'»',text)
        match=re.match(r'Direct role (\w+) of predicate «(.*?)»; whole reading=(.*)',text)
        if match:
            try:v=ast.literal_eval(match[3]);morph=self.morphology(v)
            except (ValueError,SyntaxError):morph='морфологические признаки см. в исходном вопросе'
            return 'Участник действия «'+match[2]+'». Роль: '+ROLES.get(match[1],match[1])+'. '+morph
        match=re.match(r'CASE_DEPENDENCY dependency on «(.*?)» at \d+; whole reading=(.*)',text)
        if match:
            try:morph=self.morphology(ast.literal_eval(match[2]))
            except (ValueError,SyntaxError):morph='признаки см. в исходном вопросе'
            return 'Именная зависимость от «'+match[1]+'». '+morph
        match=re.match(r'(FORALL|EXISTS) «(.*?)» binds the existing nominal «(.*?)»',text)
        if match:return 'Квантор «'+match[2]+'» относится к «'+match[3]+'». Имя ограничивает область квантора; отдельный конкретный участник не утверждается.'
        match=re.match(r'Same bound variable v(\d+) as (.*?);',text)
        if match:return 'Тот же связанный участник: '+self.variable(int(match[1]))+'. Отдельная сущность не создаётся.'
        if text.startswith('Unidentified referent'):return 'Неустановленный участник. Связь с ранее названными участниками не подтверждена.'
        if text.startswith('Current unidentified narrator'):return 'Текущий рассказчик источника; личность не установлена.'
        if text.startswith('A DIFFERENT unidentified narrator'):return 'Другой рассказчик; требуется свидетельство смены говорящего.'
        if text.startswith('Same participant as '):return 'Тот же участник: '+text[len('Same participant as '):].split(' (')[0]+'. Тождество требует контекстного основания.'
        if text.startswith('Defer root selection:'):return 'Отложить выбор внешней связи и сначала разобрать вложенную часть.'
        if '; linked morphology=' in text:
            head=text.split('; linked morphology=')[0]
            for k,v in ROLES.items():head=head.replace(k+'=',v+': ')
            head=re.sub(r'\[(\w+)\]',lambda m:'('+MORPH.get(m[1],m[1])+')',head)
            return head+('. Есть пропущенные роли; их участники определяются отдельно.' if 'omitted roles' in text else '')
        for old,new in [('Outer ','Внешняя связь: '),('applies to','охватывает'),(' binding ',' связывает '),(' (at ',' (внутри '),(' at ',' на позиции '),
            ('its content is the whole remaining area, including the conjunction','область — всё оставшееся выражение вместе с однородными частями'),
            ('each child keeps its own operators and agreement','каждая часть сохраняет свои операторы и согласование')]:text=text.replace(old,new)
        for old,new in OPERATORS.items():text=re.sub(r'\b'+old+r'\b',new,text)
        return text

    def choices(self,d):
        prompt=d.get('last_prompt') or ''
        labels={int(n):text.strip() for n,text in re.findall(r'^\s*(\d+)\. (.+)$',prompt,re.M)}
        mapping={}
        for event in d.get('history',()):
            if event.get('kind')=='SELECTION_LABEL_MAP':
                mapping={ref:n for n,ref in enumerate(event['candidates'],1)}
        for n,encoded in re.findall(r'^\s*(\d+) = (".*")\s*$',prompt,re.M):
            import json
            try:mapping[json.loads(encoded)]=int(n)
            except ValueError:pass
        rows=[]
        for i,ref in enumerate(d.get('candidates',())):
            n=mapping.get(ref);spec=self.specs.get(ref,{})
            # The displayed question and its label map are authoritative together.
            label=labels.get(n) if n is not None else None
            task=self.task_options.get((d.get('frame_id'),ref))
            if label and task:label=self.task_choice(task)
            elif label:label=self.choice_text(label)
            elif spec:label=('Словарный смысл не установлен: ' if spec.get('sense_kind')=='OPEN_LEXICAL' else 'Словарное значение: ')+spec.get('label',spec.get('sense_id','без названия'))
            else:label='Описание варианта не сохранено (вариант '+str(i+1)+')'
            rows.append([str(n if n is not None else i+1),esc(label),'Выбран' if ref in d.get('selected',()) else 'Не выбран'])
        return rows

    def decision(self,d):
        out='<h3>'+esc(QUESTIONS.get(d.get('slot_id'),'Выбор интерпретации'))+'</h3>'
        out+=paragraph('Результат: '+STATUS.get(d.get('outcome'),d.get('outcome') or 'не сохранён'))
        rows=self.choices(d)
        out+=table(['№','Допустимый вариант','Выбор'],rows) if rows else paragraph('Список вариантов не сохранён.')
        if d.get('raw_response') is not None:
            out+=paragraph('Ответ модели: '+str(d['raw_response']).strip())
            out+=paragraph('В этой пробе модель выбирала вариант. Объяснение её рассуждений не записано; номер ответа сам по себе не является обоснованием.')
        for event in d.get('history',()):
            if event.get('kind')=='PROBE_FAILURE':
                if event.get('error_type')=='ProtocolError':
                    out+=paragraph('Ответ отклонён из-за нарушения формата протокола. Выбор не подтверждён.')
                else:
                    out+=paragraph('Проба завершилась ошибкой: '+event.get('error_type','неизвестная ошибка'))
                out+=paragraph('Причина: '+event.get('message','не записана'))
        grounds=d.get('grounds',())
        out+='<h3>Сохранённые основания</h3>'
        if not grounds:out+=paragraph('Основания в снимке отсутствуют.')
        for g in grounds:
            if g.get('text')=='closed source-grounded component question':out+=paragraph('Выбор в закрытом наборе по исходному фрагменту и предоставленному контексту.')
            else:out+=self.fields(g)
        if d.get('history'):out+=paragraph('У решения есть предыдущие состояния: '+str(len(d['history']))+'. Они сохранены в технических подробностях.')
        return out

    def fields(self,record):
        names={'kind':'Тип','event':'Событие','stage':'Этап','reason':'Причина','detail':'Подробности',
            'message':'Сообщение','status':'Состояние','result':'Результат','source_range':'Фрагмент',
            'selected':'Выбрано','remaining':'Осталось','outcome':'Итог','search_complete':'Поиск завершён',
            'search_incomplete':'Поиск неполон','global_search_complete':'Вся память просмотрена',
            'rows':'Найденные записи','proof_results':'Результаты проверки','type':'Тип основания','text':'Описание',
            'value':'Значение','count':'Количество','slot':'Задача','domains':'Домены вариантов',
            'operator':'Оператор','policy':'Правило','backend':'Backend','lmstudio_model':'Модель LM Studio',
            'ollama_model':'Модель Ollama','temperature':'Температура','max_new_tokens':'Лимит ответа'}
        rows=[]
        for k,v in record.items():
            if k not in names or v is None:continue
            if k=='source_range':value=self.excerpt(v)
            elif isinstance(v,bool):value='Да' if v else 'Нет'
            elif isinstance(v,(list,dict)):value='Записей: '+str(len(v))+'; состав доступен в технических подробностях'
            else:value=STATUS.get(str(v),TRACE.get(str(v),OPERATORS.get(str(v),self.alias(str(v)))))
            rows.append([esc(names[k]),esc(value)])
        return table(['Сведения','Значение'],rows) if rows else paragraph('Для этого вида записи понятное описание пока не предусмотрено. Исходные поля доступны во вкладке «Технические данные».')

    def constraint_trace(self,r):
        state=r['constraint_state']
        def name(ref):
            if ref=='ROOT':return 'Общий разбор'
            if ref.startswith('MORPH:'):return 'Морфология «'+self.word(ref[6:])+'»'
            return self.choice_text(self.domain_names[ref]) if ref in self.domain_names else self.word(ref)
        def option(ref):return self.choice_text(self.option_labels[ref]) if ref in self.option_labels else self.alias(ref)
        rules={'SHARED_OCCURRENCE_READING':'Одно вхождение слова должно иметь совместимое морфологическое чтение во всех частях разбора.',
            'NOMINAL_ROLE_AGREEMENT_AND_PARENT':'Проверка согласования, роли участника и слова, к которому он относится.',
            'SCOPE_SINGLE_CONTENT_ACYCLIC_DOMINANCE':'У оператора одна область действия; вложенность должна быть без циклов и совместима с другими операторами.',
            'RESOLVED_SCOPE_EDGE':'Область действия уже выбрана предыдущим решением.',
            'FIXED_SOURCE_DEPENDENCY':'Зависимость уже зафиксирована при разборе исходника.'}
        out=paragraph('Здесь видно, какие варианты оставались на этом шаге и какие ограничения исключили остальные.')
        out+=table(['Что согласуется','Осталось вариантов','Описание вариантов'],[[esc(name(k)),str(len(v)),'<br>'.join(esc(option(x)) for x in v[:15]) + ('<br>Показаны первые 15.' if len(v)>15 else '')] for k,v in list(state.get('domains',{}).items())[:100]])
        rows=[]
        for removal in state.get('removals',())[:100]:
            reason=removal.get('reason');peer=''
            if isinstance(reason,dict):
                peer=' Совместимость с: '+name(reason.get('peer_ref',''))
                why=' '.join(rules.get(x,'Правило без расшифровки: '+x) for x in reason.get('constraints',()))
            else:why=rules.get(reason,'Причина без расшифровки: '+str(reason))
            rows.append([esc(name(removal.get('variable_ref',''))),'<br>'.join(esc(option(x)) for x in removal.get('removed',())[:15]),esc(why+peer)])
        out+='<h3>Исключённые варианты</h3>'+(table(['Область','Исключено','Причина'],rows) if rows else paragraph('На этом шаге исключения не записаны.'))
        if len(state.get('domains',{}))>100 or len(state.get('removals',()))>100:out+=paragraph('Показаны первые 100 записей; остальные доступны в технических данных.')
        return out

    def overview(self):
        receipt=self.index.snapshot.get('commit_receipt',{});out='<h2>Как система поняла текст</h2>'
        out+=paragraph(STATUS.get(receipt.get('terminal'),'Запись результата не подтверждена')+'. Успешная запись не гарантирует верного понимания.')
        from ah.formalizer.probe_diagnostics import configuration_text,activity_text
        out+='<h3>Пробы модели</h3>'+paragraph(configuration_text(self.index.snapshot.get('probe_configuration')))
        out+=paragraph(activity_text(self.index.snapshot.get('probe_activity')))
        roots=self.graph.get('receipt_refs',())
        if roots:
            out+='<h3>Фактически записанное выражение</h3>'+paragraph('Вложенные блоки показывают область действия. Условие внутри «возможно» или «для каждого» не утверждается отдельно.')
            for ref in roots[:30]:out+='<blockquote>'+self.formula(ref)+'</blockquote>'
            if len(roots)>30:out+=paragraph('Показаны первые 30 корней. Остальные доступны в разделе «Граф AH».')
        else:
            out+=paragraph('Записанный граф отсутствует в снимке. Ниже — промежуточные формулы; они не доказывают запись в память.')
            formulas=[e for e in self.index.entries if e.category=='Формулы']
            for e in formulas[:20]:out+='<blockquote>'+self.formula(e.record)+'</blockquote>'
            if len(formulas)>20:out+=paragraph('Остальные формулы доступны в разделе «Формулы».')
            if not formulas:out+=paragraph('Формулы не построены или не сохранены. Откройте диагностику и решения.')
        out+='<h3>Что требует внимания</h3>'
        unknown=[r for r,n in self.nodes.items() if n.get('semantic_status') in {'UNLINKED','OPEN_LEXICAL'}]
        for ref in unknown[:30]:out+=paragraph('Словарный смысл не установлен: '+self.word(self.nodes[ref].get('source_ref','')))
        for e in [e for e in self.index.entries if e.category=='Диагностика'][:30]:out+='<p>'+self.link(e.ref,self.title(e))+'</p>'
        if not unknown:out+=paragraph('Отсутствие сообщений не подтверждает смысловую точность. Проверьте отрицание, область кванторов и одинаковых участников у связанных действий.')
        out+='<h3>Как проверить вручную</h3>'+paragraph('Сравните каждый блок с исходником. Нажмите действие, чтобы увидеть его участников; откройте «Решения», чтобы сравнить выбранный вариант с альтернативами. Выберите ошибочный узел и запишите, что ожидалось.')
        return out

    def explain(self,e):
        if e.category=='Обзор':return self.overview()
        r=e.record;c=e.category;out='<h2>'+esc(self.title(e))+'</h2>'
        if e.source_range:out+='<blockquote>'+esc(self.excerpt(e.source_range))+'</blockquote>'
        if c in {'Формулы','Подформула','Граф AH'}:
            out+=paragraph(STATUS.get(e.status,e.status))
            out+=self.formula(e.ref if c=='Граф AH' else r)
            if c=='Граф AH' and r.get('source_ref'):
                for fid,f in self.frames.items():
                    if f.get('predicate_token_ref')==r['source_ref']:out+='<p>'+self.link(fid,'Разбор «'+f.get('anchor_span','')+'»: роли и решения')+'</p>'
        elif c=='Фреймы':
            sem=r.get('semantic',{});out+=paragraph('Этот вариант не завершён и не должен считаться готовым фактом.' if sem.get('structural_unresolved') else 'Это промежуточный разбор действия или свойства. Фактическую запись смотрите в обзоре.')
            if sem.get('impersonal_predication'):
                out+=paragraph('Безличное состояние: участник в дательном падеже испытывает его. Отдельное подлежащее не добавляется.')
            if sem.get('action_description'):
                out+=paragraph('Это описание действия, а не факт его совершения. Указанные участники сохранены; для остальных ролей сущности и тождества не придуманы. Внешняя связь задаёт возможность, необходимость или статус вложенного содержания.')
            if sem.get('passive_predication'):
                out+=paragraph('Страдательный залог: участник в именительном падеже является объектом действия. Согласование описывает его, а не исполнителя.')
            if sem.get('control_binding'):
                binding=sem['control_binding']
                out+='<p>Участник инфинитива взят из '+self.link(binding['frame_ref'],'родительского действия')+'. Его исходный падеж сохранён; роль в дочернем действии: '+esc(ROLES.get(binding.get('child_role'),binding.get('child_role','не указана')))+'.</p>'
            out+=table(['Роль','Участник','В тексте','Морфология'],self.frame_roles(r))
            for role in sem.get('missing_required_roles',()):out+=paragraph('Не заполнена обязательная роль: '+ROLES.get(role,role))
            for tree in sem.get('operator_forest',()):out+='<h3>Область действия</h3>'+self.formula(tree)
            for ref,d in self.state.get('decisions',{}).items():
                gap=self.gaps.get(d.get('frame_id'))
                if d.get('frame_id')==e.ref or (gap and gap[0]['frame_id']==e.ref):out+='<p>'+self.link(ref,QUESTIONS.get(d.get('slot_id'),'Решение'))+'</p>'
        elif c in {'Решения','Пробы'}:
            if r.get('superseded_by'):out+=paragraph('Это прежняя проба. Её заменило последующее решение.')
            out+=self.decision(r.get('decision',r))
            for i,a in enumerate(r.get('attempts',())[:20]):
                out+='<h3>Предыдущая попытка '+str(i+1)+'</h3>'
                out+=self.decision(a.get('decision',a)) if isinstance(a,dict) else paragraph(str(a))
        elif c=='Морфология':
            out+=paragraph('Варианты словарного чтения. Вероятность словаря не означает, что вариант принят в этом предложении.')
            out+=table(['Начальная форма','Признаки'],[[esc(v.get('lemma','')),esc(self.morphology(v))] for v in r.get('variants',())])
            for fid,f in self.frames.items():
                v=f.get('semantic',{}).get('morph_bindings',{}).get(e.ref)
                if v:out+='<p>В разборе '+self.link(fid,'«'+f.get('anchor_span','')+'»')+': '+esc(self.morphology(v))+'</p>'
        elif c=='Границы условий':
            out+=paragraph('Эта область выбрана как цельное условие. Внешняя композиция должна сохранить её содержимое.')
            rows=[]
            for i,part in enumerate(r.get('operands',())):
                label=('Ограничение / условие' if i==0 else 'Следствие / тело') if r.get('operator')=='IMPLIES' else ('Связанная переменная' if i==0 and r.get('operator') in {'FORALL','EXISTS'} else 'Содержимое')
                rows.append([esc(label),esc(self.excerpt(part.get('source_range')) if part.get('source_range') else 'Без собственного фрагмента текста')])
            out+=table(['Часть условия','Исходный текст'],rows)
        elif c=='Без привязки':out+=paragraph('Это слово не связано с фреймом в сохранённом разборе. Оно может быть служебным словом либо пропуском разбора. Проверьте его роль в исходном предложении.')
        elif c=='Привязки':out+=paragraph('Установленная ссылка: '+self.target(r.get('target')))
        elif c=='Трасса' and r.get('kind')=='DEFERRED_CLAUSE_BOUNDARY':
            out+=paragraph('Возможна вложенная часть высказывания. Разбиение на самостоятельные предложения отложено: сначала нужно подтвердить владельца и полные границы содержания отдельной пробой.')
        elif c=='Трасса' and r.get('kind')=='SEMANTIC_PRIOR_EXCLUDED':
            out+=paragraph('Прежний смысловой разбор слова «'+self.word(r.get('predicate_ref',''))+'» не применяется: '+
                ('его часть речи не соответствует выбранному чтению.' if r.get('reason')=='MORPHOLOGY_INCOMPATIBLE' else
                 'его роли несовместимы с текущим разбором, хотя ресурс проверен.')+
                ' Опыт не меняет грамматику текущего фрагмента и не делает поиск незавершённым.')
        elif c=='Трасса' and r.get('kind')=='STRUCTURAL_PARTITION_COVERAGE':
            out+=paragraph('Разбиение потеряло значимые слова: «'+' '.join(self.word(t) for t in r.get('uncovered_token_refs',()))+
                ('». Они не могут исчезнуть во вводящем выражении. Нужно расширить родительскую часть или пересмотреть связь; запись вложенной части отдельно заблокирована.' if r.get('relation') in {None,'CONTENT'} else
                 '». Проба отнесла их к описываемому событию или состоянию. Нужно пересмотреть границы содержания; запись неполного выражения заблокирована.'))
            if r.get('status')=='REPAIRED':
                out+=paragraph('Это противоречие прежнего разбиения устранено: новые границы сохраняют перечисленные слова в содержании.')
                out+='<p>'+self.link(r['replacement_decision_ref'],'Проверка исправленного разбиения')+'</p>'
        elif c=='Трасса' and r.get('kind')=='STRUCTURAL_BOUNDARY_DOMAIN':
            words=' '.join(self.word(t) for t in r.get('required_content_refs',()))
            out+=paragraph('В текущем варианте внешней связи «'+OPERATORS.get(r.get('relation'),r.get('relation',''))+'»'+
                (' слова «'+words+'» должны остаться в содержании.' if words else ' выбраны границы частей.'))
            out+=paragraph({'RESTRICTED':'Несовместимые границы исключены. Контур запрашивает новые границы, сохраняя выбранную внешнюю связь.',
                'RESOLVED':'Новое полное разбиение подтверждено. Дочерние части ещё должны пройти собственный разбор.',
                'PENDING':'Совместимое разбиение не подтверждено. Факт не записывается.',
                'SELECTED':'Полное разбиение подтверждено; дочерние части проверяются отдельно.'}.get(r.get('status'),'Разбор не завершён.'))
            out+=paragraph('Это условие только текущего варианта разбора. Оно не становится правилом для слова и не переносится в другую область или связь.')
            for proof in r.get('constraint_proofs',()):
                out+='<p>'+self.link(proof['decision_ref'],'Почему слово должно остаться в содержании')+'</p>'
        elif c=='Трасса' and r.get('kind')=='CONTENT_SEPARATOR_OWNERSHIP':
            out+=paragraph('Предложено отнести к связи с вложенным содержанием знаки «'+
                ' '.join(self.word(t) for t in r.get('separator_refs',()))+'». Родительская часть после этого: «'+
                ' '.join(self.word(t) for t in r.get('parent_after',()))+'».')
            out+=paragraph('Разбиение подтверждено пробой; завершение вложенных частей проверяется отдельно.' if r.get('status')=='CONFIRMED' else
                'Это предложение по пунктуации ещё не подтверждено полным разбиением и не разрешает запись факта.')
            if r.get('decision_ref'):out+='<p>'+self.link(r['decision_ref'],'Проверка полного разбиения')+'</p>'
        elif c=='Трасса' and r.get('kind')=='DEPENDENCY_REJECTED':
            out+=paragraph('Этот вариант зависимостей слова «'+self.word(r.get('predicate_ref'))+'» отклонён: '+
                ('проба не подтвердила ни одного прикрепления.' if r.get('reason')=='NO_LICENSED_ATTACHMENT' else
                 'грамматические ограничения не оставили допустимых вариантов для «'+' '.join(self.word(t) for t in r.get('empty_domains',()))+'».')+
                ' Это результат проверки отдельного варианта, а не вывод о невозможности разобрать всё предложение.')
        elif c=='Трасса' and r.get('kind')=='STRUCTURAL_TASK':
            out+=paragraph(QUESTIONS.get(r.get('slot'),'Выбор части разбора'))
            reasons={'CONTEXT_LIMIT':'Фрагмент превышает допустимый размер контекста. Проба не вызывалась.',
                'SEARCH_LIMIT':'Бюджет поиска исчерпан. Оставшиеся варианты не проверены.',
                'GRAMMAR_SEARCH_LIMIT':'Перебор грамматических вариантов не завершён. Проба связи не вызывалась.',
                'NO_REMAINING_CANDIDATES':'Предложенные варианты закончились. Это не доказательство отсутствия связи в языке.',
                'NONE_FIT':'Ни один вариант этой порции не подошёл. Поиск продолжится, если остались варианты.',
                'INSUFFICIENT_CONTEXT':'Не хватает контекста. Следующая порция не подменяет неопределённый ответ.',
                'MULTIPLE_ADMISSIBLE':'Остались несколько допустимых вариантов.',
                'PROBE_BLOCKED':'Подтверждённого ответа нет. Проверьте связанное решение и диагностику.'}
            out+=paragraph('Локальный выбор подтверждён; согласование дочерних частей проверяется отдельно.' if r.get('selected') else reasons.get(r.get('reason'),'Задача не завершена.'))
            if r.get('context_policy')=='OWNED_TARGET':
                out+=paragraph('Текст этой структурной задачи: «'+' '.join(self.word(t) for t in r.get('target_token_refs',()))+
                    '». Слова внешних областей в вопрос не включены; ограничения входного слота переданы отдельно.')
            elif r.get('context_policy')=='TARGET_WITH_CONTEXT':
                out+=paragraph('Текст этой структурной задачи: «'+' '.join(self.word(t) for t in r.get('target_token_refs',()))+
                    '». Окружение доступно для понимания смысла и грамматики. Выбор относится к указанным словам; внешние операторы не присваиваются им повторно.')
            out+=paragraph('Порция: '+str(r.get('page',0)+1)+'. Рассмотрено вариантов: '+str(r.get('examined',0))+'.')
            if r.get('enumeration_complete') is False:out+=paragraph('Остались непоказанные варианты. Локальный выбор не означает полного перебора.')
            if r.get('alternatives'):out+=table(['Вариант','Выбор'],[[esc(self.task_choice(v)),'Выбран' if v.get('candidate_id')==r.get('selected') else 'Не выбран'] for v in r['alternatives']])
        elif c=='Трасса' and r.get('kind','').startswith('DISPATCH_'):
            names={'COMPOSITION':'Согласование структуры', 'AGREEMENT':'Проверка согласования слов',
                   'PARTITION':'Согласование границ и принадлежности слов',
                   'MORPHOLOGY':'Выбор морфологических чтений', 'GRAMMAR':'Грамматические варианты',
                   'GOAL_CONTEXT':'Контекст и проверка логических целей'}
            out+=paragraph(names.get(r.get('task_kind'),'Морфология текущей области'))
            explanations={
                'DISPATCH_COMPLETED':'Задача рассчитана по текущим входам. Зависимые результаты теперь могут использовать эту версию.',
                'DISPATCH_REUSED':'Входы и версии зависимостей не изменились. Повторный расчёт и новые вопросы модели не нужны.',
                'DISPATCH_INVALIDATED':'Изменились входы задачи или результат, от которого она зависит. Старый результат сохранён в истории, но больше не разрешает завершить разбор.',
                'DISPATCH_RECHECK':'Во время расчёта изменился уже использованный результат. Диспетчер повторно согласует задачу; смешение версий не допускается.',
                'DISPATCH_MORPHOLOGY':'Чтения слов проверяются для этой области и её текущего родительского слота. Исходные словоформы сохранены.'}
            explanation=explanations.get(r['kind'],'Состояние зависимой задачи изменилось.')
            if r.get('reason')=='REJECTED_COMPOSITION_DISCARDED':
                explanation='Неудачная попытка построения целиком отклонена. Следующая версия использует зависимости нового разбора; история прежних решений сохранена.'
            out+=paragraph(explanation)
            if r.get('token_refs'):out+=paragraph('Область: «'+' '.join(self.word(t) for t in r['token_refs'])+'».')
            if r.get('revision'):out+=paragraph('Версия результата: '+str(r['revision'])+'.')
            def task_label(ref,revision=None):
                entry=self.dispatch_versions.get((ref,revision)) if revision else self.dispatch_tasks.get(ref)
                if not entry:return 'Зависимая задача (описание не сохранено)'
                row=entry.record
                label=names.get(row.get('task_kind'),'Задача')
                if row.get('token_refs'):label+=': «'+' '.join(self.word(t) for t in row['token_refs'])+'»'
                elif entry.source_range:label+=': «'+self.excerpt(entry.source_range,120)+'»'
                return self.link(entry.ref,label)
            if r.get('changed_task_ref'):
                out+='<p>Причина пересмотра: '+task_label(r['changed_task_ref'])+'.</p>'
            if r.get('dependencies'):
                out+=table(['Использованный результат','Версия'],[
                    [task_label(d['task_ref'],d['revision']),str(d['revision'])] for d in r['dependencies']])
        elif c=='Трасса' and r.get('kind')=='MORPHOLOGY_DOMAIN_RESTRICTION':
            out+=paragraph('Для слова «'+self.word(r.get('token_ref'))+'» выбрано чтение: '+self.task_choice(r))
            out+=paragraph('Это чтение ещё проверяется вместе с ролями и согласованием всей конструкции. '
                'Выбор начальной формы сам по себе не устанавливает значение слова или тождество упомянутых объектов.')
        elif c=='Трасса' and r.get('kind')=='STRUCTURAL_REVISION_STALLED':
            out+=paragraph('Повторены те же локальные решения без устранения ошибки. Нового различающего свидетельства нет. '
                           'Разбор оставлен неразрешённым; одинаковые вопросы дальше не отправляются.')
        elif c=='Трасса' and r.get('kind')=='TEMPORAL_PREDICATE_EXCLUDED':
            out+=paragraph('Слово «'+self.word(r.get('predicate_ref'))+'» входит в распознанное временное выражение. '
                           'Оно не может одновременно стать предикатом этой конструкции.')
        elif c=='Трасса' and r.get('kind')=='COMPOSITION_EQUIVALENT_SOURCES':
            out+=paragraph('Грамматический и компонентный разбор дали одну и ту же простую предикацию. '
                           'Совпали исходные слова, роли, морфологические чтения и допустимые валентные привязки. '
                           'Выбор источника не требует вопроса модели; происхождение обоих вариантов сохранено.')
            out+=table(['Предикат','Роли'],[[esc(self.word(r.get('predicate_ref'))),
                esc('; '.join(role+' = '+self.word(tid) for tid,role in r.get('roles',{}).items()))]])
        elif c=='Трасса' and r.get('kind')=='COMPOSITION_PRODUCERS':
            out+=paragraph('Проверены все применимые источники. Наличие грамматического разбора не отключает компонентный поиск.')
            out+=table(['Источник','Кандидатов'],[[{'GRAMMAR':'Грамматика','COMPONENT':'Компонентная композиция'}.get(x['source'],x['source']),str(x['frames'])] for x in r.get('sources',())])
        elif c=='Трасса' and r.get('kind')=='STRUCTURAL_RELATION_COMPOSED':
            out+=paragraph(OPERATORS.get(r.get('relation'),'Связь')+'. Части и границы согласованы.')
            if r.get('tree'):out+=self.formula(r['tree'])
            if r.get('owner_ref'):out+=paragraph('Владелец: «'+self.word(r['owner_ref'])+'». Содержание: «'+self.word(r.get('content_ref'))+'». Оно отдельно не утверждается.')
        elif c=='Трасса' and r.get('kind')=='ATTITUDE_COMPOSITION':
            out+=paragraph('Вложенное содержание связано с высказыванием.' if r.get('resolved') else 'Попытка присоединить вложенное содержание; завершение связи не подтверждено.')
            out+=table(['Часть разбора','Исходный текст'],[
                ['Высказывание',esc(self.word(r.get('parent_anchor')))],
                ['Содержание',esc(self.excerpt(r.get('content_range')))]])
            scope=r.get('delimiter_scope',{})
            if scope.get('marker_ref'):
                out+=paragraph('Слово «'+self.word(scope['marker_ref'])+'» выбрано как союз, вводящий вложенную часть.')
            out+=paragraph('Содержание не утверждается как самостоятельный факт.')
        elif c=='Трасса' and r.get('event')=='FEATURE_CHECK_BATCH':
            rows=[[esc(self.word(x[1])),str(x[2]+1),'Подошёл' if x[3] else 'Не подошёл'] for x in r.get('checks',())[:100]]
            out+=paragraph('Проверка вариантов слов на соответствие одному грамматическому правилу. Отказ здесь не означает ошибку всего предложения.')
            out+=table(['Слово','Номер морфологического варианта','Проверка'],rows)
            if len(r.get('checks',()))>100:out+=paragraph('Показаны первые 100 проверок; остальные сохранены в технических данных.')
        elif c=='Трасса' and 'constraint_state' in r:out+=self.constraint_trace(r)
        elif c=='Трасса' and r.get('alternatives'):
            out+=table(['Вариант области','Выбор'],[[esc(self.choice_text(x.get('label','Описание не сохранено'))),'Выбран' if x.get('candidate_id')==r.get('selected') else 'Не выбран'] for x in r['alternatives'][:100]])
        elif c=='Контекст':
            out+=paragraph('Адресное обращение к памяти. Ничего не найдено в просмотренной области не означает, что сведений нет во всей памяти.')
            out+=self.fields(r)
            for proof in r.get('proof_results',())[:30]:out+=self.fields(proof)
        elif c=='Диагностика':out+=paragraph(DIAGNOSTICS.get(r.get('code'),'Сообщение сохранено без готовой расшифровки: '+str(r.get('code',''))))+self.fields(r.get('detail') if isinstance(r.get('detail'),dict) else r)
        elif e.ref=='receipt':out+=paragraph('Результат: '+STATUS.get(r.get('terminal'),r.get('terminal') or 'не сохранён'))+paragraph('Записанных фрагментов: '+str(len(r.get('committed_fragments',()))))
        elif e.ref=='runtime-configuration':out+=self.fields(r.get('llm',{}))
        else:out+=self.fields(r)
        links=self.index.links(e)
        if links:out+='<h3>Связанные части разбора</h3><ul>'+''.join('<li>'+self.link(ref,self.title(self.index.by_ref[ref]))+'</li>' for ref in links[:40])+'</ul>'
        return out

    def report(self,notes):
        body='<h1>Проверка формализации</h1><h2>Исходный текст</h2><pre style="white-space:pre-wrap">'+esc(self.index.text)+'</pre>'+self.overview()
        entries=[e for e in self.index.entries if e.category in {'Решения','Границы условий','Диагностика','Привязки'} or e.category=='Трасса' and e.record.get('kind') in {'STRUCTURAL_TASK','STRUCTURAL_RELATION_COMPOSED','COMPOSITION_PRODUCERS','COMPOSITION_EQUIVALENT_SOURCES','STRUCTURAL_REVISION_STALLED','TEMPORAL_PREDICATE_EXCLUDED','DISPATCH_INVALIDATED','DISPATCH_RECHECK','DISPATCH_MORPHOLOGY'}]
        for e in entries[:1000]:body+='<hr>'+self.explain(e)
        if len(entries)>1000:body+=paragraph('Отчёт ограничен первыми 1000 записями. Полный снимок сохраните отдельно для повторного открытия.')
        body+='<h2>Замечания проверяющего</h2>'+table(['Оценка','Фрагмент','Комментарий'],[[esc(n.get('verdict','')),esc(self.excerpt(n.get('source_range'))),esc(n.get('comment',''))] for n in notes])
        # Standalone reports have no application link handler.
        body=re.sub(r'<a href="review:[^"]*">(.*?)</a>',r'\1',body,flags=re.S)
        return document(body)
