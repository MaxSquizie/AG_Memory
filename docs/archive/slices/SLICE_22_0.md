# Срез v0.22.0 — нормативный GC, полный DSL и системный preflight

## 1. Цель среза

Версия 0.22.0 закрывает системные обязательства архитектуры v4 перед отдельной фазой hackathon acceptance. Срез не добавляет новую когнитивную семантику и не меняет уже реализованные `IS-A`, `FOLLOW`, `CAUSE`, GoalSpec, inference, association или Context Projector.

Закрываются три связанные границы:

1. общий `initial lifetime → structural support check → physical GC`, существующий независимо от дополнительного lifecycle `N: NEW → REINFORCED → CONSOLIDATED`;
2. полный нормативный DSL/API surface из постановки хакатона;
3. детерминированный structural preflight, который позволяет перед M1–M5 проверить обязательные инварианты и пять фиксируемых гиперпараметров.

Архитектурное основание — разделы 32, 39–41 v4 и обязательные Senior/Hard requirements постановки.

---

## 2. Два разных lifecycle-механизма

0.22.0 сохраняет ранее существующий `LifecycleManager` для N:

```text
NEW
→ REINFORCED
→ CONSOLIDATED
```

Он не заменяет нормативный GC.

После дополнительной регрессии зафиксирован принципиальный контракт: его TTL не
может сам по себе физически удалить структурно живой факт. Истечение локального
N-lifecycle лишь делает N кандидатом на общую проверку забывания. Physical deletion
всегда проходит общий structural GC contract.

Также обычный retrieval/proof focus не должен ретроактивно создавать NEW-state:

```text
QUERY_RECALL / association focus / proof focus
!=
NEW_FACT
```

Если у N ещё нет lifecycle-state, он входит в `NEW` только по явному `NEW_FACT`
seed от интеграции нового знания. Это не позволяет M2/Recall превращать ранее
существовавшие propositions в «свежие факты с новым сроком забывания».

Общий физический lifecycle теперь существует отдельно:

```text
canonical insertion after Ignition start
→ technical birth tick
→ initial lifetime
→ effective structural support check
→ live / protected
   OR
→ lost / detached
→ physical deletion
```

`birth tick` — техническое runtime/persistence metadata. Оно не становится `Pr/Mt` у S/T/g/L и не расширяет canonical `q`.

---

## 3. Почему старый граф не считается «только что созданным»

Ключевой compatibility-инвариант:

```text
AH existed before IgnitionEngine start
!=
newly injected runtime element
```

Иначе запуск движка над существующей большой памятью через `initial_lifetime_ticks` начал бы ретроактивно считать всю старую AH новым мусором. Это ломало бы обычную работу и acceptance M2 на dirty ~150k UID.

Поэтому store имеет технический флаг lifetime tracking:

- до старта Ignition существующие элементы считаются установленным snapshot;
- Ignition включает tracking;
- все последующие S/C/P/H insertion автоматически получают managed birth tick;
- persisted managed UID сохраняет остаток initial lifetime после restart.

Комитетские M3 injections через runtime API происходят после запуска Ignition, поэтому автоматически попадают под нормативный GC.

---

## 4. Effective topology для GC

GC не использует `x`, relevance или proof как истину. Он анализирует каноническую поддерживающую структуру через rebuildable indexes.

Effective weighted edges:

```text
L(source,target), если L.w > 0
N ↔ template/actants, если N.w > 0
```

Structural edges без собственного `w`:

```text
T ↔ S(predicate)
g ↔ operands
k ↔ members
```

Для проверки компоненты направление игнорируется: вопрос GC — существует ли поддерживающий путь к сенсорной базе, а не следует ли логическое отношение в обратную сторону.

Это не меняет логическую направленность `IS-A/FOLLOW/CAUSE` и не влияет на inference.

---

## 5. Условие anchored-to-S

После initial lifetime detached component может быть удалён, если у него нет эффективного соединения с S.

При этом одиночный S не считается самодостаточным вечным anchor:

```text
S alone
→ protected during initial lifetime
→ after TTL: lost
```

Иначе `addAbstractSymbol` создавал бы бессмертные несвязанные символы, что противоречит смыслу первоначального времени жизни из монографии.

S, реально соединённый с T/L/другой эффективной структурой, является anchor компоненты.

### Initial lifetime — иммунитет, а не TTL знания

Значение, например:

```text
initial_lifetime_ticks = 40
```

означает:

```text
age < 40
→ GC не имеет права удалять элемент

age >= 40
→ GC имеет право проверить structural support
→ S-anchored/live: сохранить
→ detached/lost: удалить
```

