#!/usr/bin/env python3
"""Build independent, symbolic, checkpoint-based gold from the attached V7 specification.
No import of AG_Memory or its outputs. This generator is NOT a formalizer or test adapter.
"""
from __future__ import annotations
import argparse, copy, hashlib, itertools, json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/formalizer_v7_oracle'
CASES=[]
MECHANISMS={}

def canonical(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(x): return hashlib.sha256(x).hexdigest()
def pred(name, **roles): return {'predicate':name,'roles':roles}
def g(op,*args): return {'operator':op,'operands':list(args)}
def ent(name): return {'entity':name}
def var(name): return {'bound_var':name}
def point(t): return {'kind':'POINT','t':t}
def interval(a,b,sem='EXISTENTIAL'): return {'kind':'INTERVAL','bounds':[a,b],'semantics':sem}
def check(path,value,op='eq'): return {'op':op,'path':path,'value':value}
def same(path,checkpoint): return {'op':'same_as','path':path,'checkpoint':checkpoint}
def step(id,action,payload=None,checks=None): return {'id':id,'action':action,'payload':payload or {},'checks':checks or []}
def facts(fs):
    # Three channels are inspected; structural nodes do NOT count as asserted formulas.
    return [check('/assertions/ah',fs,'set_eq'),check('/assertions/ir',fs,'set_eq'),check('/assertions/journal',fs,'set_eq')]
def forbidden(fs):
    return [check('/assertions/'+ch,fs,'excludes') for ch in ('ah','ir','journal')]
def raw(text,id='O1',kind='ASSERTION',timestamp='2026-10-09T12:00:00+00:00'):
    return {'text':text,'source_id':id,'revision':1,'range':[0,len(text)],'language':'ru','source_timestamp':timestamp,'batch_kind':'MESSAGE','request_kind':kind}
def add(id,title,mechs,steps,*,tier='component',a=(),dr=(),profile='known',tags=(),description=''):
    if isinstance(mechs,str): mechs=mechs.split()
    refs=sorted({r for m in mechs for r in MECHANISMS[m]['norm_refs']})
    CASES.append({'schema_version':'v7-symbolic-oracle-1','case_id':id,'title':title,'tier':tier,'mechanisms':mechs,'norm_refs':refs,'acceptance_refs':list(a),'dry_run_refs':list(dr),'fixture_profile':profile,'tags':list(tags),'description':description,'initial_state':'EMPTY','steps':steps})
def mech(id,refs,title): MECHANISMS[id]={'title':title,'norm_refs':refs.split(),'case_ids':[]}

# Independent contract inventory: coverage is by mechanism, not by document line count.
INVENTORY='''
input|§1.1|Валидация RawInput и отсутствие побочных записей при отказе
observation_key|§1.1|Ключ observation не содержит source_revision
revision|§1.1 §8.1|Повтор, конфликт байтов и declared v+1
canonical_ids|§1.3|Стабильные IDs, canonical serialization и коллизии
contexts|§1.2|GenerationContext и ResolutionContext; frozen declared reads
grounds|§1.3 §7.2 §7.4|Truth O/C/W отдельно от interpretation R/D/M/A/P
source_trace|§5.1|Ровно пять CandidateSourceTrace на слот
source_exhaustion|§5.1 §10|FOUND=0, пять терминальных traces, честное исчерпание
source_blocked|§5.1 §5.3|BLOCKED не равен пустоте и запрещает RESOLVED
selector|§5.2|ID-selector ONE/MULTIPLE/NONE и проверка протокола
value_grounds|§5.3|Ground каждого выбранного/выжившего значения
constraint_search|§5.3|Arc consistency, циклические кластеры, полный bounded search
alternatives|§3 §5.3|LinkedAlternative не теряется без RejectionRecord
oscillation|§5.4|Freeze повторного состояния, M не re-arm
budget|§0 §9|Независимые лимиты, FROZEN, timing replay
resource_schema|§2.1 §2.4|Закрытые CandidateSchema, IDs, enums, dependencies, cycles
release_trust|§2.4|Подпись, trust registry, timestamp, content/coverage hash
resource_missing|§2.1 §5.1|RESOURCE_MISSING не CHECKED_EMPTY
resource_permutation|§2.2|Перестановки entries не меняют результат
coverage_report|§2.3 §2.4|Фиксированный корпус и раздельные ресурсные/семантические категории
morph_unknown|§2.1 §4.1 §4.3|UNKNOWN-признак не отрицание; hard morph agreement
raw_alignment|§4.1|Полное исходное покрытие токенами, пробелами, пунктуацией
srl_boundary|§4.1|SRL не создаёт смысл/факты; typo prior и KEEP_AS_IS
structural_heads|§4.2 §4.5|Глагольные, nonfinite, nominal, impersonal, elliptic centers
multi_anchor|§4.5|Несколько lexical anchors; запрет opaque целой строки
attachment|§4.2 §4.3|Только проверенные attachment и SURFACE_ARG
proposal_validation|§4.5 §5.2|Типы, anchors, cycles, локальные roles, никакого UID/g/truth
proposal_bounds|§4.5 §9|Finite proposal budget и полный отказ неполного префикса
seal|§4.3 §4.5|Structural seal; T3 не меняет структуру
scopes|§4.3 §6.2|Вложенность, depth/source order, OR/XOR/NOT/quantifiers
coreference|§4.3 §7.3|Адресная coreference, окно, собственные binding paths
existential_ref|§3 §6.2|Локальный ExistentialRef вместо фиктивного M
open_lexical|§5.1 §7.1|Изолированный UNLINKED T; exact attestation, no alias
open_key|§7.1|Occurrence-local key, роли/attachment/spans, контекстный replay
known_mapping|§7.1 §7.2|Известный sense без TemplateMap не обходится open
coverage|§1.3 §2.3|FULL/OPEN/PARTIAL/NONE ортогональны outcome
partial|§7.2|Независимые ASSERTED фрагменты, нет скрытой полной opaque интерпретации
modus|§0 §6.1|ASSERTION/QUERY/COMMAND/MIXED и косвенный speech act
som|§7.5|Материализация структурных N/G/M без truth-support
attitude_links|§3 §7.5|ATTITUDE per-observation/holder, UNKNOWN map
operator_links|§3 §7.5 §17|Канонические OPERATOR ссылки только proposition slots
s_access|§7.5 §8.2|Транзитивная S-access от F-visible, нет самоподдерживающего цикла
reaccess|§3 §8.2|Старые опоры мертвы, узлы переиспользуются и REACCESSIBLE
node_events|§3 §8.3|Type-dependent identity, support_id, T/seq, атомарный audit
event_audit_integrity|§3 §8.3|Неповреждаемый audit; индекс rebuild, corruption fail-safe
state_identity|§6.3 §7.1|RelationKey без времени, STATE один N и независимые опоры
occurrence_identity|§7.1 §7.6|EVENT/PROCESS/TRANSITION/UNKNOWN разные occurrences
function_identity|§7.3 §15|Синтаксический typed порядок, commutative только AND/OR/XOR
and_commit|§7.4 §15|AND_ELIMINATION commit-time, корень ROOT, дети DERIVED
or_demand|§7.4 §15|N-ary OR on-demand, все n−1 отрицаний
forall_demand|§6.2 §7.4|Два операнда FORALL; root-only commit; instance on-demand
modus_ponens|§15|IMPLIES+antecedent, без converse/contraposition
modal_guard|§6.1 §15|Модальность, отрицание, цитата и hypothetical не утверждают операнд
association|§6.3 §15|ASSOCIATION не CAUSE/IMPLIES
registered_ops|§15 §17|g/L лишь с полным handler/schema/codec; rollback неизвестных
time_absent|§6.3 §7.1|Недатированный SupportRecord без TimeAssertion
time_default|§6.3|POINT/EXISTENTIAL/CONTINUOUS, явное время и source timestamp
time_symbolic|§6.3|Символические границы без runtime now и без угадывания
simultaneity|§6.3|∀ независимых реализаций, все комбинации и singleton
query_time|§6.3|Точечный и экзистенциальный запрос, bounds/coverage
query_not_time|§6.3|NOT-root область отрицания; Q subset I для NO
no_interpolation|§6.3|Два point witness не доказывают между ними
or_time|§7.4|Каждая реализация OR покрыта NOT, mixed unknown
forall_time|§6.3|Симметричная temporal license и вычисленная область
multi_premise_time|§6.3|Общее пересечение всех premises, не попарная лицензия
witness_correlation|§7.6|AND наследует общий witness; равные bounds не корреляция
time_provenance|§17|source×support, матрица ROOT/DERIVED, атомарная пара
assertion_retraction|§8.2 §17|По assertion_id любой source, SupportRecord жив, durable dedup
effective_time|§6.3 §8.2|Ledger LIVE при мёртвом пути; effective visibility
conflict_admission|§6.3 §7.3|Текущий AH и взаимные конфликты внутри batch
conflict_pairs|§6.3|Один отчёт на пару; CandidateCommitted и TwoCandidate
conflict_open|§6.3 §8.2|Все evidences эффективны, REPORT_CLOSED, born closed
conflict_late|§6.3|Новый ресурс: поздний отчёт, no auto-retract
precheck|§6.3 §7.2|GATE_PRECHECK только диагностика, не отчёт и не terminal
fragment_plan|§6.3 §7.3|plan\\E closure; общие ops сохранены, исключённые опоры отсутствуют
writers|§0 §7.3 §17|C read-only, T6/Goal/status права дизъюнктны
batch_idempotence|§7.2 §7.3|batch hash и marker; повтор без новых операций
head_order|§7.3 §8.3|Глобальный head-only, PENDING_ADMISSION_ORDER не durable
stale_plan|§7.3 §8.3|STALE_SUPERSEDED terminal; следующий head продолжает
commit_decision|§7.3 §8.3|Marker+D атомарны; APPLIED из D без re-admission
full_reject|§7.3|Полный отказ: один append с кандидатами/отчётами, без D/marker
batch_recovery|§8.3|Все crash-окна и точная пара version/marker
run_binding|§0 §7.2|CAS run до первого вывода; чужой run investigation-only
provider_log|§0 §9|PENDING/RECEIVED fsync, ordinal≠attempt, replay byte-identical
goal_dedup|§8.3 §17|Четыре компонента; request_window не ключ
goal_decision|§8.3 §17|Решение атомарно с эффектом; created = путь, не узел
goal_dbn|§8.3 §18|DB-N общая сериализация с отзывом для NOOP/ABORTED
goal_recovery|§8.3|R0 historical, R1/R2 STALE/LICENSE/NOOP/APPLIED
goal_license_race|§8.3 §10|До PENDING mismatch без GOAL, после GOAL_LICENSE_FAILED
support_paths|§7.4 §8.2|Любой полный путь достаточен; частичные не склеиваются
binding_paths|§7.3 §8.2|Отзыв antecedent инвалидирует только зависимые binding paths
source_retraction|§8.2|Всё observation vs одна версия, audit сохраняется
closure_independence|§8.2|Общее R не зависимость, общий W/C factual зависимость
states|§8.4|SEALED только version; outcomes/coverage отдельно от machine state
rx|§2.1 §7.3|Stage-isolated prior, только committed/live writes, frozen replay
declared_trigger|§1.2 §8.1|Изменение declared read подписка и recompute, не обязательная смена исхода
migration|§14 §17|Open→known явные evidence, новые пути и атомарный visibility switch
migration_bulk|§14|Frozen per-source CAS targets, receipt, per-item atomicity
migration_failure|§14|Rollback до commit; после commit старые опоры не оживают
legacy_adapter|§12 §17|Lossless V2/legacy только representable; ADAPTER_NOT_COVERED
dsl|§16|Текст BNF↔JSON AST, precedence, typed emits, closed data-only DSL
dsl_limits|§16|Chars/rules/depth/joins, UNKNOWN не eval, invalid whole release
goal_compile|§6.3 §17|WH/YESNO/COUNT/CAUSE/ASSOC/COUNTERFACTUAL разные targets
workspace|§6.3|Только возбуждённые источники, cold activation, no global scan
exact_attestation|§6.3 §17|Все lexical/role/scope fields, source scope, no derived write
numeric_scope|§6.3 §17|BoundVar+body+CountLiteral, int bounds, no fake n facts
count_domain|§6.3 §17|Distinct M, lower bound, DomainCertificate для exact/atmost
compound_binding|§6.3 §17.3|Полный WH/COUNT scope, QueryVar без AH UID
formula_domain|§6.3|Alpha-normalized formula certificate и live completeness
ordering_goal|§17.3|BEFORE max<min, DURING coverage, no possible overlap proof
query_budget|§6.3|1024 combinations, incomplete enumeration не closed domain
query_readonly|§6.3 §17|Runtime results не facts/versions/markers
oracle_replay|§11.2|Exact IDs/diagnostics/structural delta/replay, no learned gold
coverage_gate|§20|G5 unknown corpus ≥500 и пороги; oracle не proof универсальности
'''
for line in INVENTORY.strip().splitlines():
    i,r,t=line.split('|',2); mech(i,r,t)

IVAN=ent('ivan'); PETR=ent('petr'); MARIA=ent('maria'); BOOK=ent('book'); TABLE=ent('table'); SHELF=ent('shelf')
P=pred('ARRIVE',AGENT=IVAN); Q=pred('ARRIVE',AGENT=PETR); S=pred('SLEEP',AGENT=MARIA)
LOC=pred('LOCATIVE',THEME=BOOK,LOCATION=TABLE)
LOC2=pred('LOCATIVE',THEME=BOOK,LOCATION=SHELF)
BODY=g('IMPLIES',pred('STUDENT',THEME=var('x')),pred('PASS_EXAM',AGENT=var('x')))
ALL=g('FORALL',var('x'),BODY)

# A case anchors. Later families exercise their variants rather than merely repeating IDs.
def lang(id,text,fs,mechs,*,a=(),dr=(),profile='known',extra=(),tags=(),kind='ASSERTION',gold=None):
    payload={'raw_input':raw(text,id,kind),'provider_script':'VALID_LOCAL','resource_profile':profile}
    checks=facts(fs)+list(extra)
    if gold is not None: checks.append(check('/generation/gold_patterns',gold,'contains'))
    add(id,text,mechs,[step('ingest','formalize',payload,checks)],tier='pipeline',a=a,dr=dr,profile=profile,tags=tags)

def scenario(id,title,mechs,actions,a=(),dr=(),tags=()):
    add(id,title,mechs,actions,tier='durability',a=a,dr=dr,tags=tags)

def component(id,title,mechs,operation,payload,checks,a=(),dr=(),profile='known'):
    add(id,title,mechs,[step('result',operation,payload,checks)],a=a,dr=dr,profile=profile)

# Each acceptance family has nonempty gold and negative checks where relevant.
lang('A01','Иван сказал, что Пётр пришёл.',[pred('SAY',AGENT=IVAN,CONTENT=Q)],'som attitude_links modal_guard',a=['A01'],dr=['DR4'],extra=[check('/supports/root_targets',[{'formula':pred('SAY',AGENT=IVAN,CONTENT=Q)}],'set_eq'),check('/structural/formulas',[Q],'contains')])
lang('A02','Иван и Пётр пришли.',[P,Q,g('AND',P,Q)],'structural_heads scopes and_commit',a=['A02'],extra=[check('/generation/coordination_kind','NOMINAL_GROUP')])
lang('A03','Иван пришёл и Мария уснула.',[g('AND',P,S),P,S],'scopes and_commit time_provenance',a=['A03'],extra=[check('/supports/derived_rules',['AND_ELIMINATION','AND_ELIMINATION'],'multiset_eq')])
component('A04','Или…или без доказанной исключительности','alternatives scopes or_demand','resolve_structure',{'text':'Или Иван, или Пётр пришёл.','scope_alternatives':['OR','XOR'],'grounds_per_value':False},[check('/decision/outcome','UNRESOLVED'),check('/diagnostics/codes',['NO_GROUNDED_CANDIDATE'],'contains'),check('/alternatives/operators',['OR','XOR'],'set_eq')]+facts([]),a=['A04'])
scenario('A05','Сбой после T5 до T6','batch_recovery batch_idempotence',[
 step('journal','journal_batch',{'batch':'B','seq':1,'formulas':[P]},[check('/store/markers',[]),facts([])[0]]),
 step('crash','crash',{'boundary':'AFTER_T5_FSYNC'},[check('/journal/batch_pending',['B'])]),
 step('recovered','recover',{},facts([P])+[check('/store/markers',['B'],'set_eq'),check('/journal/batch_terminal',{'B':'APPLIED'})]),
 step('repeat','recover',{},[same('/state/semantic_digest','recovered')])],a=['A05'],dr=['DR3'])
sc=g('NOT',g('FORALL',var('x'),g('IMPLIES',pred('STUDENT',THEME=var('x')),g('POSSIBLE',g('NOT',pred('PASS_EXAM',AGENT=var('x')))))))
lang('A06','Не каждый студент мог не сдать экзамен.',[sc],'scopes modal_guard som forall_demand',a=['A06'],dr=['DR1'],extra=[check('/supports/root_count',1),check('/store/forall_instance_count',0)])
scenario('A07','Два независимых STATE-пути с общим R','support_paths state_identity closure_independence source_retraction',[
 step('two','seed_state',{'node':'N','formula':LOC,'supports':['s1','s2'],'source_tags':['O1:v1','O2:v1'],'shared_rule_refs':['R_LOCATIVE']},[check('/nodes/N/f_visible',True)]),
 step('one','retract_observation',{'observation':'O1'},[check('/nodes/N/f_visible',True),check('/supports/s1/status','SUPERSEDED'),check('/supports/s2/status','LIVE')]),
 step('zero','retract_observation',{'observation':'O2'},[check('/nodes/N/f_visible',False)])],a=['A07'],dr=['DR7'])
component('A08','Coreference с явным контекстом и hard gender','coreference morph_unknown binding_paths','resolve_reference',{'text':'Она взлетела.','antecedents':[{'entity':'plane','gender':'neut'},{'entity':'rocket','gender':'femn'}],'context_facts':['rocket_at_launchpad'],'value_grounds':{'rocket':['P:O_rocket']}},[check('/decision/outcome','RESOLVED'),check('/binding/target','rocket'),check('/rejections/entities',['plane'],'contains')],a=['A08'],dr=['DR2'])
component('A09','Два grounded antecedent без dominance','coreference value_grounds alternatives','resolve_reference',{'text':'Он вошёл.','antecedents':['ivan','petr'],'value_grounds':{'ivan':['P:O1'],'petr':['P:O2']}},[check('/decision/outcome','AMBIGUOUS'),check('/alternatives/entities',['ivan','petr'],'set_eq')]+facts([]),a=['A09'])
component('A10','OOV сохраняется несмотря на edit-distance','srl_boundary open_lexical morph_unknown','lexical_candidates',{'text':'Зорбекс прибыл.','surface':'Зорбекс','nearest_dictionary_form':'зоркий','edit_distance_prior':True},[check('/lexical/retained_surfaces',['Зорбекс'],'contains'),check('/lexical/auto_replacements',[])],a=['A10'],profile='open')
lang('A11','Кто-то вошёл, а затем он сел.',[g('EXISTS',var('x'),g('AND',pred('ENTER',AGENT=var('x')),pred('SIT',AGENT=var('x'))))],'existential_ref coreference scopes',a=['A11'],extra=[check('/store/fictitious_entities',[]),check('/bindings/discourse_variable','x')])
lang('A12','Возможно, Иван пришёл.',[g('POSSIBLE',P)],'modal_guard scopes',a=['A12'],extra=forbidden([P]),dr=['DR31'])
lang('A13','Если Иван пришёл, то Мария спит.',[g('IMPLIES',P,S)],'modus_ponens som modal_guard',a=['A13'],extra=forbidden([P,S]))
lang('A14','Если бы Иван пришёл, Мария бы уснула.',[g('COUNTERFACTUAL',P,S)],'modal_guard goal_compile',a=['A14'],extra=forbidden([P,S]))
component('A15','Ассоциация не причинность','association goal_compile','association_query',{'left':P,'right':S,'independent_sources':True,'relation_id':'ASSOCIATED'},[check('/answer/kind','ASSOCIATIVE'),check('/answer/is_entailment',False)]+forbidden([g('IMPLIES',P,S),pred('CAUSE',LEFT=P,RIGHT=S)]),a=['A15'])
component('A16','Вчера без source time — символический anchor','time_symbolic time_default','parse_time',{'raw_input':dict(raw('Книга была на столе вчера.'),source_timestamp=None)},[check('/time/symbolic',True),check('/time/clock_default_used',False),check('/diagnostics/codes',['REFERENCE_UNKNOWN'],'contains')],a=['A16'])
component('A17','Временной цикл не исправляется произвольной датой','ordering_goal constraint_search','time_constraints',{'edges':[['t1','BEFORE','t2'],['t2','BEFORE','t1']]},[check('/decision/outcome','UNRESOLVED'),check('/diagnostics/codes',['CONSTRAINT_CONFLICT'],'contains'),check('/time/invented_dates',[])],a=['A17'])
scenario('A18','Взаимный ASSERTED конфликт двух кандидатов','conflict_admission conflict_pairs full_reject',[
 step('reject','admit_batch',{'batch':'B','seq':1,'fragments':{'F1':P,'F2':g('NOT',P)}},facts([])+[check('/journal/batch_terminal',{'B':'REJECTED_CONFLICT_ADMISSION'}),check('/store/markers',[]),check('/store/commit_decisions',[]),check('/reports/evidence_kinds',[['CANDIDATE','CANDIDATE']]),check('/reports/open_count',1),check('/candidates/count',2)])],a=['A18'],dr=['DR13'])
component('A19','Непокрытая связь не уничтожает независимый фрагмент','partial coverage multi_anchor','formalize_partial',{'text':'Мария спит; Иван глоркнул как-то неизвестно.','resolved_fragments':[S],'unresolved_attachment':True},facts([S])+[check('/coverage/status','PARTIAL'),check('/coverage/opaque_full_claim',False)],a=['A19'])
component('A20','Нет R-V, R-S и open продолжаются','resource_missing source_trace source_blocked morph_unknown','candidate_sources',{'missing_entry':'R-V','other_candidates':{'2':['K'],'5':['OPEN']},'resource_present':True},[check('/source_traces/checked_sources',[1,2,3,4,5],'set_eq'),check('/diagnostics/codes',['VALENCY_UNKNOWN'],'contains'),check('/source_traces/source2/status','FOUND')],a=['A20'],dr=['DR6'])
component('A21','Known sense без TemplateMap — не open fallback','known_mapping registered_ops','consolidate',{'known_sense':'K_SEND','mapping':None,'open_candidate_available':True},facts([])+[check('/diagnostics/codes',['CANONICAL_MAPPING_MISSING'],'contains'),check('/plan/operations',[]),check('/store/open_template_count',0)],a=['A21'],dr=['DR6','DR24'],profile='known_mapping_broken')
scenario('A22','T6 повтор commit по hash','batch_idempotence commit_decision',[
 step('first','commit_batch',{'batch':'B','hash_alias':'H_B','formulas':[LOC]},facts([LOC])+[check('/supports/count',1),check('/journal/applied_count',1)]),
 step('repeat','commit_batch',{'batch':'B','hash_alias':'H_B','formulas':[LOC]},[same('/state/semantic_digest','first'),check('/journal/applied_count',1),check('/supports/count',1)])],a=['A22'])
scenario('A23','STATE две точки, единый N','state_identity no_interpolation time_absent',[
 step('seed','seed_state',{'node':'N','formula':LOC,'supports':['s1','s2'],'times':[point(9),point(14)]},[check('/store/atomic_node_count',1),check('/time_assertions/count',2)]),
 step('gap','query',{'formula':LOC,'point':11},[check('/answer/status','UNKNOWN')]),
 step('point','query',{'formula':LOC,'point':9},[check('/answer/status','YES')])],a=['A23'],dr=['DR7'])
component('A24','EVENT идентичное содержание не сливает occurrences','occurrence_identity','seed_occurrences',{'formula':P,'observations':['O1','O2'],'mode':'EVENT','times':[point(9),point(14)]},[check('/store/occurrence_count',2),check('/store/content_count',1),check('/store/event_identity_links',[])],a=['A24'])
component('A25','Observation identity без revision','observation_key revision','input_identity',{'records':[raw('Мария спит.','source'),dict(raw('Мария уснула.','source'),revision=2)],'force_equal_range':[0,12]},[check('/identity/same_observation',True),check('/identity/interpretation_versions',[1,2])],a=['A25'])
component('A26','Supersede v1 не отзывает v2','source_retraction revision declared_trigger','supersede_version',{'observation':'O','versions':[1,2],'supersede':1},[check('/supports/by_tag',{'O:v1':'SUPERSEDED','O:v2':'LIVE'})],a=['A26'])
component('A27','Declared perturbation пересчитывает, outcome может совпасть','declared_trigger contexts','change_declared_read',{'read':'context:1','new_version':2,'semantic_outcome_unchanged':True},[check('/execution/recomputed',True),check('/identity/interpretation_version',2),check('/decision/outcome','RESOLVED')],a=['A27'])
component('A28','Неполный search не AMBIGUOUS/RESOLVED','budget constraint_search states','solve_cluster',{'compatible_tuples':[['a'],['b']],'limit_branches':1,'timing_ticks':[0,1,2]},[check('/decision/outcome','COMPUTATION_LIMIT'),check('/decision/search_complete',False),check('/decision/machine_state','FROZEN')]+facts([]),a=['A28'])
component('A29','Редкое имя не исправляется в словарное','srl_boundary raw_alignment','lexical_candidates',{'text':'Ксавир приехал.','surface':'Ксавир','nearest_dictionary_form':'Ксавье','typo_ground':None},[check('/lexical/retained_surfaces',['Ксавир'],'contains'),check('/lexical/auto_replacements',[])],a=['A29'],profile='open')
component('A30','GoalCompiler не сканирует невозбуждённую память','workspace goal_compile query_readonly','compile_goal',{'text':'Кто пришёл?','activated_templates':['ARRIVE'],'unactivated_fact':pred('SLEEP',AGENT=IVAN)},[check('/goal/kind','RoleFillGoal'),check('/reads/global_scan_count',0),check('/goal/template_sources',['ARRIVE'],'set_eq')],a=['A30'])
lang('A31','Мне холодно.',[pred('OPEN:холодно',EXPERIENCER=ent('speaker'))],'structural_heads open_lexical attachment',a=['A31'],dr=['DR21'],profile='open',extra=[check('/coverage/status','OPEN_LEXICAL'),check('/open/semantic_status','UNLINKED'),check('/aliases',[])]+forbidden([pred('COLD_OBJECT',THEME=ent('speaker'))]),tags=['impersonal','unknown_lexical'])
component('A32','Control infinitive: ungrounded обе альтернативы','structural_heads alternatives value_grounds som','resolve_control',{'text':'Я попросил Машу передать книгу.','variants':['speaker','maria'],'value_grounds':{},'child_attitude':'EMBEDDED'},[check('/decision/outcome','UNRESOLVED'),check('/diagnostics/codes',['NO_GROUNDED_CANDIDATE'],'contains'),check('/alternatives/entities',['speaker','maria'],'set_eq')]+forbidden([pred('TRANSFER',AGENT=MARIA,THEME=BOOK)]),a=['A32'],dr=['DR22'])
lang('A33','Курьер переадресовал письмо.',[pred('OPEN:переадресовать',AGENT=ent('courier'),THEME=ent('letter'))],'open_lexical open_key known_mapping',a=['A33'],dr=['DR23'],profile='open',extra=[check('/coverage/status','OPEN_LEXICAL'),check('/aliases',[]),check('/decision/outcome','RESOLVED')]+forbidden([pred('SEND',AGENT=ent('courier'),THEME=ent('letter'))]))
component('A34','Known sense broken mapping сохраняет отказ','known_mapping','consolidate',{'known_sense':'K_SEND','mapping':None},facts([])+[check('/diagnostics/codes',['CANONICAL_MAPPING_MISSING'],'contains'),check('/store/open_template_count',0)],a=['A34'],dr=['DR24'],profile='known_mapping_broken')
lang('A35','Мария перестала курить.',[pred('STOP_LEXICAL',EXPERIENCER=MARIA,CONTENT=pred('SMOKE',AGENT=MARIA))],'multi_anchor som registered_ops modal_guard',a=['A35'],dr=['DR25'],extra=forbidden([pred('SMOKE',AGENT=MARIA),g('NOT',pred('SMOKE',AGENT=MARIA))])+[check('/store/unregistered_functions',[])])
component('A36','TemporalMode выбирается по frame','occurrence_identity state_identity coverage','frame_temporal_mode',{'text':'Книга лежала на столе. Иван лёг на стол.','frames':[{'sense':'LOCATIVE','mode_ground':'STATE'},{'sense':'LIE_DOWN','mode_ground':'TRANSITION'}]},[check('/frames/modes',['STATE','TRANSITION']),check('/frames/merged_across_modes',False)],a=['A36'],dr=['DR26'])
component('A37','Косвенный request не assertion действия','modus goal_compile','formalize_speech_act',{'raw_input':raw('Не мог бы ты открыть окно?',kind='MIXED'),'speech_act_ground':'REQUEST','action':pred('OPEN_WINDOW',AGENT=ent('addressee'))},facts([])+[check('/modus','COMMAND'),check('/goal/non_factive',True)],a=['A37'],dr=['DR27'])
for attitude in ['NOT','QUOTED']:
    content=pred('OPEN:переадресовать',AGENT=ent('courier'),THEME=ent('letter'))
    f=g('NOT',content) if attitude=='NOT' else pred('SAY',AGENT=IVAN,CONTENT=content)
    lang('A38-'+attitude,'Курьер не переадресовал письмо.' if attitude=='NOT' else 'Иван сказал: «Курьер переадресовал письмо».',[f],'open_lexical som attitude_links operator_links modal_guard',a=['A38'],dr=['DR31'],profile='open',extra=forbidden([content])+[check('/structural/formulas',[content],'contains'),check('/structural/entity_aliases',['courier','letter'],'contains')],tags=['scope','unknown_lexical'])
component('A39','Пять пустых terminal sources','source_trace source_exhaustion','candidate_sources',{'sources':{str(i):'CHECKED_EMPTY' for i in range(1,6)},'candidates':[]},[check('/decision/outcome','NO_CANDIDATE'),check('/diagnostics/codes',['CANDIDATE_SOURCE_EXHAUSTED'],'contains'),check('/source_traces/count',5),check('/audit/frame_retained',True)]+facts([]),a=['A39'],dr=['DR6'])

# Independent mathematical gold for finite closed interval vectors, not SUT evaluation.
# ticks are fixture-relative rationals; source timestamp/timezone are fixed in fixtures.json.
W=[None,point(0),point(1),point(3),interval(0,1,'CONTINUOUS'),interval(1,3,'CONTINUOUS'),interval(0,3,'CONTINUOUS'),interval(4,6,'CONTINUOUS'),interval(1,1,'CONTINUOUS'),interval(0,1),interval(1,3),interval(0,3),interval(4,6),interval(1,1),{'kind':'INTERVAL','bounds':['symbolic:start',3],'semantics':'EXISTENTIAL'}]

def norm(w):
    if w is None:return None
    if w['kind']=='POINT':return ('P',w['t'],w['t'])
    a,b=w['bounds']
    if not isinstance(a,(int,float)) or not isinstance(b,(int,float)):return ('U',a,b)
    if a==b:return ('P',a,a)
    return ('C' if w['semantics']=='CONTINUOUS' else 'E',a,b)

def simultaneous(a,b):
    a,b=norm(a),norm(b)
    if a is None or b is None: return False
    if 'U' in (a[0],b[0]):return False
    if a[0]=='P' and b[0]=='P': return a[1]==b[1]
    if a[0]=='C' and b[0]=='C': return max(a[1],b[1])<=min(a[2],b[2])
    if b[0]=='C':a,b=b,a
    if a[0]=='C':return a[1]<=b[1] and b[2]<=a[2]
    return False

def or_license(root,neg):
    a,b=norm(root),norm(neg)
    if a is None or b is None: return (a is None and b is None)
    if 'U' in (a[0],b[0]):return False
    if b[0]=='P':return a[0]=='P' and a[1]==b[1]
    if b[0]=='C':return b[1]<=a[1] and a[2]<=b[2]
    return False

def forall_license(a,b):
    na,nb=norm(a),norm(b)
    if na is None or nb is None:return (na is None and nb is None),None
    if 'U' in (na[0],nb[0]):return False,None
    if not simultaneous(a,b):return False,None
    if a['kind']==b['kind']=='INTERVAL' and a['semantics']==b['semantics']=='CONTINUOUS':
        return True,interval(max(na[1],nb[1]),min(na[2],nb[2]),'CONTINUOUS')
    if na[0]=='P':return True,point(na[1])
    if nb[0]=='P':return True,point(nb[1])
    if na[0]==nb[0]=='C':return True,interval(max(na[1],nb[1]),min(na[2],nb[2]),'CONTINUOUS')
    if na[0]=='E':return True,copy.deepcopy(a)
    if nb[0]=='E':return True,copy.deepcopy(b)
    return False,None

def time_answer(w,q,negative=False):
    n=norm(w)
    if q['kind']=='PROPOSITIONAL':return 'NO' if negative else 'YES'
    if n is None or n[0]=='U':return 'UNKNOWN'
    if q['kind']=='POINT':ok=n[1]==q['t'] if n[0]=='P' else n[0]=='C' and n[1]<=q['t']<=n[2]
    else:
        a,b=q['bounds']
        if negative: ok=n[0]=='C' and n[1]<=a and b<=n[2] or n[0]=='P' and a==b==n[1]
        elif n[0]=='P':ok=a<=n[1]<=b
        elif n[0]=='C':ok=max(a,n[1])<=min(b,n[2])
        else:ok=a<=n[1] and n[2]<=b
    return ('NO' if negative else 'YES') if ok else 'UNKNOWN'

for i,a in enumerate(W):
    for j,b in enumerate(W):
        if a is not None and b is not None:
            ok=simultaneous(a,b)
            checks=[check('/time/guaranteed_simultaneity',ok),check('/reports/open_count',1 if ok else 0)]
            if any(norm(x)[0]=='U' for x in (a,b)):checks+=[check('/diagnostics/codes',['INTERVAL_BOUNDARY_UNKNOWN'],'contains')]
            component(f'SIM-{i:02}-{j:02}','Гарантированная одновременность независимых witnesses','simultaneity conflict_admission', 'check_simultaneity',{'witness_a':a,'witness_b':b,'incompatibility_rule':'LOCATIVE_EXCLUSIVE','independent':True},checks,a=['A18'],dr=['DR8','DR12'])
        ok=or_license(a,b)
        cs=[check('/license/valid',ok),check('/derived/support_count',1 if ok else 0),check('/derived/time',copy.deepcopy(a) if ok else None)]
        if not ok: cs += [check('/answer/status','UNKNOWN'),check('/diagnostics/codes',['OR_ELIMINATION_TEMPORAL_MISMATCH'],'contains'),check('/journal/goal_pending_count',0)]
        component(f'ORT-{i:02}-{j:02}','OR temporal root/NOT coverage','or_time time_symbolic goal_license_race','derive_or',{'or_formula':g('OR',P,Q),'not_formula':g('NOT',Q),'root_witness':a,'not_witness':b,'invoke':'ON_DEMAND','independent':True},cs,dr=['DR16','DR19','DR29'])
        ok,region=forall_license(a,b)
        cs=[check('/license/valid',ok),check('/derived/support_count',1 if ok else 0),check('/derived/time',region)]
        if not ok:cs += [check('/answer/status','UNKNOWN'),check('/diagnostics/codes',['FORALL_INST_TEMPORAL_MISMATCH'],'contains'),check('/journal/goal_pending_count',0)]
        component(f'FAT-{i:02}-{j:02}','FORALL symmetric temporal license','forall_time time_symbolic goal_license_race','derive_forall',{'quantified_root':ALL,'restriction':pred('STUDENT',THEME=IVAN),'root_witness':a,'restriction_witness':b,'independent':True},cs,dr=['DR28'])

QUERIES=[{'kind':'PROPOSITIONAL'}]+[{'kind':'POINT','t':t} for t in (-1,0,1,2,3,4,6,7)]+[{'kind':'EXISTS','bounds':[a,b]} for a,b in [(-1,7),(0,0),(0,1),(1,2),(1,3),(2,3),(4,6),(3,4)]]
for i,w in enumerate(W):
    for j,q in enumerate(QUERIES):
        for negative in (False,True):
            component(f'TQ-{i:02}-{j:02}-{int(negative)}','Временной запрос к единственному доказанному пути','query_time query_not_time time_absent time_symbolic', 'query_time',{'formula':g('NOT',P) if negative else LOC,'witness':w,'query':q},[check('/answer/status',time_answer(w,q,negative)),check('/query/new_root_supports',0)],dr=['DR7','DR16'])

# On-demand n-ary OR: exhaust every subset of negatives for n=2..6.
for n in range(2,7):
    atoms=[pred('ARRIVE',AGENT=ent(f'person_{k}')) for k in range(n)]
    for mask in range(1<<(n-1)):
        negs=[g('NOT',atoms[k]) for k in range(1,n) if mask & (1<<(k-1))]
        ok=len(negs)==n-1
        component(f'OR-N{n}-{mask:02x}','Все n−1 отрицаний, ни одной выбранной ветви при недостатке','or_demand modal_guard support_paths', 'nary_or_query',{'root':g('OR',*atoms),'not_roots':negs,'target':atoms[0]},[check('/answer/status','YES' if ok else 'UNKNOWN'),check('/derived/premise_count',n if ok else 0),check('/derived/support_count',1 if ok else 0),check('/commit/instances_before_goal',0)]+([] if ok else [check('/diagnostics/codes',['OR_ELIMINATION_INCOMPLETE'],'contains')]),dr=['DR10'])

# Correlation is a proof relation, not equality of intervals or observation tags.
for rule in ('OR_ELIMINATION','FORALL_INST'):
    for shared in (False,True):
        for same_tag in (False,True):
            component(f'WIT-{rule}-{int(shared)}-{int(same_tag)}','Общий witness vs равные bounds','witness_correlation or_time forall_time time_provenance','correlated_inference',{'rule':rule,'witnesses':[interval(0,3),interval(0,3)],'same_source_tag':same_tag,'shared_witness_ref':'W_AND' if shared else None,'shared_witness_proof':{'root_support':'S_AND','assertion_refs':['A1','A2']} if shared else None},[check('/license/valid',shared),check('/derived/support_count',int(shared)),check('/derived/witness_ref','W_AND' if shared else None),check('/derived/is_continuous',False)],dr=['DR11','DR12'])
component('WIT-NO-REGION','Registered >2-premise rule без объявленного result-region','multi_premise_time','multi_premise_inference',{'rule':'REGISTERED_TEST_RULE','premises':[interval(0,3,'CONTINUOUS')]*3,'declared_result_region':None},[check('/answer/status','UNKNOWN'),check('/diagnostics/codes',['INFERENCE_TEMPORAL_MISMATCH'],'contains'),check('/derived/support_count',0)])

# Source truth/interpretation matrix: all singleton and two-ground combinations.
for n in (1,2):
    for gs in itertools.combinations(['O','C','W','R','D','M','A','P'],n):
        truth=sorted(set(gs)&{'O','C','W'})
        component('GRD-'+'-'.join(gs),'Основания не смешиваются при materialization','grounds writers','commit_grounded_fragment',{'formula':S,'selected_value_ground_types':list(gs),'otherwise_integrity_valid':True},[check('/supports/root_ground_types',truth,'set_eq'),check('/commit/materialized',bool(truth)),check('/store/fact_count',int(bool(truth)))],a=['A09'])

# T4 exact decision table and exhaustion vs BLOCKED; source traces are never inferred from an empty candidate list.
for nt in range(4):
 for grounded in (False,True):
  for blocked in (False,True):
   for complete in (False,True):
    outcome='COMPUTATION_LIMIT' if not complete else 'UNRESOLVED' if blocked or nt and not grounded else 'NO_CANDIDATE' if nt==0 else 'RESOLVED' if nt==1 else 'AMBIGUOUS'
    component(f'T4-{nt}-{int(grounded)}-{int(blocked)}-{int(complete)}','Полная таблица решения T4','value_grounds constraint_search source_exhaustion source_blocked states','resolve_tuples',{'surviving_tuple_count':nt,'each_value_has_positive_ground':grounded,'source_complete':not blocked,'search_complete':complete,'source_statuses':['CHECKED_EMPTY']*5 if not nt and not blocked else ['FOUND','BLOCKED' if blocked else 'CHECKED_EMPTY','CHECKED_EMPTY','CHECKED_EMPTY','CHECKED_EMPTY']},[check('/decision/outcome',outcome),check('/decision/materializable',outcome=='RESOLVED'),check('/decision/source_complete',not blocked),check('/decision/search_complete',complete)])
for source in range(1,6):
    component(f'SRC-MISSING-{source}','Missing trace is integrity error, not exhaustion','source_trace','candidate_sources',{'omitted_trace_source':source},[check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains'),check('/decision/materializable',False)]+facts([]),a=['A39'])
    for blocker in ['RESOURCE_MISSING','PROVIDER_UNAVAILABLE','PROTOCOL_ERROR','COMPUTATION_LIMIT']:
        component(f'SRC-BLOCK-{source}-{blocker}','Один BLOCKED источник не считается пустым','source_blocked source_exhaustion','candidate_sources',{'sources':{str(i):('BLOCKED' if i==source else 'CHECKED_EMPTY') for i in range(1,6)},'reason':blocker,'candidate_from_other_source':'K'},[check('/decision/outcome','COMPUTATION_LIMIT' if blocker=='COMPUTATION_LIMIT' else 'UNRESOLVED'),check('/diagnostics/codes',[blocker],'contains'),check('/diagnostics/codes',['CANDIDATE_SOURCE_EXHAUSTED'],'excludes'),check('/commit/materialized',False)],a=['A39'])

# Diversity comes from grammatical structure/roles/scope, not just replacing a person's name.
# Every pattern is paired with another construction or polarity. Fixtures pin the chosen sense and roles.
PEOPLE=[('Иван','ivan'),('Пётр','petr'),('Сергей','sergey'),('Алексей','alexey')]
PATTERNS=[
 ('{n} вошёл.',lambda e:pred('ENTER',AGENT=e),'finite'),
 ('Вошёл {n}.',lambda e:pred('ENTER',AGENT=e),'word_order'),
 ('{n} читает книгу.',lambda e:pred('READ',AGENT=e,THEME=BOOK),'transitive'),
 ('Книгу читает {n}.',lambda e:pred('READ',AGENT=e,THEME=BOOK),'word_order'),
 ('{n} передал книгу Марии.',lambda e:pred('TRANSFER',AGENT=e,THEME=BOOK,RECIPIENT=MARIA),'ditransitive'),
 ('Марии {n} передал книгу.',lambda e:pred('TRANSFER',AGENT=e,THEME=BOOK,RECIPIENT=MARIA),'word_order'),
 ('{n} — врач.',lambda e:pred('DOCTOR',THEME=e),'nominal'),
 ('{n} устал.',lambda e:pred('TIRED',EXPERIENCER=e),'state'),
 ('{n} сидит на стуле.',lambda e:pred('SIT_STATE',THEME=e,LOCATION=ent('chair')),'state'),
 ('{n} работает.',lambda e:pred('WORK',AGENT=e),'process'),
 ('{n} открыл окно.',lambda e:pred('OPEN',AGENT=e,THEME=ent('window')),'transition'),
 ('{n} позвонил Марии.',lambda e:pred('CALL',AGENT=e,RECIPIENT=MARIA),'roles'),
 ('{n} написал письмо.',lambda e:pred('WRITE',AGENT=e,THEME=ent('letter')),'finite'),
 ('{n} встретил курьера.',lambda e:pred('MEET',AGENT=e,THEME=ent('courier')),'roles'),
 ('{n} приехал в Москву.',lambda e:pred('ARRIVE_CITY',AGENT=e,DESTINATION=ent('moscow')),'preposition'),
 ('{n} уехал из Москвы.',lambda e:pred('DEPART_CITY',AGENT=e,SOURCE=ent('moscow')),'preposition'),
]
for i,(pat,fun,tag) in enumerate(PATTERNS):
 for j,(name,alias) in enumerate(PEOPLE):
    atom=fun(ent(alias));text=pat.format(n=name)
    for mode in ['bare','not','possible','quoted','before_point','yesterday','continuous','question']:
        if mode=='bare':txt=text; fs=[atom];extras=[]
        elif mode=='not':
            # Fixture specifies scoped NOT, so model does not choose negation attachment arbitrarily.
            txt='Неверно, что '+text[0].lower()+text[1:];fs=[g('NOT',atom)];extras=forbidden([atom])
        elif mode=='possible':txt='Возможно, '+text[0].lower()+text[1:];fs=[g('POSSIBLE',atom)];extras=forbidden([atom])
        elif mode=='quoted':txt='Мария сказала: «'+text[:-1]+'».';fs=[pred('SAY',AGENT=MARIA,CONTENT=atom)];extras=forbidden([atom])
        elif mode=='before_point':txt='В 09:00 '+text[0].lower()+text[1:];fs=[atom];extras=[check('/time_assertions/semantics',['POINT'],'multiset_eq')]
        elif mode=='yesterday':txt='Вчера '+text[0].lower()+text[1:];fs=[atom];extras=[check('/time_assertions/semantics',['EXISTENTIAL'],'multiset_eq')]
        elif mode=='continuous':txt='Весь вчерашний день '+text[0].lower()+text[1:];fs=[atom];extras=[check('/time_assertions/semantics',['CONTINUOUS'],'multiset_eq')]
        else:txt='Верно ли, что '+text[0].lower()+text[1:-1]+'?';fs=[];extras=[check('/modus','QUERY')]
        lang(f'LANG-{i:02}-{j}-{mode}',txt,fs,'structural_heads raw_alignment modus modal_guard time_default query_readonly',extra=extras,tags=[tag,mode],kind='QUERY' if mode=='question' else 'ASSERTION',gold=[atom])

# Nonfinite/impersonal/ellipsis patterns with unasserted child content.
NF=[
 ('Иван хочет читать книгу.',pred('WANT',EXPERIENCER=IVAN,CONTENT=pred('READ',AGENT=IVAN,THEME=BOOK)),pred('READ',AGENT=IVAN,THEME=BOOK)),
 ('Иван решил открыть окно.',pred('DECIDE',AGENT=IVAN,CONTENT=pred('OPEN',AGENT=IVAN,THEME=ent('window'))),pred('OPEN',AGENT=IVAN,THEME=ent('window'))),
 ('Пётр намерен уехать.',pred('INTEND',AGENT=PETR,CONTENT=pred('DEPART',AGENT=PETR)),pred('DEPART',AGENT=PETR)),
 ('Мария просит Ивана принести книгу.',pred('REQUEST',AGENT=MARIA,ADDRESSEE=IVAN,CONTENT=pred('BRING',AGENT=IVAN,THEME=BOOK)),pred('BRING',AGENT=IVAN,THEME=BOOK)),
 ('Мне хочется спать.',pred('DESIRE',EXPERIENCER=ent('speaker'),CONTENT=pred('SLEEP',AGENT=ent('speaker'))),pred('SLEEP',AGENT=ent('speaker'))),
 ('Иван надеется вернуться.',pred('HOPE',EXPERIENCER=IVAN,CONTENT=pred('RETURN',AGENT=IVAN)),pred('RETURN',AGENT=IVAN)),
 ('Книгу можно прочитать.',pred('PERMITTED_LEXICAL',CONTENT=pred('READ',THEME=BOOK)),pred('READ',THEME=BOOK)),
 ('Нужно открыть окно.',pred('NEED_LEXICAL',CONTENT=pred('OPEN',THEME=ent('window'))),pred('OPEN',THEME=ent('window'))),
]
for i,(text,parent,child) in enumerate(NF):
 for variant in ['base','quote','nested_quote','question']:
    fs=[parent] if variant=='base' else [pred('SAY',AGENT=PETR,CONTENT=parent)] if variant=='quote' else [pred('SAY',AGENT=IVAN,CONTENT=pred('THINK',EXPERIENCER=PETR,CONTENT=parent))] if variant=='nested_quote' else []
    txt=text if variant=='base' else 'Пётр сказал: «'+text[:-1]+'».' if variant=='quote' else 'Иван сказал, что Пётр думает: «'+text[:-1]+'».' if variant=='nested_quote' else 'Верно ли, что '+text[0].lower()+text[1:-1]+'?'
    lang(f'NONFINITE-{i:02}-{variant}',txt,fs,'structural_heads som s_access modal_guard attitude_links',extra=forbidden([child]),tags=['nonfinite',variant],kind='QUERY' if variant=='question' else 'ASSERTION',gold=[parent,child])

# Linguistic mutation cases keep the gold relation, but roles and reference proof are explicit.
for n,(surface,lemma) in enumerate([('глоркнул','глоркнуть'),('зумбировал','зумбировать'),('флукнул','флукнуть'),('квелировал','квелировать'),('бронкнул','бронкнуть'),('шарпировал','шарпировать'),('переадресовал','переадресовать'),('траверсировал','траверсировать')]):
 for j,(name,alias) in enumerate(PEOPLE):
  atom=pred('OPEN:'+lemma,AGENT=ent(alias),THEME=BOOK)
  for mode in ['asserted','not','quoted','or']:
    text=f'{name} {surface} книгу.'
    fs=[atom]
    if mode=='not':text=f'{name} не {surface} книгу.';fs=[g('NOT',atom)]
    if mode=='quoted':text='Мария сказала: «'+text[:-1]+'».';fs=[pred('SAY',AGENT=MARIA,CONTENT=atom)]
    if mode=='or':text=text[:-1]+' или Мария уснула.';fs=[g('OR',atom,S)]
    lang(f'OPEN-{n:02}-{j}-{mode}',text,fs,'open_lexical multi_anchor som modal_guard open_key',profile='open',tags=['unknown_lexical',mode],extra=[check('/aliases',[]),check('/open/capabilities',['EXACT_ATTESTATION'],'set_eq')]+(forbidden([atom]) if mode!='asserted' else []),gold=[atom])

# Retraction variants with precise, separately checked status and effective visibility.
for source in ['OBSERVATION_ROOT','OBSERVATION_AND_DERIVED','GOAL_RUN_DERIVED']:
 for how in ['OBSERVATION','ASSERTION','BINDING','PREMISE']:
    retracted=how=='ASSERTION' or how=='OBSERVATION' and source.startswith('OBSERVATION')
    component(f'RET-{source}-{how}','Status TimeAssertion и эффективная живость — разные оси','time_provenance assertion_retraction effective_time source_retraction binding_paths','retract_time_path',{'assertion_id':'A','source_support_variant':source,'trigger_scope':how,'another_live_path':False},[check('/time_assertions/A/status','RETRACTED' if retracted else 'LIVE'),check('/time_assertions/A/effective',False),check('/journal/time_retraction_count',int(retracted)),check('/supports/original_alive',how=='ASSERTION')],dr=['DR8','DR12','DR28','DR30'])
for variant in ['same_support_different_assertions','different_supports_same_node']:
 scenario('RET-INDEPENDENT-'+variant,'Отзыв только выбранного свидетельства не спасается другой датировкой','assertion_retraction effective_time support_paths goal_dedup',[
  step('seed','seed_derived_paths',{'variant':variant,'node':'N','paths':{'SD15':{'temporal_refs':['A_or15','A_not15']},'SD16':{'temporal_refs':['A_or16','A_not16']}}},[check('/nodes/N/f_visible',True)]),
  step('retract','retract_assertion',{'assertion_id':'A_or15'},[check('/supports/SD15/effective',False),check('/supports/SD16/effective',True),check('/nodes/N/f_visible',True),check('/time_assertions/A_or15/status','RETRACTED'),check('/supports/S_or/status','LIVE')]),
  step('again','retract_assertion',{'assertion_id':'A_or15'},[same('/state/semantic_digest','retract'),check('/journal/time_retraction_count',1)])],dr=['DR29'])

# SOM closed from an empty store, shared parent links, recursion, and recovery.
for depth in range(1,6):
    inner=P
    for k in range(depth):inner=g('POSSIBLE' if k%2 else 'NOT',inner)
    scenario(f'SOM-DEPTH-{depth}','Транзитивная доступность до asserted предка','som operator_links s_access reaccess node_events',[
     step('commit','commit_som',{'root':inner,'leaf':P,'mode':'STATE','source':'O1'},[check('/som/chain_s_access',[True]*(depth+1)),check('/som/chain_f_visible',[True]+[False]*depth),check('/supports/root_count',1)]),
     step('withdraw','retract_observation',{'observation':'O1'},[check('/som/chain_s_access',[False]*(depth+1)),check('/usage/operator_statuses',['LIVE']*depth)]),
     step('return','commit_som',{'root':inner,'leaf':P,'mode':'STATE','source':'O2'},[check('/som/chain_s_access',[True]*(depth+1)),check('/store/new_content_nodes',0),check('/supports/old_status','SUPERSEDED'),check('/events/reaccessible_count',depth+1)])],dr=['DR31'])
for mode in ['STATE','EVENT','PROCESS','TRANSITION','UNKNOWN']:
 scenario('SOM-INDEPENDENT-'+mode,'Позднее asserted содержание: mode-correct identity','som attitude_links state_identity occurrence_identity',[
  step('quote','commit_som',{'root':pred('SAY',AGENT=IVAN,CONTENT=LOC),'leaf':LOC,'mode':mode,'source':'O1'},[check('/som/leaf_f_visible',False),check('/som/leaf_s_accessible',True)]),
  step('assert','assert_content',{'content':LOC,'mode':mode,'source':'O2'},[check('/store/asserted_shares_structural_node',mode=='STATE'),check('/store/occurrence_count',2 if mode!='STATE' else 1)]),
  step('withdraw_parent','retract_observation',{'observation':'O1'},[check('/asserted_content/f_visible',True),check('/usage/attitude_status','SUPERSEDED')]),
  step('withdraw_child','retract_observation',{'observation':'O2'},[check('/asserted_content/f_visible',False)])],dr=['DR4','DR25'])
scenario('SOM-TWO-HOLDERS','Два родителя одного структурного содержания','attitude_links som s_access',[
 step('two','commit_two_attitudes',{'content':LOC,'sources':['O1','O2'],'holders':['ivan','petr'],'attitudes':['QUOTED','EMBEDDED']},[check('/store/content_count',1),check('/usage/attitude_count',2),check('/som/leaf_f_visible',False)]),
 step('one','retract_observation',{'observation':'O1'},[check('/som/leaf_s_accessible',True),check('/usage/live_attitude_count',1)]),
 step('none','retract_observation',{'observation':'O2'},[check('/som/leaf_s_accessible',False)])],dr=['DR4'])
component('SOM-CYCLE','Цикл без F-visible предка не самоподдерживается','s_access','compute_s_access',{'node_links':[['A','B'],['B','A']],'f_visible_roots':[]},[check('/som/accessible_nodes',[])])
component('LINK-OP-RETRACT','Прямой отзыв канонического OPERATOR запрещён','operator_links','retract_usage_link',{'kind':'OPERATOR','link_id':'L'},[check('/diagnostics/codes',['RETRACT_OPERATOR_LINK_FORBIDDEN'],'contains'),check('/usage/L/status','LIVE')])
for op,nprops,nliterals in [('FORALL',1,1),('EXISTS',1,1),('AT_LEAST_N',1,2),('BEFORE_TIME',0,2),('BEFORE_PROPS',2,0),('NOT',1,0),('POSSIBLE',1,0),('COUNTERFACTUAL',2,0)]:
 component('LINK-SLOTS-'+op,'SOM-link лишь для Ref(N|G), literals/bound_var внутри G','operator_links registered_ops numeric_scope','materialize_function_slots',{'operator':op,'proposition_slots':nprops,'non_proposition_slots':nliterals},[check('/usage/operator_count',nprops),check('/usage/links_to_non_propositions',0)])

# Function identity / lexical isolation / temporal frame mode.
for op in ['AND','OR','XOR','NOT','IMPLIES','FORALL','EXISTS','POSSIBLE','NECESSARY','COUNTERFACTUAL','BEFORE','AFTER','DURING','ASSOCIATION','EXACTLY_N','AT_LEAST_N','AT_MOST_N']:
  if op in ['NOT','POSSIBLE','NECESSARY']:args=[P]
  elif op in ['FORALL','EXISTS']:args=[var('x'),BODY]
  elif op in ['EXACTLY_N','AT_LEAST_N','AT_MOST_N']:args=[var('x'),pred('STUDENT',THEME=var('x')),{'count_literal':2}]
  elif op in ['BEFORE','AFTER','DURING']:args=[{'time_literal':0},{'time_literal':3}]
  else:args=[P,Q]
  is_comm=op in ['AND','OR','XOR']
  reverse_valid=op not in ['FORALL','EXISTS','EXACTLY_N','AT_LEAST_N','AT_MOST_N']
  component('FUNC-'+op,'Typed key и синтаксический порядок оператора','function_identity registered_ops', 'function_identity',{'operator':op,'operands':args,'compare_operands':list(reversed(args))},[check('/functions/second_well_typed',reverse_valid),check('/functions/same_key',is_comm or len(args)==1),check('/functions/syntax_order_preserved',True)],dr=['DR17'])
for change in ['context_version','observation_id','source_revision','role','attachment','sense_conflict']:
    stable=change=='context_version'
    component('OPEN-KEY-'+change,'Ключ open T не identity по слову','open_key open_lexical alternatives','open_template_keys',{'base':{'observation':'O1','revision':1,'surface':'глоркнул','role':'AGENT','attachment':'nsubj'},'changed_dimension':change},[check('/open/key_equal',stable),check('/open/alias_created',False),check('/open/materialized',change!='sense_conflict')],dr=['DR23'])
for mode in ['STATE','EVENT','PROCESS','TRANSITION','UNKNOWN']:
    component('FRAME-'+mode,'Mode принадлежит frame, слияние только STATE','state_identity occurrence_identity','seed_occurrences',{'formula':LOC,'mode':mode,'observations':['O1','O2'],'times':[point(0),point(3)]},[check('/store/atomic_node_count',1 if mode=='STATE' else 2),check('/time/interpolated',False)],dr=['DR26'])

# Goal transaction four-part key, event occurrence identity and races.
for mode in ['STATE','EVENT','PROCESS','TRANSITION','UNKNOWN']:
 for keychange in ['none','request_window','temporal_assertion','support','rule','conclusion']:
    new=keychange not in ['none','request_window']
    component('DEDUP-'+mode+'-'+keychange,'Ключ пути не совпадает с ключом узла','goal_dedup goal_decision occurrence_identity state_identity','repeat_goal',{'mode':mode,'existing_goal_path':{'rule_id':'OR_ELIMINATION','premise_support_refs':['S1','S2'],'conclusion_signature':'SIG_P','temporal_premise_assertion_refs':['A1','A2']},'change':keychange,'premises_live':True,'license_valid':True},[check('/goal/outcome','APPLIED' if new else 'APPLIED_NOOP'),check('/goal/created_path',new),check('/store/new_occurrence_count',int(new and mode!='STATE')),check('/time_assertions/new_count',int(new)),check('/derived/target_matches_mode',True),check('/derived/time_target_matches_support',True),check('/derived/formula_ref_matches_content',True)],dr=['DR18','DR29','DR30'])
for committed_outcome in [None,'APPLIED','APPLIED_NOOP','ABORTED']:
 for has_path in [False,True]:
  for live in [False,True]:
   for license_valid in [False,True]:
    if committed_outcome in ['APPLIED','APPLIED_NOOP'] and not has_path: continue  # Impossible ordinary-crash state: rows persist in audit.
    out=committed_outcome or ('ABORTED' if not live or not license_valid else 'APPLIED_NOOP' if has_path else 'APPLIED')
    reason=None if out!='ABORTED' else 'GOAL_PREMISES_STALE' if committed_outcome else 'GOAL_PREMISES_STALE' if not live else 'GOAL_LICENSE_FAILED'
    component(f'GREC-{committed_outcome or "NONE"}-{int(has_path)}-{int(live)}-{int(license_valid)}','Полная decision-first R0/R1/R2 таблица','goal_recovery goal_decision goal_dbn goal_license_race','recover_goal',{'stored_decision':None if committed_outcome is None else {'outcome':committed_outcome,'reason':'GOAL_PREMISES_STALE' if committed_outcome=='ABORTED' else None},'dedup_path_exists':has_path,'premises_live':live,'license_valid':license_valid,'pending_durable':True},[check('/goal/outcome',out),check('/goal/reason',reason),check('/goal/new_derived_support_count',int(committed_outcome is None and out=='APPLIED')),check('/journal/goal_decision_count',1),check('/journal/goal_terminal_count',1)],dr=['DR19','DR20','DR30'])
for order in ['RETRACTION_FIRST','DECISION_FIRST']:
 for death in ['SUPPORT','ASSERTION']:
    out='APPLIED_NOOP' if order=='DECISION_FIRST' else 'ABORTED'
    reason=None if out=='APPLIED_NOOP' else 'GOAL_PREMISES_STALE' if death=='SUPPORT' else 'GOAL_LICENSE_FAILED'
    scenario('DBN-'+order+'-'+death,'NOOP/ABORTED reading и fsync в единой границе с отзывом','goal_dbn goal_recovery goal_license_race',[
     step('seed','seed_goal_path',{'supports':['S1','S2'],'assertions':['A1','A2'],'mode':'STATE'},[check('/nodes/N/f_visible',True)]),
     step('race','interleave_dbn_retraction',{'durable_order':order,'retract_kind':death,'crash_after_decision':True},[check('/goal/decision_outcome',out),check('/goal/decision_reason',reason),check('/goal/new_derived_support_count',0)]),
     step('recover','recover',{},[check('/goal/outcome',out),check('/nodes/N/f_visible',False),check('/time_assertions/A_D/status','LIVE'),check('/time_assertions/A_D/effective',False),check('/journal/goal_terminal_count',1)])],dr=['DR20','DR30'])

# Conflict branch pairs and granularity; candidate evidence remains non-factive after winner dies.
for k in [1,2,3]:
 scenario(f'REPORT-PAIRS-{k}','Отчёт для каждого независимого conflicting evidence','conflict_pairs conflict_open conflict_admission',[
 step('reject','reject_against_evidences',{'candidate':'OR_F','formula':P,'committed_evidences':[f'A{i}' for i in range(k)],'not_formula':g('NOT',P),'window':interval(0,3,'CONTINUOUS')},[check('/reports/open_count',k),check('/candidates/count',1),check('/store/candidate_asserted',False)]),
 *[step(f'retract{i}','retract_assertion',{'assertion_id':f'A{i}'},[check('/reports/open_count',k-i-1),check('/journal/report_closed_count',i+1),check('/store/candidate_asserted',False)]) for i in range(k)],
 step('query','query',{'formula':P,'window':[0,3]},[check('/answer/status','UNKNOWN'),check('/answer/conflict_refs',[])])],dr=['DR17'])
for partial_commit in (False,True):
 for crash in ['BEFORE_DECISION','AFTER_DECISION','AFTER_TERMINAL']:
    scenario('REPORT-TWO-'+str(int(partial_commit))+'-'+crash,'Два кандидата+отчёт атомарны с терминальным исходом','conflict_pairs commit_decision full_reject batch_recovery fragment_plan',[
     step('plan','journal_batch',{'batch':'B','seq':1,'fragments':{'F_P':P,'F_NOT':g('NOT',P),**({'F_Q':S} if partial_commit else {})}},[check('/reports/count',0)]),
     step('crash','admit_with_crash',{'batch':'B','stop':crash},[]),
     step('recover','recover',{},facts([S] if partial_commit else [])+[check('/journal/batch_terminal',{'B':'APPLIED' if partial_commit else 'REJECTED_CONFLICT_ADMISSION'}),check('/candidates/count',2),check('/reports/evidence_kinds',[['CANDIDATE','CANDIDATE']]),check('/reports/open_count',1),check('/store/commit_decision_count',int(partial_commit)),check('/store/marker_count',int(partial_commit)),check('/journal/terminal_report_atomic',True)]),
     step('again','recover',{},[same('/state/semantic_digest','recover')])],dr=['DR13'])
scenario('PRECHECK-RETRACT','Предпроверка конфликта, отзыв X до admission','precheck conflict_admission commit_decision',[
 step('gate','gate_precheck',{'fragment':P,'against':g('NOT',P),'source':'OX'},[check('/journal/precheck_count',1),check('/reports/count',0),check('/precheck/terminal',False),check('/plan/excluded',[])]),
 step('retract','retract_observation',{'observation':'OX'},[check('/reports/count',0)]),
 step('admit','commit_batch',{'batch':'B','formulas':[P]},facts([P])+[check('/reports/count',0),check('/journal/applied_precheck_refs',['PRECHECK_1']),check('/precheck/immutable',True)])],dr=['DR14'])
scenario('LATE-CONFLICT','Новый incompatibility rule после обоих коммитов','conflict_late conflict_open source_retraction',[
 step('seed','seed_without_incompatibility',{'formulas':[LOC,LOC2],'windows':[interval(0,3,'CONTINUOUS'),interval(0,3)]},[check('/store/fact_count',2),check('/reports/count',0)]),
 step('release','change_declared_resource',{'rule':'LOCATIVE_EXCLUSIVE','version':2},[check('/reports/open_count',1),check('/store/fact_count',2),check('/store/auto_retraction_count',0)]),
 step('point','query',{'formula':LOC2,'point':1},[check('/answer/status','UNKNOWN'),check('/answer/conflict_count',1)]),
 step('exists','query',{'formula':LOC2,'window':[0,3]},[check('/answer/status','YES'),check('/answer/conflict_count',1)])])

# Head-only admission order permutations and failure positions.
for order in itertools.permutations([1,2,3]):
 for crash in ['NONE','BEFORE_T6','AFTER_FIRST_COMMIT','AFTER_MARKER_BEFORE_APPLIED']:
    scenario('HEAD-'+'-'.join(map(str,order))+'-'+crash,'Global seq, не порядок вызовов T6','head_order full_reject batch_recovery conflict_admission',[
      step('journal','journal_batches',{'batches':[{'seq':1,'batch':'B1','fragments':[P,g('NOT',P)]},{'seq':2,'batch':'B2','fragments':[P]},{'seq':3,'batch':'B3','fragments':[S]}]},[check('/store/marker_count',0)]),
      step('execution','execute_head_calls',{'call_order':list(order),'crash_at':crash},[]),
      step('drain','recover',{},facts([P,S])+[check('/journal/batch_terminal',{'B1':'REJECTED_CONFLICT_ADMISSION','B2':'APPLIED','B3':'APPLIED'}),check('/store/markers',['B2','B3'],'set_eq'),check('/reports/open_count',1),check('/journal/pending_admission_order_records',0)]),
      step('repeat','recover',{},[same('/state/semantic_digest','drain')])],dr=['DR13'])
scenario('STALE-HEAD','Stale head терминален; чужая пара продолжает','stale_plan head_order batch_recovery',[
 step('journal','journal_batches',{'batches':[{'seq':1,'batch':'B1','pair':'O1:v1','stale':True,'fragments':[P]},{'seq':2,'batch':'B2','pair':'O2:v1','fragments':[S]}]},[]),
 step('drain','recover',{},facts([S])+[check('/journal/batch_terminal',{'B1':'STALE_SUPERSEDED','B2':'APPLIED'}),check('/store/markers',['B2'],'set_eq')]),
 step('repeat','recover',{},[same('/state/semantic_digest','drain')])],dr=['DR13'])
scenario('PLAN-E-SHARED','Общая entity сохранена, чужие support/binding/time/R-X не записаны','fragment_plan conflict_admission precheck',[
 step('seed','seed_fact',{'formula':g('NOT',P),'window':interval(0,3,'CONTINUOUS'),'source':'OX'},[]),
 step('partial','commit_partial_plan',{'batch':'B','fragments':{'F1':pred('READ',AGENT=IVAN,THEME=BOOK),'F2':P},'shared_entity':'ivan','windows':{'F1':interval(0,3),'F2':interval(0,3)}},[check('/plan/committed',['F1'],'set_eq'),check('/plan/excluded',['F2'],'set_eq'),check('/store/entities',['ivan','book'],'contains'),check('/store/records_for_excluded_fragments',[]),check('/reports/open_count',1)]),
 step('recover','recover',{},[same('/state/semantic_digest','partial'),check('/journal/applied_count',1)])],dr=['DR15'])
for before in (False,True):
 scenario('PARTIAL-D-CHANGED-'+str(int(before)),'Из D восстанавливается реальный partial commit, не новое E','commit_decision conflict_open batch_recovery',[
 step('commit','partial_commit_before_terminal',{'batch':'B','committed':['F1'],'excluded':['F2'],'excluded_evidence_kind':'CANDIDATE_COMMITTED'},[check('/store/marker_count',1),check('/store/commit_decision_count',1),check('/journal/applied_count',0)]),
 step('change','change_conflict_evidence',{'retract_before_recovery':before},[]),
 step('recover','recover',{},[check('/journal/applied_committed',['F1']),check('/journal/applied_excluded',['F2']),check('/reports/open_count',0 if before else 1),check('/candidates/count',1),check('/store/repeated_admission_count',0)]),
 step('again','recover',{},[same('/state/semantic_digest','recover')])],dr=['DR15'])

# Input/canonical/replay/context boundaries.
for field,value in [('source_id',''),('revision',0),('revision',-1),('revision',True),('language','xx'),('batch_kind','INVALID'),('request_kind','INVALID'),('range',[-1,3]),('range',[3,1])]:
 component('INPUT-'+field+'-'+str(value),'Invalid RawInput: no run/batch/AH writes','input writers','validate_input',{'base':raw('Мария спит.'),'override':{field:value}},[check('/input/accepted',False),check('/diagnostics/codes',['INPUT_REJECTED'],'contains'),check('/durable/new_record_count',0)])
for mutation in ['same_revision_different_text','same_pair_different_context_hash','same_pair_different_resource_hash']:
 component('INPUT-CONFLICT-'+mutation,'Идентичная пара не принимает изменённые входы','revision contexts run_binding','replay_identity',{'mutation':mutation},[check('/diagnostics/codes',['INPUT_CONFLICT' if mutation=='same_revision_different_text' else 'INTEGRITY_ERROR'],'contains'),check('/store/new_record_count',0)])
component('ID-COLLISION','Одинаковый candidate_id с различным payload запрещён','canonical_ids','candidate_id_collision',{'forced_digest':'collision','payloads':[{'surface':'а'},{'surface':'б'}]},[check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains'),check('/commit/materialized',False)])
for changed in ['R_entries_order','source_iteration_order','constraint_iteration_order','replay_provider_bytes']:
 scenario('META-'+changed,'Детерминизм при семантически нейтральной перестановке','canonical_ids resource_permutation oracle_replay',[
  step('base','run_fixed_fixture',{'fixture':'SIMPLE_LOCATIVE','mutation':None},[check('/decision/outcome','RESOLVED')]),
  step('other','run_fixed_fixture',{'fixture':'SIMPLE_LOCATIVE','mutation':changed,'isolated_store':True},[same('/ir/candidate_ids','base'),same('/ir/decision_ids','base'),same('/state/semantic_digest','base'),same('/diagnostics/located_multiset','base')])])
for source in ['GenerationContext','ResolutionContext']:
 component('CTX-'+source,'Контекст generation vs resolution без скрытого factual write','contexts grounds','context_candidate_reads',{'context_kind':source,'context_fact':P,'new_structural_antecedent':True},[check('/generation/new_antecedent_candidate_count',int(source=='GenerationContext')),check('/store/context_fact_materialized',False)])
for changed in [False,True]:
 component('DECLARED-'+str(int(changed)),'Только declared read вызывает новую версию','declared_trigger contexts','change_source',{'declared':changed,'new_version':2},[check('/execution/recomputed',changed),check('/identity/version_increment',int(changed))])
component('OSCILLATION-M','Повтор M не re-arm и не truth-ground','oscillation grounds','repeat_selector_cycle',{'choices':['A','B','A'],'real_ground_signature':'unchanged','new_grounds':['M']},[check('/decision/machine_state','FROZEN'),check('/decision/rearmed',False)])
component('OSCILLATION-REAL','Новый ground re-arm','oscillation declared_trigger','repeat_selector_cycle',{'choices':['A','B','A'],'real_ground_signature':'changed','new_grounds':['P:O_new']},[check('/decision/rearmed',True),check('/identity/version_increment',1)])
for missing in ['gender','number','case','person']:
 component('MORPH-UNKNOWN-'+missing,'Неизвестный признак не является hard mismatch','morph_unknown','morph_agreement',{'feature':missing,'left':'UNKNOWN','right':'KNOWN','unknown_is_negative':False},[check('/constraint/result','UNKNOWN'),check('/candidate/rejected_by_missing_feature',False)])
for mismatch in ['gender','number','person']:
 component('MORPH-HARD-'+mismatch,'Контекст не переопределяет известное несогласие','morph_unknown coreference','morph_agreement',{'feature':mismatch,'left':'known_a','right':'known_b','context_favors_left':True},[check('/constraint/result','FALSE'),check('/candidate/rejected_by_hard_feature',True)])
for text in ['Иван,\tПётр — здесь.','  «Мария\nспит»  ','Ксавир\u00a0прибыл!','Я — врач; а он?']:
 component('RAW-'+sha(text.encode())[:8],'Каждый codepoint raw покрыт, spaces/punct сохраняются','raw_alignment','tokenize_alignment',{'text':text},[check('/alignment/reconstructed_text',text),check('/alignment/uncovered_spans',[]),check('/alignment/overlapping_spans',[])])
for problem in ['canonical_uid','new_g_id','truth_claim','out_of_bounds_anchor','role_not_registered','cycle','undeclared_read','new_text','sealed_mutation']:
 component('TP-INVALID-'+problem,'Невалидный local proposal не меняет AH/registry','proposal_validation seal registered_ops','validate_proposal',{'mutation':problem,'base_script':'VALID_LOCAL'},[check('/proposal/accepted',False),check('/diagnostics/codes',['PROPOSAL_INVALID'],'contains'),check('/registry/new_entry_count',0),check('/store/new_record_count',0)])
for cap in ['tp_calls','lexical_calls','nodes','edges','depth','tokens']:
 for over in [False,True]:
    component('BUDGET-'+cap+'-'+str(int(over)),'Граница независимого лимита','proposal_bounds budget','proposal_budget',{'limit_name':cap,'limit':4,'used':5 if over else 4,'recorded_timing_ticks':[0,1,2]},[check('/budget/limit_exceeded',over),check('/decision/search_complete',not over),check('/budget/unvalidated_prefix_committed',False)])
for reply in ['unknown_id','duplicate_id','wrong_shape','non_json','wrong_request_id','empty_one_selected']:
 component('SELECTOR-'+reply,'ID-selector protocol rejection, note не ground','selector provider_log','validate_selector_reply',{'reply_mutation':reply},[check('/selector/accepted',False),check('/diagnostics/codes',['PROTOCOL_ERROR'],'contains'),check('/store/new_record_count',0)])
for response in ['ONE_SELECTED','MULTIPLE_ADMISSIBLE','NONE_FIT']:
 component('SELECTOR-VALID-'+response,'Closed ID-selector не выдаёт произвольный T','selector value_grounds open_lexical','validate_selector_reply',{'response_kind':response,'candidate_ids':['A','B'],'selected_ids':['A'] if response=='ONE_SELECTED' else ['A','B'] if response=='MULTIPLE_ADMISSIBLE' else [],'note':'not a proof'},[check('/selector/accepted',True),check('/selector/value_specific_m_ground',response=='ONE_SELECTED'),check('/selector/arbitrary_known_template_selected',False)])
component('T3-SEAL','T3 lexical proposal не добавляет новый frame','seal proposal_validation','post_seal_proposal',{'new_frame':True},[check('/proposal/accepted',False),check('/structure/seal_changed',False)])

# Review/release schemas: corruption matrices plus successful verification boundary.
RK=['R1','R-V','R-S','PredicateSchema','SyntaxRules','ScopeLexicon','CorefPolicy','R-WK','EvidencePriorityPolicy','TemplateMap','RoleRegistry','ProposalPolicy','OpenTemplatePolicy']
for kind in RK:
 for mutation in ['missing_required_field','unknown_field','wrong_field_type','duplicate_id','unresolved_dependency','dependency_version_mismatch']:
    component('RES-'+kind+'-'+mutation,'Невалидный ресурс не загружается частично','resource_schema resource_missing','load_release',{'fixture':'COMPLETE_SIGNED_TEST_RELEASE','mutate_kind':kind,'mutation':mutation},[check('/release/available',False),check('/diagnostics/codes',['RESOURCE_MISSING'],'contains'),check('/runtime/t0_started',False)],profile='release_validation')
for mutation in ['dependency_cycle','conflicting_entries','unregistered_emit_kind','emit_arity','capture_ref_missing','role_ref_missing','transitive_dependency_missing']:
 component('RES-GRAPH-'+mutation,'Validation поверх JSON Schema','resource_schema dsl','load_release',{'fixture':'COMPLETE_SIGNED_TEST_RELEASE','mutation':mutation},[check('/release/available',False),check('/diagnostics/codes',['RESOURCE_MISSING'],'contains')],profile='release_validation')
for mutation in ['signature_bytes','public_key_length','signature_length','untrusted_reviewer','revoked_key','expired_review','naive_timestamp','tampered_entry','tampered_dependency','tampered_coverage','reviewed_sha256_mismatch','resource_content_sha256_mismatch']:
 component('TRUST-'+mutation,'Review/подпись покрывают данные, зависимости и coverage','release_trust coverage_report','load_release',{'fixture':'COMPLETE_SIGNED_TEST_RELEASE','mutation':mutation,'test_only_trust_registry':True},[check('/release/available',False),check('/diagnostics/codes',['RESOURCE_MISSING'],'contains')],profile='release_validation')
component('TRUST-VALID','Детерминированная тестовая Ed25519 review-атрибуция','release_trust resource_schema coverage_report','load_release',{'fixture':'COMPLETE_SIGNED_TEST_RELEASE','mutation':None,'test_only_trust_registry':True},[check('/release/available',True),check('/release/dependency_closure_checked',True),check('/release/review_content_coverage_verified',True)],profile='release_validation')
component('COVERAGE-NOT-G5','Число слов не полнота semantics','coverage_report coverage_gate','coverage_report',{'units':1000000,'outcomes':{'FULL_CANONICAL':0,'OPEN_LEXICAL':0,'PARTIAL':10,'NONE':0},'surface_only':10},[check('/coverage/semantic_success_count',0),check('/gates/G5/pass',False)])

# Text BNF parser and JSON AST equivalence and limits. Scalar unknown remains 3-valued.
DSL='rule noun:1 {stage=SRL, reads [R1:entries@1], captures={"n":{"POS":"NOUN"}}, when n.POS="NOUN", emit TOKEN_HYPOTHESIS {"capture":"n","variants":["keep_as_is"]}, priority=1, min_evidence=1, coverage_tag="noun"}'
component('DSL-EQUIVALENCE','BNF/JSON AST один data-only runtime','dsl canonical_ids','compile_rule_pair',{'text':DSL,'json_ast_fixture':'EQUIVALENT_NOUN_RULE'},[check('/dsl/ast_equal',True),check('/dsl/output_equal',True),check('/dsl/callback_count',0)])
for mutation in ['duplicate_stage','missing_reads','unknown_field','unknown_candidate_kind','python_eval','NaN','Infinity','wrong_emit_payload','undeclared_LOOKUP','capture_feature_missing','expr_depth_17','chars_262145','rules_4097','join_budget_exceeded']:
 component('DSL-REJECT-'+mutation,'Невалидное правило/лимит не частичный успешный release','dsl dsl_limits','compile_rule',{'base':DSL,'mutation':mutation},[check('/dsl/accepted',False),check('/release/partial_fallback_used',False),check('/dsl/code_executed',False)])
for left,right in [('UNKNOWN','FALSE'),('UNKNOWN','TRUE'),('UNKNOWN','UNKNOWN')]:
 component('DSL-3VAL-'+right,'NOT missing feature не TRUE','dsl dsl_limits morph_unknown','evaluate_rule_expr',{'expression':'NOT (n.gender="masc")','feature_state':left,'irrelevant_other_feature':right},[check('/dsl/truth','UNKNOWN'),check('/dsl/emitted_count',0)])
for expr,expected in [('n.oov=true OR n.POS="VERB" AND n.gender="masc"',True),('NOT (n.oov=true OR n.POS="VERB")',False),('(n.oov=true OR n.POS="VERB") AND n.gender="masc"',False)]:
 component('DSL-PRECEDENCE-'+sha(expr.encode())[:6],'AND до OR, parentheses/NOT','dsl','evaluate_boolean_expr',{'expression':expr,'features':{'n.oov':True,'n.POS':'NOUN','n.gender':'femn'}},[check('/dsl/truth',expected)])

# Provider and run CAS durable boundary including unresolved without materialization marker.
for boundary in ['BEFORE_RUNMARKER','AFTER_PENDING_BEFORE_SEND','AFTER_SEND_BEFORE_RESPONSE','AFTER_RESPONSE_BEFORE_RECEIVED','AFTER_RECEIVED_BEFORE_VALIDATION','AFTER_VALIDATION']:
    received=boundary in ['AFTER_RECEIVED_BEFORE_VALIDATION','AFTER_VALIDATION']
    before_marker=boundary=='BEFORE_RUNMARKER'
    component('CALL-CRASH-'+boundary,'Call ordinal/attempt и fsync replay','provider_log run_binding budget','recover_provider_call',{'boundary':boundary,'run_id':'R','ordinal':1,'attempt':1,'timing_log':[0,1,2],'reply_bytes':'{"kind":"ONE_SELECTED","candidate_id":"A"}'},[check('/provider/recovery_send_count',0 if received else 1),check('/provider/ordinal',1),check('/provider/attempt',1 if received or before_marker else 2),check('/provider/response_replayed',received)],dr=['DR9'])
component('CALL-SAME-PROMPT','Одинаковый prompt с новым ordinal — новый вызов','provider_log','execute_identical_prompts',{'run_id':'R','ordinals':[1,2,3],'prompt':'same bytes'},[check('/provider/send_count',3),check('/provider/ordinals',[1,2,3]),check('/provider/cross_ordinal_cache_hits',0)],dr=['DR9'])
component('RUN-CAS','Два конкурентных run получают единственный canonical binding','run_binding writers','concurrent_run_claim',{'pair':'O:v1','runs':['R1','R2']},[check('/run/canonical_count',1),check('/run/loser_investigation_only',True),check('/run/binding_before_provider',True)])
for prior in ['NO_CANDIDATE','UNRESOLVED','RESOLVED']:
 component('RUN-REPLAY-'+prior,'Повтор без нового trigger не ищет удачный ответ модели','run_binding provider_log states','rerun_same_pair',{'canonical_run_id':'GR0','recorded_outcome':prior,'materialization_marker':prior=='RESOLVED','new_provider_answer':'different valid choice','new_run_id':'GR1'},[check('/run/canonical_run_id','GR0'),check('/run/new_run_mode','INVESTIGATION_ONLY'),check('/provider/new_canonical_send_count',0),check('/run/new_t5_batch_count',0)],dr=['DR9','DR23'])
for what in ['C_plan','QUERY_result','COMMAND_no_goal','agent_utterance']:
 component('WRITER-'+what,'Не factual writer — не AH commit','writers modus query_readonly','non_factual_path',{'kind':what},[check('/store/new_factual_record_count',0),check('/store/new_marker_count',0)])
component('RECONCILE-EXACT-VERSION','Marker v1 не маскирует потерянную v2','batch_recovery event_audit_integrity','reconcile',{'declared_committed_pair':'O:v2','markers':['O:v1']},[check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains'),check('/service/factual_reads_enabled',False)])

# Events cannot be silently rebuilt. Projection can.
for corruption in ['missing_event','extra_event','wrong_order','duplicate_identity']:
 component('AUDIT-'+corruption,'Повреждение audit: fail safe, без чинящего append','event_audit_integrity node_events','recover_node_events',{'mutation':corruption,'canonical_support_statuses':{'s_a':'SUPERSEDED','s_b':'SUPERSEDED'}},[check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains'),check('/service/factual_reads_enabled',False),check('/audit/repair_append_count',0)])
component('AUDIT-PROJECTION','Утрата fast index не повреждает audit','event_audit_integrity','recover_node_events',{'mutation':'missing_derived_index'},[check('/projection/rebuilt',True),check('/audit/mutated',False),check('/service/factual_reads_enabled',True)])
scenario('AUDIT-TWO-SUPPORTS','Две опоры в одном batch: identity содержит support_id','node_events event_audit_integrity reaccess',[
 step('create','commit_two_state_supports',{'node':'N','support_ids':['s_a','s_b'],'tx_ref':'H_B1'},[check('/events/N/types',['CREATED','SUPPORT_ADDED','SUPPORT_ADDED']),check('/events/N/support_ids',[None,'s_a','s_b']),check('/events/N/seq',[0,1,2]),check('/events/identity_unique',True)]),
 step('withdraw','retract_support_batch',{'support_ids':['s_b','s_a'],'tx_ref':'R_B2'},[check('/events/last_tx/types',['SUPPORT_RETRACTED','SUPPORT_RETRACTED','CASCADE_SUPERSEDED']),check('/events/last_tx/support_ids',['s_a','s_b',None]),check('/events/last_tx/seq',[0,1,2])]),
 step('recover','recover',{},[check('/events/N/count',6),check('/service/factual_reads_enabled',True),check('/audit/mutated',False)])])

# R-X stage isolation and liveness, never semantic alias or factual confirmation.
for state in ['COMMITTED_LIVE','SUPERSEDED','JOURNALED','AMBIGUOUS']:
 for stage in ['SRL','T2','T3']:
    readable=state=='COMMITTED_LIVE'
    component('RX-'+state+'-'+stage,'R-X cache не ground; stage isolation','rx grounds','rx_read',{'record_state':state,'read_stage':stage,'record_stage':stage,'open_lexical':True},[check('/rx/readable',readable),check('/rx/writes_uncommitted',False),check('/supports/root_from_rx',0),check('/aliases',[])])
component('RX-FROZEN','Новый опыт не меняет replay прежней пары','rx contexts','rx_replay',{'frozen_snapshot':'RX1','current_snapshot':'RX2','pair':'O:v1'},[check('/rx/read_snapshot','RX1'),check('/run/new_version_created',False)])
for ground in ['R','W','C']:
 component('CLOSURE-'+ground,'Общее правило и общий factual источник имеют разный смысл','closure_independence support_paths','proof_independence',{'supports':['s1','s2'],'observation_sources':['O1','O2'],'shared_ground':ground},[check('/proof/independent',ground=='R'),check('/proof/retract_O1_keeps_s2',True)])

# Migration success/failure/receipts. Rollback before commit does not mean resurrection later.
for failure in ['NONE','BEFORE_STORE_COMMIT','AFTER_STORE_BEFORE_TERMINAL','AFTER_SUCCESS_RETRACT_V2','AMBIGUOUS_SENSE','STALE_INPUT']:
 component('MIG-'+failure,'Known/open migration frozen v+1 и история','migration migration_failure declared_trigger source_retraction','execute_migration',{'source':'O1','from_version':1,'to_version':2,'mapping':'explicit_release_mapping','equivalence_supports':['EQ1'],'failure':failure},[check('/migration/old_supports_live',failure in ['BEFORE_STORE_COMMIT','AMBIGUOUS_SENSE','STALE_INPUT']),check('/migration/old_records_rewritten',False),check('/migration/alias_reasoner_enabled',False),check('/migration/old_supports_resurrected',False)],dr=['DR23'])
for boundary in ['BEFORE_PLAN','AFTER_RESERVE','AFTER_ITEM_COMMIT_BEFORE_RECEIPT','AFTER_RECEIPT']:
 component('MIG-BULK-'+boundary,'Массовая миграция per-item, не job transaction','migration_bulk migration batch_recovery','recover_bulk_migration',{'observations':['O2','O1'],'target_versions':{'O1':2,'O2':3},'boundary':boundary,'frozen_context_hash':'CTX','resource_snapshot':'REL2'},[check('/migration/item_order',['O1','O2']),check('/migration/target_versions_reused',False),check('/migration/item_receipts_unique',True),check('/migration/provider_holds_writer_lock',False),check('/migration/atomicity','PER_OBSERVATION')])
for bad in ['name_similarity_only','dead_equivalence_support','changed_frozen_source_text','reused_target_version']:
 component('MIG-BLOCK-'+bad,'Нет неявного identity или ремонта frozen job','migration_bulk migration_failure','plan_migration',{'invalid_condition':bad},[check('/migration/applied',False),check('/aliases',[])])
for shape in ['representable_graph','open_template','nested_scope','surface_arg','typed_count_literal','structural_usage_link']:
    lossless=shape=='representable_graph'
    component('ADAPTER-'+shape,'Legacy adapter не теряет неподдержанную структуру','legacy_adapter','legacy_roundtrip',{'shape':shape,'legacy_declared_capabilities':['representable_graph']},[check('/adapter/legacy_used',lossless),check('/adapter/lossy_coercion',False),check('/adapter/v2_preserved',not lossless)]+([] if lossless else [check('/diagnostics/codes',['ADAPTER_NOT_COVERED'],'contains')]))

# ExactAttestation constraints; origin-scoped aliases are fixture bindings, not spelling-based identity.
for mismatch in ['none','verb','role','scope','source_scope','dead_proof','surface_as_agent','absolute_query_token_position']:
    yes=mismatch in ['none','absolute_query_token_position']
    component('EXACT-'+mismatch,'Точное открытое свидетельство — не canonical equivalence','exact_attestation workspace query_readonly open_lexical','exact_attestation_query',{'asserted_open_formula':pred('OPEN:переадресовать',AGENT=ent('courier'),THEME=ent('letter')),'activated_source':'O1','change':mismatch,'fixture_identity_bindings':{'query:courier':'courier','query:letter':'letter'}},[check('/answer/status','YES' if yes else 'UNKNOWN'),check('/query/new_derived_supports',0),check('/query/new_markers',0),check('/aliases',[])]+([check('/answer/semantic_status','UNLINKED')] if yes else []),dr=['DR23'])
for kind,target in [('WH','RoleFillGoal'),('YESNO','FormulaGoal'),('COUNT','CountGoal'),('CAUSAL','CauseEntailmentGoal'),('ASSOCIATIVE','AssociationGoal'),('COUNTERFACTUAL','CounterfactualGoal')]:
    component('COMPILE-'+kind,'Правильный goal sort, без подмены EXISTS','goal_compile query_readonly','compile_query_kind',{'query_kind':kind,'declared_handler':True,'ready_formula':P},[check('/goal/kind',target),check('/query/factual_result_materialized',False)])
for unsupported in ['SUPERLATIVE','COMPARISON','AMBIGUOUS_OWNER','CAUSAL_NO_HANDLER','IF_UNKNOWN_BOUNDARIES']:
    component('COMPILE-BLOCK-'+unsupported,'Неподдержанный запрос честно unbound','goal_compile','compile_query_kind',{'query_kind':unsupported,'declared_handler':False},[check('/diagnostics/codes',['QUERY_TARGET_UNBOUND'],'contains'),check('/goal/arbitrary_exists_fallback',False)])
for value in [0,1,2,1000000000000,-1,1000000000001,1.5,True]:
 valid=type(value) is int and 0<=value<=10**12
 component('NUM-LITERAL-'+str(value),'Typed CountLiteral не UID и не число от TP','numeric_scope registered_ops','numeric_scope_literal',{'operator':'EXACTLY_N','literal':value,'source':'RAW_DIGITS'},[check('/literal/accepted',valid),check('/store/fictitious_entity_count',0),check('/usage/nonproposition_link_count',0)])
for source in ['RAW_DIGITS','DECLARED_NUMERAL_RULE','MODEL_NUMBER_ONLY']:
 component('NUM-SOURCE-'+source,'Числовое значение имеет raw/resource ground','numeric_scope proposal_validation','numeric_scope_literal',{'literal':3,'source':source},[check('/literal/accepted',source!='MODEL_NUMBER_ONLY'),check('/store/fictitious_entity_count',0)])
for distinct in [1,2,4]:
 for certificate in ['NONE','VALID','WRONG_BODY','WRONG_WINDOW','DEAD_COMPLETENESS_SUPPORT']:
    valid=certificate=='VALID'
    component(f'COUNT-{distinct}-{certificate}','Distinct M, finite list не domain closure','count_domain formula_domain query_readonly','count_query',{'witness_entities':['e'+str(k) for k in range(distinct)]+['e0']*2,'certificate':certificate,'body':pred('STUDENT',THEME=var('x')),'count_variable':'x','window':None,'comparison':'EXACT'},[check('/answer/lower_bound',distinct),check('/answer/exact_count',distinct if valid else None),check('/answer/domain_complete',valid),check('/query/factual_result_materialized',False)])
for n in [1,2,3]:
 component('COUNT-ATLEAST-'+str(n),'AT_LEAST_N из lower bound без closed world','count_domain numeric_scope','count_query',{'witness_entities':['e1','e2'],'certificate':'NONE','body':pred('STUDENT',THEME=var('x')),'comparison':'AT_LEAST','threshold':n},[check('/answer/status','YES' if n<=2 else 'UNKNOWN'),check('/answer/lower_bound',2),check('/answer/domain_complete',False)])
for mismatch in ['restriction','count_variable','nested_scope','time_window','source_scope','dead_support']:
 component('CERT-'+mismatch,'FormulaDomainCertificate scoped alpha/body/window/live','formula_domain count_domain','validate_formula_certificate',{'signature_version':'native-query-pattern-v1','change':mismatch},[check('/certificate/valid',False),check('/answer/exact_count',None),check('/answer/domain_complete',False)])
component('CERT-ALPHA','Alpha rename при одинаковом capture-safe body','formula_domain compound_binding','validate_formula_certificate',{'signature_version':'native-query-pattern-v1','renaming':{'x':'y'},'capture_safe':True},[check('/certificate/valid',True),check('/signature/alpha_equal',True)])
for scope in ['AND','OR','NOT','EXISTS','FORALL','IMPLIES','QUOTED']:
 for fullproof in [False,True]:
    component('BIND-'+scope+'-'+str(int(fullproof)),'NativeBindingGoal доказывает полную формулу','compound_binding query_readonly modal_guard','compound_binding_query',{'mode':'WH','scope':scope,'runtime_variable':'q','candidate_bindings':['ivan','petr'],'whole_pattern_proof_entities':['ivan'] if fullproof else [],'atomic_body_match_entities':['ivan','petr'],'quoted_content_independent_assertion':False},[check('/answer/binding_entities',['ivan'] if fullproof else [],'set_eq'),check('/query/variable_has_ah_uid',False),check('/query/chosen_branch_materialized',False),check('/query/new_root_supports',0)])
for combinations in [1023,1024,1025]:
 component('QUERY-BUDGET-'+str(combinations),'Незавершённый gap product не completeness','query_budget compound_binding formula_domain','compound_binding_budget',{'required_combinations':combinations,'limit':1024,'enumeration_exhausted':combinations<=1024},[check('/query/search_complete',combinations<=1024),check('/query/domain_certificate_inferred_from_enumeration',False),check('/query/combinations_visited',min(combinations,1024))])
for order in ['BEFORE','AFTER','DURING']:
 for wa,wb in [(point(0),point(3)),(point(3),point(0)),(interval(0,1),interval(2,3)),(interval(0,3),interval(1,2)),(point(1),interval(0,3,'CONTINUOUS'))]:
    na,nb=norm(wa),norm(wb)
    valid=na[2]<nb[1] if order=='BEFORE' else nb[2]<na[1] if order=='AFTER' else or_license(wa,wb)
    component('ORDER-'+order+'-'+sha(canonical([wa,wb]).encode())[:8],'Порядок по гарантированным bounds; overlap не DURING','ordering_goal query_time','ordering_query',{'operator':order,'left_witness':wa,'right_witness':wb,'explicit_relation':None},[check('/answer/status','YES' if valid else 'UNKNOWN'),check('/query/new_root_supports',0)])
component('MP-NO-CONVERSE','Implication не converse и не contraposition','modus_ponens modal_guard','modus_ponens_query',{'implication':g('IMPLIES',P,S),'asserted':S,'target':P},[check('/answer/status','UNKNOWN'),check('/derived/support_count',0)])
scenario('MP-BOTH-PREMISES','Modus ponens хранит обе опоры','modus_ponens support_paths',[
 step('proof','modus_ponens_query',{'implication':g('IMPLIES',P,S),'asserted':P,'target':S},[check('/answer/status','YES'),check('/derived/premise_count',2)]),
 step('withdraw','retract_observation',{'observation':'O_antecedent'},[check('/derived/effective',False),check('/answer/status','UNKNOWN')])])
component('DR5-PARTIAL','Знакомая часть+неизвестная связь не полный frame','partial multi_anchor coverage','formalize_partial',{'text':'Мария спит; Иван глоркнул книгу посредством непокрытой связи.','resolved_fragments':[S],'unresolved_attachment':True,'tp_abstain':True},facts([S])+[check('/coverage/status','PARTIAL'),check('/coverage/opaque_full_claim',False),check('/audit/raw_input_retained',True)],dr=['DR5'])

# Clean up linguistic assertions not justified by mere nominal coordination/perfective morphology.
for c in CASES:
    if c['case_id']=='A02':
        grouped=pred('ARRIVE',AGENT={'group':[IVAN,PETR]})
        c['steps'][0]['checks']=facts([grouped])+[check('/generation/coordination_kind','NOMINAL_GROUP'),check('/generation/event_frame_count',1)]
    if c['case_id']=='A03': c['steps'][0]['payload']['raw_input']=raw('Иван пришёл и Мария спит.','A03')
    if c['case_id']=='A35':
        c['fixture_profile']='open'
        c['steps'][0]['payload']['resource_profile']='open'
        c['steps'][0]['payload']['raw_input']=raw('Мария перестала курить.','A35')
        old=pred('STOP_LEXICAL',EXPERIENCER=MARIA,CONTENT=pred('SMOKE',AGENT=MARIA))
        new=pred('OPEN:перестать',EXPERIENCER=MARIA,CONTENT=pred('SMOKE',AGENT=MARIA))
        for ck in c['steps'][0]['checks']:
            if ck['op']=='set_eq' and ck['path'].startswith('/assertions/'):ck['value']=[new]
    if c['case_id'].startswith('LANG-') and c['case_id'].endswith('-continuous'):
        base_i=int(c['case_id'].split('-')[1]);tag=PATTERNS[base_i][2]
        if tag not in ['state','process','nominal']: c['_remove']=True
        else:
            r=c['steps'][0]['payload']['raw_input']; text=r['text'].replace('сидит','сидел').replace('работает','работал')
            c['steps'][0]['payload']['raw_input']=raw(text,c['case_id'])
    if c['case_id'].startswith('ORT-'):
        payload=c['steps'][0]['payload'];w=payload['root_witness']
        if w is not None and w['kind']=='INTERVAL' and w.get('semantics')=='EXISTENTIAL' and isinstance(w['bounds'][0],int) and w['bounds'][0]==w['bounds'][1]:
            for ck in c['steps'][0]['checks']:
                if ck['path']=='/derived/time' and ck['value'] is not None:ck['value']=point(w['bounds'][0])
CASES[:]=[c for c in CASES if not c.pop('_remove',False)]

# Extra explicit boundaries found during gold review.
mech('alpha_scope','§6.2 §17','Alpha capture, binder uniqueness, tree/graph roundtrip')
mech('disabled_bridges','§2.1 §20','ReportBridgingRule/EventIdentityRule disabled defaults')
mech('registry_rollback','§7.3 §17','Unknown ID/role/support variant rolls back whole transaction')
mech('open_world','§6.2 §15','Отсутствие доказательства не явное отрицание')
for mutation in ['free_variable','double_binder','capture_after_substitution','string_restriction','three_slot_FORALL','quantifier_scope_first_wins']:
 component('SCOPE-INVALID-'+mutation,'Binder/alpha/scope не теряется и не угадывается','alpha_scope scopes alternatives','validate_scope',{'mutation':mutation},[check('/scope/valid',False),check('/store/new_asserted_fact_count',0)])
component('SCOPE-ROUNDTRIP','G↔ScopeTree обратимость и alpha pre-order','alpha_scope function_identity','scope_roundtrip',{'tree':g('FORALL',var('x'),g('EXISTS',var('y'),g('IMPLIES',pred('KNOW',AGENT=var('x'),THEME=var('y')),pred('PERSON',THEME=var('y')))))},[check('/scope/roundtrip_equal',True),check('/scope/binder_ids',['x0','x1']),check('/scope/free_variables',[])])
for rule in ['ReportBridgingRule','EventIdentityRule']:
 component('DISABLED-'+rule,'Нет bridge/identity из того, что человеку очевидно','disabled_bridges modal_guard occurrence_identity','disabled_rule_request',{'rule':rule,'phase':'P4','explicit_rule_enabled':False},[check('/inference/rule_fired',False),check('/inference/unsupported_truth_count',0)])
for problem,code in [('unknown_g','REGISTRY_REJECT'),('unknown_L','REGISTRY_REJECT'),('open_role_mismatch','OPEN_TEMPLATE_INVALID'),('GOAL_RUN_ROOT','INTEGRITY_ERROR'),('OBSERVATION_OR_DERIVED','INTEGRITY_ERROR'),('missing_support_record','INTEGRITY_ERROR'),('conclusion_target_mismatch','INTEGRITY_ERROR')]:
 component('WRITE-ROLLBACK-'+problem,'Write boundary атомарен: новый T не остаётся сиротским','registry_rollback registered_ops time_provenance writers','invalid_write_transaction',{'fault':problem,'create_open_t_first':True},[check('/diagnostics/codes',[code],'contains'),check('/store/new_node_count',0),check('/store/new_template_count',0),check('/store/new_support_count',0),check('/store/new_marker_count',0)])
for polarity in ['POSITIVE','NEGATIVE']:
 component('OWA-ABSENT-'+polarity,'Empty память не YES и не NO','open_world query_readonly','query',{'formula':P if polarity=='POSITIVE' else g('NOT',P),'initial_state':'EMPTY'},[check('/answer/status','UNKNOWN'),check('/query/new_root_supports',0)])
component('GOAL-ATOMIC-MISSING','Decision APPLIED без атомарного support/time — повреждение','goal_decision event_audit_integrity','recover_goal_atomic_pair',{'decision':'APPLIED','support_exists':False,'time_exists':False},[check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains'),check('/service/factual_reads_enabled',False)])
component('GOAL-TIME-MISSING','Dated derived support без TimeAssertion — повреждение','goal_decision time_provenance event_audit_integrity','recover_goal_atomic_pair',{'decision':'APPLIED','support_exists':True,'time_exists':False,'dated':True},[check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains'),check('/service/factual_reads_enabled',False)])
scenario('DR2-FULL','Coreference v1→v2→v3→отзыв antecedent','coreference binding_paths declared_trigger source_retraction grounds',[
 step('v1','formalize_reference_with_context',{'raw_input':raw('Он взлетел.','O_cur'),'generation_antecedents':[],'context_version':1},[check('/decision/outcome','UNRESOLVED')]+facts([])),
 step('v2','declare_context_version',{'observation':'O_cur','context_version':2,'antecedent_observation':'O_plane','antecedent':'plane','antecedent_ground':'P:O_plane','morphology':{'plane':'masc','runway':'femn'}},[check('/binding/target','plane'),check('/decision/outcome','RESOLVED'),check('/supports/root_ground_types',['O'],'set_eq'),check('/identity/interpretation_version',2)]),
 step('v3','declare_context_version',{'observation':'O_cur','context_version':3,'irrelevant_resource_change':True},[check('/execution/recomputed',True),check('/binding/target','plane'),check('/identity/interpretation_version',3)]),
 step('v4','retract_observation',{'observation':'O_plane'},[check('/binding/status','INVALID'),check('/facts/current_visible',False),check('/observations/O_cur/retracted',False)])],dr=['DR2'])
scenario('DR11-FULL','FORALL root-only commit, запрос, отзыв membership','forall_demand forall_time support_paths goal_decision',[
 step('root','commit_batch',{'batch':'B1','formulas':[ALL]},[check('/store/forall_instance_count',0),check('/supports/root_count',1)]),
 step('member','commit_batch',{'batch':'B2','formulas':[pred('STUDENT',THEME=IVAN)]},[check('/store/forall_instance_count',0)]),
 step('goal','derive_forall',{'quantified_root':ALL,'restriction':pred('STUDENT',THEME=IVAN),'root_witness':None,'restriction_witness':None},[check('/derived/support_count',1),check('/goal/new_marker_count',0),check('/goal/new_interpretation_version_count',0),check('/goal/outcome','APPLIED')]),
 step('withdraw','retract_observation',{'observation':'O_membership'},[check('/derived/effective',False),check('/quantified_root/f_visible',True)]),
 step('query','query',{'formula':pred('PASS_EXAM',AGENT=IVAN)},[check('/answer/status','UNKNOWN')])],dr=['DR11'])
scenario('DR12-FULL','AND два STATE конъюнкта, общий existential witness, отзыв','and_commit witness_correlation time_provenance source_retraction',[
 step('commit','commit_dated_conjunction',{'root':g('AND',LOC,pred('WET',THEME=BOOK)),'window':interval(0,3),'source':'O_and','witness_ref':'W_AND'},[check('/supports/root_count',1),check('/supports/derived_count',2),check('/time_assertions/derived_source_types',['OBSERVATION','OBSERVATION']),check('/time_assertions/shared_witness_count',3)]),
 step('point','query',{'formula':LOC,'point':1},[check('/answer/status','UNKNOWN')]),
 step('retract','retract_observation',{'observation':'O_and'},[check('/time_assertions/statuses',['RETRACTED','RETRACTED','RETRACTED']),check('/derived/live_path_count',0)]),
 step('query','query',{'formula':LOC,'window':[0,3]},[check('/answer/status','UNKNOWN')])],dr=['DR12'])
scenario('DR16-FULL','Сегодняшняя OR и вчерашняя NOT не выводят сегодня','or_time goal_license_race source_retraction effective_time',[
 step('seed','seed_temporal_or',{'or_formula':g('OR',P,Q),'or_window':interval(0,3),'not_formula':g('NOT',Q),'not_window':interval(-3,-1,'CONTINUOUS')},[]),
 step('wrong','derive_or',{'root_witness':interval(0,3),'not_witness':interval(-3,-1,'CONTINUOUS')},[check('/answer/status','UNKNOWN'),check('/journal/goal_pending_count',0),check('/derived/support_count',0)]),
 step('replace','replace_not_observation',{'old_source':'O_not_old','new_source':'O_not_new','not_window':interval(0,3,'CONTINUOUS')},[]),
 step('right','derive_or',{'root_witness':interval(0,3),'not_witness':interval(0,3,'CONTINUOUS')},[check('/answer/status','YES'),check('/derived/time',interval(0,3))]),
 step('retract','retract_observation',{'observation':'O_or'},[check('/derived/effective',False),check('/time_assertions/A_derived/status','LIVE'),check('/time_assertions/A_derived/effective',False)]),
 step('query','query',{'formula':P,'window':[0,3]},[check('/answer/status','UNKNOWN')])],dr=['DR16'])
for caller_hash in ['SAME','DIFFERENT']:
 component('DR9-MARKER-'+caller_hash,'Чужой hash marker не допускает новый факт','batch_idempotence run_binding','t6_with_marker',{'marker_hash':'H1','caller_hash':'H1' if caller_hash=='SAME' else 'H2','canonical_run':True},[check('/store/repeated_operation_count',0),check('/journal/new_fact_count',0),check('/diagnostics/codes',[] if caller_hash=='SAME' else ['INTEGRITY_ERROR'],'set_eq')],dr=['DR9'])
for how in ['ASSERTION_ID','UNKNOWN_ID','REPEAT_ID']:
 component('RET-BOUNDARY-'+how,'Per-assertion durable record и статус согласованы','assertion_retraction event_audit_integrity','explicit_assertion_retraction',{'mode':how,'assertion_id':'A'},[check('/journal/time_retraction_count',1 if how!='UNKNOWN_ID' else 0),check('/store/support_alive',True),check('/store/observation_alive',True),check('/store/other_time_assertions_unchanged',True)]+([check('/diagnostics/codes',['INTEGRITY_ERROR'],'contains')] if how=='UNKNOWN_ID' else []),dr=['DR28','DR30'])
for prior in ['AMBIGUOUS','UNRESOLVED','NO_CANDIDATE','INSUFFICIENT_CONTEXT']:
 component('STATE-NONRESOLVED-'+prior,'T4 завершён без RESOLVED: version SEALED, decision PROVISIONAL','states run_binding','completed_t4_state',{'outcome':prior,'resolved_fragment_count':0},[check('/version/state','SEALED'),check('/decision/machine_state','PROVISIONAL'),check('/store/new_marker_count',0)])
component('STATE-MIXED','Один resolved фрагмент разрешает частичный C plan','states partial','completed_t4_state',{'outcomes':['RESOLVED','UNRESOLVED'],'resolved_fragment_count':1},[check('/version/state','RESOLVED'),check('/decisions/machine_states',['RESOLVED_LOCAL','PROVISIONAL']),check('/plan/fragment_count',1)])

# Numeric bound contents and aggregation, not just counting a list of entities.
for closure in ['NONE','ENUMERATED','ASSERTED_BOUND']:
 for matching in [False,True]:
  for live in [False,True]:
   exact=matching and live and closure!='NONE'
   component(f'COUNT-CLOSURE-{closure}-{int(matching)}-{int(live)}','Сертификат closure scoped body и live grounds','count_domain numeric_scope formula_domain','count_from_asserted_bounds',{'asserted_lower':3,'asserted_upper':3,'counted_distinct_entities':['e1','e2','e3'] if closure=='ENUMERATED' else ['e1','e2'],'bounds_body_matches':matching,'bounds_proof_live':live,'closure_mode':closure,'certificate_present':closure!='NONE','certificate_body_matches':matching,'certificate_supports_live':live},[check('/answer/lower_bound',3 if matching and live or closure=='ENUMERATED' else 2),check('/answer/exact_count',3 if exact else None),check('/store/fictitious_entity_count',0)])
component('COUNT-NO-WINDOW-AGGREGATION','Existential числовое утверждение не total unique count окна','count_domain query_time','count_window_aggregate',{'asserted_scope':g('EXACTLY_N',var('x'),pred('STUDENT',THEME=var('x')),{'count_literal':3}),'witness':interval(0,3),'aggregation_domain_declared':False},[check('/answer/exact_count',None),check('/answer/domain_complete',False),check('/store/fictitious_entity_count',0)])
component('OPEN-OR-CROSS-SOURCE','Две одинаковые open леммы не одинаковые proposition Ref','open_key open_lexical or_demand','open_or_cross_source',{'or_operand_observation':'O1','not_operand_observation':'O2','same_surface':'глоркнул','same_roles':True,'same_time':True,'declared_equivalence':False},[check('/answer/status','UNKNOWN'),check('/derived/support_count',0),check('/aliases',[])])
for rule in ['AND_ELIMINATION','OR_ELIMINATION','FORALL_INST']:
 component('DERIVED-G-'+rule,'Выведенный оператор имеет conclusion Ref(G), не N(P)','and_commit or_demand forall_demand modal_guard','derive_operator_conclusion',{'rule_id':rule,'conclusion':g('NOT',P),'premises_proven':True,'same_time_license':True},[check('/derived/conclusion_type','G'),check('/derived/root_support_count',0),check('/derived/support_count',1),check('/operands/independent_truth_count',0)])
for position in [127,128,129]:
 component('COREF-WINDOW-'+str(position),'Объявленная граница coreference window','coreference contexts','resolve_reference_window',{'text':'Он пришёл.','distance_tokens':position,'max_window':128,'declared_antecedent':'ivan','value_ground':'P:O1'},[check('/reference/candidate_in_window',position<=128),check('/binding/created',position<=128)])
for pronoun in ['я','ты']:
 for ctx in [False,True]:
  component('COREF-DEIXIS-'+pronoun+'-'+str(int(ctx)),'Speaker/addressee не выдумываются из местоимения','coreference contexts','resolve_deictic_reference',{'pronoun':pronoun,'speaker_addressee_context_present':ctx},[check('/reference/resolved',ctx),check('/store/fictitious_entity_count',0)])
for att in ['QUOTED','EMBEDDED','HYPOTHETICAL','UNKNOWN']:
 component('ATTITUDE-'+att,'Attitude на UsageLink, не на content identity','attitude_links som modal_guard','materialize_attitude_argument',{'content':P,'attitude':att,'holder':'ivan','source':'O1'},[check('/usage/attitude',att),check('/content/epistemic','UNATTACHED'),check('/content/root_support_count',0),check('/content/f_visible',False)])
for prefix,lemma in [('начал','начать'),('перестал','перестать'),('снова смог','снова-мочь')]:
 content=pred('READ',AGENT=IVAN,THEME=BOOK)
 lang('LEXICAL-SCOPE-'+lemma,'Иван '+prefix+' читать книгу.',[pred('OPEN:'+lemma,AGENT=IVAN,CONTENT=content)],'open_lexical registered_ops som modal_guard',profile='open',extra=forbidden([content])+[check('/store/unregistered_functions',[]),check('/time/invented_past_intervals',[])],gold=[content],tags=['nonfinite','unknown_lexical'])

# A pipeline language case intentionally doesn't prescribe the implementation's arbitrary IDs.
# Its closed compiled §11.2 OracleCase must bind symbolic fixtures independently of SUT output.
FIXTURES={
 'schema_version':'v7-symbolic-fixtures-1',
 'time':{'source_timestamp':'2026-10-09T12:00:00+00:00','timezone':'UTC','yesterday':['2026-10-08T00:00:00+00:00','2026-10-09T00:00:00+00:00'],'today':['2026-10-09T00:00:00+00:00','2026-10-10T00:00:00+00:00'],'vector_ticks':'exact fixture-relative rational coordinates, closed sets; not system clock'},
 'entities':{'ivan':{'naming_evidence':'explicit fixture identity binding, not spelling similarity'},'petr':{},'maria':{},'book':{},'table':{},'shelf':{},'courier':{},'letter':{},'chair':{},'window':{},'moscow':{},'speaker':{'source':'declared speaker context'},'addressee':{'source':'declared addressee context'},'sergey':{},'alexey':{}},
 'profiles':{
  'known':{'required_registered_senses':'all non-OPEN predicate symbols used by selected cases; mapping and roles pinned independently','role_registry':['AGENT','THEME','LOCATION','CONTENT','EXPERIENCER','RECIPIENT','ADDRESSEE','DESTINATION','SOURCE','LEFT','RIGHT'],'disabled_rules':['ReportBridgingRule','EventIdentityRule'],'provider':'FAKE scripted, requests recorded, selected sense/role pinned by case'},
  'open':{'base':'known','absent_senses':['переадресовать','глоркнуть','зумбировать','флукнуть','квелировать','бронкнуть','шарпировать','траверсировать','холодно','перестать','начать','снова-мочь'],'open_template_policy':'valid','surface_roles_require_proven_attachment':True,'aliases':[]},
  'known_mapping_broken':{'base':'known','selected_known_sense':'K_SEND','template_mapping':'deliberately absent; no open replacement'},
  'release_validation':{'base':'COMPLETE_SIGNED_TEST_RELEASE','test_only_trust':True,'ed25519_test_seed_hex':'7f'*32,'reviewer_id':'ORACLE_FIXTURE_ONLY','production_review_claim':False,'recipe':'construct one valid entry per selected resource schema from source fixture builder; sign canonical release payload; mutate exactly the stated dimension after signing when testing tampering'}
 },
 'provider_scripts':{'VALID_LOCAL':{'scope':'only declared fixture-local frames/roles and raw spans','no_canonical_uid':True,'no_new_g_or_L':True,'no_truth_claim':True,'deterministic':True},'EQUIVALENT_NOUN_RULE':{'rule_id':'noun','stage':'SRL','input_feature_pattern':{'captures':{'n':{'POS':'NOUN'}},'window':'SENTENCE','distinct':True,'where':{'op':'feature_eq','field':'n.POS','value':'NOUN'}},'output_kind':'TOKEN_HYPOTHESIS','output':{'capture':'n','variants':['keep_as_is']},'constraints':[],'priority':1,'min_evidence':1,'coverage_tag':'noun'}},
 'binding_policy':{'actual_uids':'independent fixture builder records Ref map before run','candidate_ids':'compute from fixture producers and canonical payload per §1.3, not learn from SUT','hashes':'hash actual fixture bytes and independently built initial/gold snapshots; never zero/guessed hashes','extra_actual_nodes':'must be exported with unbound:<uid> aliases, never filtered away','scope_identity':'typed AST including occurrence and variable scope; not rendered text','event_occurrences':'alias includes observation/goal path key; content equality is not event identity','stage_tests':'component cases cannot count as full G3/G4/G5 pipeline success'}
}

TEMPLATES={}
def catalogue_templates(x):
    if isinstance(x,dict):
        if 'predicate' in x and isinstance(x['predicate'],str) and not x['predicate'].startswith('OPEN:') and isinstance(x.get('roles'),dict):
            TEMPLATES.setdefault(x['predicate'],set()).add(tuple(sorted(x['roles'])))
        for v in x.values():catalogue_templates(v)
    elif isinstance(x,list):
        for v in x:catalogue_templates(v)
catalogue_templates(CASES)
FIXTURES['registered_templates']=[{'symbol':k,'role_signatures':[list(sig) for sig in sorted(v)],'uid_policy':'real UID returned by fixture AH template creation; record in binding manifest before SUT'} for k,v in sorted(TEMPLATES.items())]

SCHEMA={
 '$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:ag-memory:v7-symbolic-oracle:1','type':'object','additionalProperties':False,
 'required':['schema_version','case_id','title','tier','mechanisms','norm_refs','acceptance_refs','dry_run_refs','fixture_profile','tags','description','initial_state','steps'],
 'properties':{
  'schema_version':{'const':'v7-symbolic-oracle-1'},'case_id':{'type':'string','minLength':1},'title':{'type':'string','minLength':1},'tier':{'enum':['pipeline','component','durability','metamorphic','resource','query']},
  **{k:{'type':'array','items':{'type':'string'},'uniqueItems':True} for k in ['mechanisms','norm_refs','acceptance_refs','dry_run_refs','tags']},
  'fixture_profile':{'enum':list(FIXTURES['profiles'])},'description':{'type':'string'},'initial_state':{'const':'EMPTY'},
  'steps':{'type':'array','minItems':1,'items':{'type':'object','additionalProperties':False,'required':['id','action','payload','checks'],'properties':{'id':{'type':'string','minLength':1},'action':{'type':'string','minLength':1},'payload':{'type':'object'},'checks':{'type':'array','items':{'oneOf':[
   {'type':'object','additionalProperties':False,'required':['op','path','value'],'properties':{'op':{'enum':['eq','set_eq','multiset_eq','contains','excludes','count']},'path':{'type':'string','pattern':'^/'},'value':{}}},
   {'type':'object','additionalProperties':False,'required':['op','path','checkpoint'],'properties':{'op':{'const':'same_as'},'path':{'type':'string','pattern':'^/'},'checkpoint':{'type':'string'}}}
  ]}}}}}
 }
}

README='''# Oracle нормативной архитектуры V7

Это независимое gold-описание, составленное по приложенному документу. Генератор не импортирует формализатор и не извлекает ожидаемые результаты из его ответов. Все файлы UTF-8. Сборка воспроизводима.

## Состав и назначение

`cases.jsonl` — конкретные входы/сценарии и ожидаемые checkpoint-проверки. `fixtures.json` — декларативные тестовые предпосылки. `mechanisms.json` и `coverage.json` — механизм → кейсы, A01–A39, DR1–DR31. `source_map.json` — заголовки и расположение норм в точном исходном документе. `manifest.json` пинит SHA256 архитектуры, генератора и артефактов. `oracle.schema.json` описывает формат. `SPEC_NOTES.md` отделяет ограничения oracle от статуса архитектуры.

Корпус включает положительные, отрицательные, пограничные, неоднозначные, неразрешённые, конфликтные и crash/recovery ветви. Матрицы времени вычислены независимо от реализации. Все наборы отрицаний n-ary OR для n=2..6 перечислены полностью. Разнообразие языковых входов опубликовано отдельно от количества механических векторов; замена имени не считается новым механизмом.

## Уровни исполнения

- `pipeline`: raw русский текст → все применимые стадии → IR → AH/TemporalLedger/journal. FAKE провайдер фиксирует разрешённые предложения, но не подменяет T0/T1/T2/validators/C/T5/T6.
- `component`: тест одной реальной границы с явно подготовленным входом; проверяет механизм, не end-to-end покрытие языка.
- `durability`: несколько действий над одним persistent store; crash должен завершать процесс/разрывать durable границу, а recovery — читать заново файл, не сохранённый Python объект.

Нельзя засчитать component case в G3/G4 как полный вертикальный прогон. Нельзя засчитать scripted corpus в G5 как ранее не виденный экспертный holdout. Нельзя объявить PASS наличием oracle либо успешной проверкой его JSON.

## Подключение к проекту

1. Реализуйте adapter `module:function(case, fixtures) -> trace` поверх реальных публичных API проекта. Действия и их payload определены в JSONL; `actions.json` перечисляет поля каждой границы. Адаптер не имеет права читать `steps[].checks`. Конкретное начальное состояние строится из EMPTY + setup actions; все identity links даны fixture явно.
2. Свяжите символы (`ivan`, `N`, `S_or`, `A_not`, …) с реальными Ref/UID через независимый fixture builder. Нельзя объединять сущности по одинаковому имени. Known T должны реально существовать в fixture AH; open T создаёт SUT. Релиз тестовый; это не production reviewed release и не подпись человека.
3. Перед запуском compiler/binder должен получить байты fixture release, frozen context/provider/timing и построить ожидаемые canonical IDs и hash структурных snapshots **независимо от SUT**. Получившийся closed `OracleCase` по §11.2 храните вместе с binding manifest: source document/corpus hash, ah commit, concrete resource hashes, model/params, scripts/timing, UID aliases и expected snapshot hashes. Незаполненный binding — BLOCKED, не PASS. Этот пакет содержит символический исполнимый gold, а не выдуманные UID/sha256 будущего release.
4. Exporter возвращает checkpoint для каждой step (включая setup/crash), без фильтрации лишних фактов/узлов. Формулы — typed JSON AST (`predicate/roles` либо `operator/operands`); structural presence не равно asserted truth. Поля `/assertions/ah`, `/assertions/ir`, `/assertions/journal` перечисляют только фактические утверждения соответствующего канала. Дополнительные факты должны остаться в этих списках и провалить exact set check.
5. Нормализация не меняет semantic identity, polarity, mode, temporal bounds, provenance или outcome. Alias unknown UID экспортируется как `unbound:<uid>`. `state.semantic_digest` — SHA256 canonical semantic state всех записей (AH/TL/опоры/links/markers/D/decisions/отчёты/audit/R-X), с исключением лишь documented volatile timings; значение обязан вычислять exporter. Не используйте SUT ответ вместо digest.

Формат trace: `{schema_version:"v7-oracle-trace-1", case_id, checkpoints:[{step_id, actual:{…}}]}`. Каждая `/path` — JSON Pointer в `actual` данного checkpoint. Missing path — FAIL, даже если expected `null`/пусто/UNKNOWN. `/diagnostics/located_multiset` — пары `(code,location)`; byte-for-byte replay проверяется отдельно, не только по перечню кодов.

```
python tools/build_formalizer_v7_oracle.py --architecture /absolute/path/FORMALIZER_ARCHITECTURE_V7.md
python tools/check_formalizer_v7_oracle.py validate data/formalizer_v7_oracle
python tools/verify_formalizer_v7_oracle_artifacts.py
python tools/check_formalizer_v7_oracle.py run data/formalizer_v7_oracle --adapter my_oracle_adapter:run --out /tmp/actual.jsonl
python tools/check_formalizer_v7_oracle.py compare data/formalizer_v7_oracle /tmp/actual.jsonl --report /tmp/oracle_report.json
```

По умолчанию `compare` требует **все** case IDs; пропуск/дубликат/лишний case, checkpoint или required field — FAIL. Для поднабора используйте `--case` явно: отчёт помечен `PARTIAL`, общий PASS запрещён. В `run` adapter получает копию кейса без checks; verifier хранит gold отдельно. Необслуживаемое действие/отсутствие adapter — BLOCKED/ошибка, не безопасный UNKNOWN, засчитанный как успех.

## Сравнение

`eq` точное typed равенство; `set_eq` одинаковые множества без дубликатов; `multiset_eq` учитывает кратность; `contains` требует все заданные элементы и кратности; `excludes` запрещает typed элементы; `count` проверяет длину; `same_as` сверяет выбранное поле с ранее полученным checkpoint. Недостаточно сравнить лишь естественный язык ответа. Forbidden truth не запрещает структурный операнд той же формулы без опоры. Нет подстрочных проверок вида «слово встретилось в журнале».

Важные негативные ветви: M-only fact, missing source ≠ empty, known mapping failure ≠ open fallback, live ledger ≠ effective witness, two candidate reports в partial APPLIED, отсутствующий D при full reject, request_window не dedup ключ, assertion refs входят в ключ, текущая лицензия R1/R2, историческое решение R0, общий witness ≠ одинаковые bounds, EVENT occurrence ≠ content identity, старые migration supports не оживают.

Пакет не меняет архитектуру/G0–G5 и не содержит результатов запуска проектных тестов. После binding запускайте сначала component, затем persistent durability, затем pipeline. Отчёт должен разделять ошибки реализации, реальную неоднозначность спецификации, непривязанный fixture и языковое покрытие.
'''

SPEC_NOTES='''# Границы и замечания к источнику

1. В приложенном документе есть ссылки на §6.4, но сам раздел/заголовок §6.4 отсутствует. Goal gold взят из действительных §8.3, §17 и DR19/DR20/DR30. Нельзя считать эту проверку восстановлением удалённого нормативного текста. Рекомендуется восстановить единый goal contract и проверить его на этих же векторах; после изменения байтов перепинить document SHA256.
2. Источник прямо устанавливает G0–G5 BLOCKED. Oracle не переносит прежний G0 PASS на этот файл и не создаёт review manifest от имени человека.
3. Реальный signed production resource release/экспертная разметка holdout не приложены. Fixture profiles — условия теста, не подтверждённые ресурсы проекта. Тестовый Ed25519 seed публичен и годится исключительно для fixture trust registry.
4. Произвольные ID/хеши будущих AH/resource snapshots не выдуманы. Символический корпус требует adapter/binder, который фиксирует concrete fixtures до запуска. Это отдельная техническая интеграция, не дополнительное решение семантики.
5. Граница времени в математических векторах — явные замкнутые множества точных fixture-relative координат. Календарный парсер проверяется отдельно; нельзя перенести endpoint convention искусственных векторов на полуоткрытый гражданский день без зафиксированной policy/timezone.
6. Формулировки в §8.2/§7.1 о переиспользовании канонического N читаются с явным mode-контрактом §7.6: STATE общий N; новый EVENT/PROCESS/TRANSITION/UNKNOWN путь — отдельный occurrence. В gold этот приоритет указан; если автор имел в виду другое, это SPEC_GAP, а не повод поменять expected под SUT.
7. В §6.2 осталась фраза о числовых кванторах через `N_LITERAL (M_NUM)`, тогда как §6.3/§17.3 требуют typed `CountLiteral` без UID. Gold использует явную схему §6.3/§17.3; устаревшую строку нужно согласовать перед нормативной заморозкой.
8. Обобщение на практически любой русский текст конечным oracle не доказано. Скриптованные положительные структуры фиксируют один подтверждённый fixture reading; естественная языковая неоднозначность вне этих предпосылок не обязана разрешаться так же. Полнота здесь означает покрытие перечисленных нормативных механик и ветвей, не всех конструкций русского языка.
9. Кейсы с invalid protocol/schema, budgets, migration и crash требуют fault injection на реальной границе. Запись заранее ожидаемого outcome адаптером запрещена. Корпус не предоставляет альтернативную реализацию формализатора.
'''

def generate(architecture):
    OUT.mkdir(parents=True,exist_ok=True)
    source=pathlib.Path(architecture); data=source.read_bytes();text=data.decode('utf-8-sig')
    ids=[c['case_id'] for c in CASES]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate case id')
    for c in CASES:
        if not any(s['checks'] for s in c['steps']):raise ValueError('empty gold '+c['case_id'])
        for m in c['mechanisms']:MECHANISMS[m]['case_ids'].append(c['case_id'])
    missing=[m for m,d in MECHANISMS.items() if not d['case_ids']]
    if missing:raise ValueError('Uncovered mechanisms: '+','.join(missing))
    accepts={f'A{i:02}':sorted(c['case_id'] for c in CASES if f'A{i:02}' in c['acceptance_refs']) for i in range(1,40)}
    drs={f'DR{i}':sorted(c['case_id'] for c in CASES if f'DR{i}' in c['dry_run_refs']) for i in range(1,32)}
    if not all(accepts.values()) or not all(drs.values()):raise ValueError('Missing A/DR coverage')
    from collections import Counter
    texts={s['payload']['raw_input']['text'] for c in CASES for s in c['steps'] if 'raw_input' in s['payload']}
    stats={'cases':len(CASES),'mechanisms':len(MECHANISMS),'acceptance_requirements':len(accepts),'dry_run_requirements':len(drs),'steps':sum(len(c['steps']) for c in CASES),'checks':sum(len(s['checks']) for c in CASES for s in c['steps']),'unique_raw_inputs':len(texts),'cases_by_tier':dict(Counter(c['tier'] for c in CASES)),'language_pattern_families':len(PATTERNS)+len(NF)+8,'time_vectors':len(W),'g5_holdout_claim':False}
    source_map={'document_sha256':sha(data),'byte_count':len(data),'line_count':len(text.splitlines()),'headings':[{'line':n,'title':line.strip()} for n,line in enumerate(text.splitlines(),1) if line.startswith('#')],'missing_referenced_section':['6.4'],'acceptance_lines':{a:next((n for n,line in enumerate(text.splitlines(),1) if line.startswith('|') and a in re.findall(r'\bA\d{2}\b',line.split('|')[1])),None) for a in accepts},'dry_run_lines':{d:next((n for n,line in enumerate(text.splitlines(),1) if re.match(r'^### '+d+r':',line)),None) for d in drs}}
    actions={}
    for c in CASES:
      for s in c['steps']:
       d=actions.setdefault(s['action'],{'payload_fields':set(),'case_ids':[]});d['payload_fields'].update(s['payload']);d['case_ids'].append(c['case_id'])
    actions={k:{'payload_fields':sorted(d['payload_fields']),'case_ids':sorted(set(d['case_ids']))} for k,d in sorted(actions.items())}
    def write(name,obj):
        (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (OUT/'cases.jsonl').write_text(''.join(canonical(c)+'\n' for c in CASES),encoding='utf-8')
    write('fixtures.json',FIXTURES);write('oracle.schema.json',SCHEMA);write('mechanisms.json',MECHANISMS)
    write('coverage.json',{'mechanisms':{m:d['case_ids'] for m,d in MECHANISMS.items()},'acceptance':accepts,'dry_runs':drs,'stats':stats})
    write('source_map.json',source_map);write('actions.json',actions)
    (OUT/'README.md').write_text(README,encoding='utf-8');(OUT/'SPEC_NOTES.md').write_text(SPEC_NOTES,encoding='utf-8')
    md=['# Покрытие oracle\n',f"Кейсов: **{len(CASES)}**. Механизмов: **{len(MECHANISMS)}**. A01–A39 и DR1–DR31 связаны с кейсами.\n",'Это проектные gold-сценарии; результаты исполнения и статусы G0–G5 не утверждаются.\n','| Механизм | Норма | Кейсов | Первые примеры |','|---|---|---:|---|']
    for m,d in MECHANISMS.items():md.append(f"| `{m}` — {d['title']} | {' '.join(d['norm_refs'])} | {len(d['case_ids'])} | {', '.join(d['case_ids'][:4])} |")
    md+=['\n## Acceptance\n','| Требование | Кейсы |','|---|---|']
    md += [f"| {a} | {', '.join(v[:12])}{' …' if len(v)>12 else ''} |" for a,v in accepts.items()]
    md+=['\n## Dry-runs\n','| Трасса | Кейсов | Примеры ветвей |','|---|---:|---|']
    md += [f"| {d} | {len(v)} | {', '.join(v[:6])} |" for d,v in drs.items()]
    (OUT/'COVERAGE.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    artifact_hashes={p.name:sha(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.json'}
    manifest={'schema_version':'v7-oracle-manifest-1','source_document':{'filename':source.name,'sha256':sha(data),'bytes':len(data)},'gold_authoring':'independent normative symbolic fixtures; never SUT-derived','status':'AUTHORED_NOT_EXECUTED','gates':{f'G{i}':'NOT_EVALUATED' for i in range(6)},'requires_adapter_binding':True,'project_commit_reference':'ce80c890f30bf0559da03ea8d8bae4c257647bea','stats':stats,'generator_sha256':sha(pathlib.Path(__file__).read_bytes()),'checker_sha256':sha((ROOT/'tools/check_formalizer_v7_oracle.py').read_bytes()),'artifact_verifier_sha256':sha((ROOT/'tools/verify_formalizer_v7_oracle_artifacts.py').read_bytes()),'artifacts':artifact_hashes}
    write('manifest.json',manifest)
    print(canonical(stats)); print('document_sha256='+sha(data))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--architecture',required=True);generate(parser.parse_args().architecture)