Поэтому нормальный факт не исчезает на 40-м тике только потому, что ему исполнилось
40 тиков. Этот параметр защищает ещё не достроенную новую структуру и одновременно
даёт M3 возможность гарантированно собрать реально изолированные injections в пределах
50 тиков.

---

## 6. Активация не превращена в критерий истины или забывания

Сохранён v4-инвариант:

```text
activation != truth
inactivity alone != delete
```

Если detached component прямо сейчас имеет ненулевое возбуждение, GC не удаляет его в середине текущего когнитивного процесса. Компонента получает отсрочку и проверяется позже.

Холодный искусственно внедрённый orphan такой защиты не получает.

---

## 7. Изменение топологии после удаления

Удаление одного узла может сделать старый соседний компонент orphan уже после того, как его собственный первоначальный TTL когда-то прошёл.

Поэтому GC сохраняет соседей удаляемого фрагмента и планирует их повторную structural-check. Это предотвращает ситуацию:

```text
A was anchored through B
B deleted
A stays forever only because A's original TTL event already happened
```

---

## 8. Referential closure

Перед physical deletion проверяется, что target не остаётся referenced из surviving canonical structure.

Detached component удаляется целиком. Для одиночного lifecycle-кандидата внешний structural referrer защищает его.

Incident `L` удаляются вместе с удалённым endpoint через единственный canonical store deletion primitive.

Derived indexes после deletion rebuild-ятся из canonical state.

---

## 9. Proof-support invalidation

Перед удалением UID:

```text
invalidate supports that use UID as premise
remove support records owned by deleted conclusion
```

Если surviving conclusion имеет независимый support, он остаётся допустимым.

GC не реализует рекурсивный «удалить всё доказанное» shortcut. Conclusion, потерявшее последний support, далее живёт по обычным lifecycle/GC правилам.

---

## 10. Persistence initial lifetime

В `store_metadata`, то есть вне canonical AH, сохраняются:

```text
lifetime_clock_tick
lifetime_birth_tick[uid]
lifetime_managed_uids
```

При reload:

- canonical AH загружается независимо;
- технические lifetime metadata восстанавливаются;
- Ignition snapshot возвращает tick index;
- GC перестраивает heap;
- новый полный initial lifetime не выдаётся заново.

Старые schema-1 dumps без этих optional metadata остаются совместимыми: существующие элементы загружаются как established snapshot и не удаляются немедленно.

Canonical schema version не повышалась, потому что формат самих S/C/P/H/L не изменён.

---

## 11. Внешний audit, а не H

`GCResult` теперь несёт детерминированную причину удаления, например:

```text
LIFECYCLE_SUPPORT_EXPIRED
DETACHED_FROM_S
ZERO_WEIGHT_LOST
INCIDENT_TO_DELETED_ENDPOINT
```

Scheduled runtime через `IgnitionClock` отправляет deletion/lifecycle events в `SessionLogger`.

Это diagnostic/audit channel. Никаких `GC deleted ...` событий в canonical H не создаётся.

---

## 12. Полный нормативный DSL surface

`DSLInterpreter.NORMATIVE_OPERATIONS` фиксирует полный surface из постановки:

```text
addAbstractSymbol
editAbstractSymbol
addElement
editElement
addProperty
editProperty
addLink
getAbstractSymbol
findAbstractSymbols
getSReference
findSReferences
getMReference
findMReferences
getSymbol
findSymbols
getList
findLists
getTemplate
getHypernode
findHypernodes
findRoles
getLink
findLinks
```

Итого: 23 операции.

Helper stages (`where`, `refs`, `unique`) не выдаются за нормативные операции; они только обеспечивают композицию результатов.

---

## 13. editElement

До 0.22 часть textual DSL `editElement` была уже, но имела слишком узкий shape. Теперь через AH Core покрываются:

```text
m  → name / Pr replacements
T  → monotonic role expansion
N  → weight / actant edits с повторной validation
g  → function/operands с FunctionRegistry validation
k  → members с reference validation
L  → weight, без изменения relation/endpoints
```

`T.predicate` и `L` endpoints/relation не переписываются скрыто: сохраняются действующие canonical invariants.

---

## 14. DSL composition

Сохраняется pipeline:

```text
findRoles role=LOCATION value=@M_X domain=H
| findLists domain=H
| where meta.TYPE=Episode
```

Каждый stage получает typed result предыдущего. DSL не имеет отдельной памяти и не обходит AH Core при mutation.

---

## 15. HackathonPreflightInspector

Добавлен deterministic read-only preflight.

Он проверяет:

- размер S;
- размер `C∪P∪H + L`;
- полный normative DSL manifest;
- непустой `R_text` каждого S;
- корректность прямых UID/reference kind;
- ацикличность `IS-A`;
- ацикличность `FOLLOW` внутри H;
- наличие ровно пяти обязательных hyperparameter records.

Scale flags (`>=150 S`, `>=1000 C/P/H+L`) показываются отдельно: пустой dev graph может быть структурно корректен, но ещё не подготовлен как финальный corpus dump.

Preflight не вычисляет M1–M5 и не называется acceptance.

---

## 16. Ровно пять гиперпараметров постановки

Preflight формирует пять top-level records:

1. `initial_lifetime` — `lifecycle.initial_lifetime_ticks`;
2. `decay_g` — выбранная функция decay и её коэффициенты;
3. `workspace_threshold_t` — `workspace.threshold`;
4. `weight_update_h` — Hebbian function + increment/decrement/floor;
5. `rhythm_frequency_nu` — `ignition.nu`.

Внутренние коэффициенты `g/h` не ошибочно считаются шестым, седьмым и т. д. гиперпараметром: они являются параметрами соответствующей обязательной функции.

---

## 17. CLI

Добавлена команда:

```bash
python -m ah.cli --config config/default.toml preflight
```

Она печатает JSON structural report и возвращает ненулевой exit code только при нарушении структурных invariant-ов. Недобор corpus scale показывается отдельными flags и не смешивается с поломкой самой архитектуры.

---

## 18. Регрессионные случаи 0.22

Добавлены проверки:

- 200 cold isolated runtime nodes удаляются в пределах 50 ticks;
- S-anchored live subgraph сохраняется;
- connected node переживает initial lifetime: возраст сам по себе не является delete condition;
- `QUERY_RECALL` не создаёт `NEW` lifecycle-state у ранее существующего N;
- истёкший `NEW` N, остающийся в S-anchored effective component, не удаляется timer-ом;
- detached subgraph с положительным внутренним L удаляется целиком;
- incident L удаляется вместе с endpoints;
- lone S живёт initial lifetime и затем удаляется;
- lifetime birth/managed state переживает persistence и не сбрасывает TTL;
- old pre-Ignition dirty graph не ретроактивно маркируется новым;
- весь normative DSL manifest присутствует;
- каждая query operation исполняется на реальной canonical AH;
- `editElement` покрывает ключевые canonical kinds;
- preflight возвращает ровно пять hyperparameters;
- preflight обнаруживает IS-A и H/FOLLOW cycles.

Итоговая регрессия перед выпуском:

```text
python -m compileall -q src
OK

pytest -q
707 passed, 38 subtests passed
```

Отдельно повторён тяжёлый M2 regression с dirty AH не менее 150k UID:

```text
40/40 cases PASS
pytest case: 7.14 s в текущем контейнере
```

Это именно внутренний regression, не комитетская M2-метрика.

---

## 19. Производительность tick

Отдельный локальный smoke benchmark на 1000 canonical elements (не комитетский reference stand, поэтому не официальный M/acceptance результат) после 0.22 дал порядок единиц миллисекунд на synchronous tick в текущем контейнере; hard requirement постановки остаётся `<=500 ms` и должен быть повторён на референсном стенде.

Этот smoke benchmark не записывается как итоговая метрика хакатона.

---

## 20. Что 0.22.0 намеренно не делает

0.22.0 не запускает и не объявляет пройденными:

```text
M1 role F1
M2 committee 20-question metric
M3 committee injection on reference harness
M4 RAG comparison
M5 SLM vs commercial model experiment
full 15k-word corpus final run
reference-hardware tick benchmark
```

Это следующая фаза — acceptance/measurement, а не новая архитектурная подсистема.

Также не добавляются bonus-направления из раздела 11 монографии и не меняются три OPEN-вопроса v4.

---

## 21. Итог среза

После 0.22 основной архитектурный путь выглядит так:

```text
text
→ deterministic-first formalization
→ CandidateIR / consolidation
→ MutationPlan / atomic AH commit
→ initial-lifetime registration
→ Ignition / Workspace
→ GoalSpec / inference OR association
→ Context Projector
→ Main LLM
→ H experience

parallel maintenance:
N consolidation lifecycle
+
general structural GC
+
persistence/audit
```

Следующий этап проекта — не ещё один крупный semantic slice, а систематический acceptance по постановке и исправление только тех архитектурных/реализационных разрывов, которые обнаружатся измерениями.
