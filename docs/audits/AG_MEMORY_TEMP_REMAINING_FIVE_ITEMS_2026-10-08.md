# AG_Memory temp: доработка пяти оставшихся направлений

Дата: 2026-10-08. Проверяемая база до изменений: `59fc13ec415809a9b262fd72a0b5ed5594de285a`. Изменены production исходники, зависимости и документация. Тесты не читались, не запускались и не изменялись. Статическая проверка не является доказательством G0–G5 PASS.

## Что изменилось относительно предыдущего отчёта

| Направление | На базе 59fc13e | В этой доработке | Текущий предел |
|---|---|---|---|
| Resource release | Loader/init/check; внешний review pin без crypto | Actual T catalog; build/coverage/sign/check; content-bound coverage и Ed25519 с внешним key registry | Авторские lexicon, corpus и reviewer key не предоставлены; production release не изготовлен |
| Структурная композиция | JSON AST, multi-token anchors, TimeLiteral, атомарный WH/COUNT, positive EXISTS join | Текстовый DSL; схемы каждого зарегистрированного Emit; numeric operators/CountLiteral; full-scope WH/COUNT и nested EXISTS; временные proposition operands | Покрытие surfaces не измерено; arbitrary counterfactual/causal, lexical restrictions и агрегатный count по окну требуют дальнейших контрактов/данных |
| R-X | Stage-isolated cache и frozen reads | Индекс snapshot+R1 lexical keys, bounded retrieval, counters/timings, actual-snapshot profile CLI | На большой production памяти измерений нет; semantic benefit требует контролируемого корпусного сравнения |
| Boundary | Поддержанный JSON и review-атрибуция | Закрытые JSON Schema, semantic/cross-record validation, Ed25519 verify/revocation/exact pin | Это граница зарегистрированного runtime; отложенные/неизвестные resource kinds отклоняются |
| Migration/identity | Одна declared replacement и host bindings | Durable mass plan, version reservations, resumable per-source receipts; CorefPolicy resolver по declared frozen window с grounded selector | Не автоматическое слияние имён; event identity/report bridging выключены; миграционные corpus runs не выполнены |

## 1. Ресурсные данные и реальные T

**Недочёт.** Отсутствовали реальный reviewed release и coverage report. Нельзя заменить их демонстрационным словарём либо назначить смыслы по названию существующего T.

**Как исполнено сейчас.** `resources.authoring` экспортирует реальные T/roles текущего AH snapshot, собирает авторские контейнеры и проверяет каждый TemplateMap против существующего T и точного набора ролей. `coverage` читает фиксированный корпус `{corpus_id,units:[{unit_id,text}]}`, вычисляет его byte SHA256 и реальные R1 token spans, категории доступности R-S/R-V/TemplateMap. Coverage привязан к `resource_content_sha256`; после присоединения coverage финальный reviewed hash покрывает и данные, и отчёт. `sign` использует только предоставленный приватный Ed25519 key. `check` в production требует внешний trust registry и реальный AH snapshot. FormalizerAdapter повторяет проверку TemplateMap при подключении.

**Как должно быть.** Владелец данных предоставляет подготовленные lexicon/valencies/mappings, фиксированный корпус, корректный AH snapshot и доверенную reviewer атрибуцию/ключ. Независимый reviewer подписывает конкретный release. G2/G5 подтверждаются отдельными доказательствами, а не самим наличием CLI.

**Причина.** Наполнение ресурсов — содержательные данные и человеческое решение о смысле; криптографическая подпись доказывает авторство конкретных байтов, но не языковую правильность словаря.

**Состояние:** код инструментов подключён; внешний production release **BLOCKED**. Реальных coverage значений и подписей в этой работе не создавалось.

## 2. Production-композиция и query scope (I04/I20/I34/I38, A06/A07)

**Недочёт.** JSON SyntaxRules не замыкал недоопределённый BNF. Numeric scope не имел полного operand codec и reader; составной query slot либо отбрасывался, либо рисковал стать вопросом только к одному предикату.

**Как исполнено сейчас.**

- §16 задаёт однозначную текстовую форму captures/reads/when/Emit JSON. `rule_dsl` компилирует её в существующий AST без eval; версии reads обязаны совпадать с manifest. CandidateSchema пинит закрытые схемы всех четырёх зарегистрированных Emit; далее проверяются typed graph/role/arity/cycle/anchor constraints.
- Multi-token anchors, explicit heads и R-S anchor_pattern сохранены; numeric NUMERAL несёт только raw anchors. Значение определяется цифрами либо reviewed NumeralRules. FunctionRegistry, native plan, codec и persistence поддерживают `[entity BoundVar, body Ref(N|G), CountLiteral]` для AT_LEAST_N/EXACTLY_N/AT_MOST_N. Не создаются n вымышленных объектов.
- CountGoal объединяет distinct-M witnesses и asserted bounds **совпадающего полного атомарного body**. Ограничение/restriction не удаляется для расширения совпадений. Exact count и proof AT_MOST_N требуют scoped completeness. ENUMERATED и ASSERTED_BOUND closure различены.
- Query gap имеет уникального владельца внутри полного дерева. NativeBindingGoal получает кандидатов по narrow template indexes, подставляет runtime QueryVar и доказывает всё дерево. Результат WH не утверждает отдельную ветку OR/QUOTE. Составной COUNT требует FormulaDomainCertificate по typed pattern signature, variable, window и живым completeness supports. Без него публикуется лишь нижняя граница.
- Nested EXISTS использует capture-safe substitution в полное body; NOT/OR/AND и другие scopes сохраняются. Перебор не выводит FORALL; отсутствие свидетеля — UNKNOWN. Незавершённый бюджетом поиск не становится «полным».
- BEFORE/AFTER/DURING принимают TimeLiteral или proposition Ref. Прямой ordering root не утверждает children. Inferred BEFORE требует живых временных evidence с max(A)<min(B); DURING — гарантированного покрытия. EXISTENTIAL не становится CONTINUOUS. Не найденная event pair не опровергает открытый relation.

**Как должно быть.** Общие механизмы должны выдержать oracle/DR и unseen corpus без patch по примеру. Topic/type restrictions остаются в body; cardinality, державшаяся в неизвестный момент Q, не должна превращаться в число разных событий за весь Q.

**Причина.** Сохранённое дерево и выполненный proof contract устраняют преждевременный отсев интерпретаций. Они не заменяют ресурсные данные и доказательство реального покрытия.

**Состояние:** перечисленные source paths подключены; поведение не проверено тестами. **Осталось:** контрфактический proof с фильтрацией native paths по временным assumptions; недостающие causal/superlative/manner/прочие handlers; полноценная лексическая типизация и чтение произвольного restricted count body; отдельная declared aggregate CountDomain по временному окну. Неизвестные формы дают typed UNKNOWN. Полный G5 не заявлен.

## 3. R-X опыт: чтение, польза и стоимость

**Недочёт.** Canonical записи опыта уже существовали, но чтение и полезность на большой памяти не были измерены.

**Как исполнено сейчас.** ExperienceIndex — заменяемая проекция по snapshot+surface/lemma. Ключи текущего запроса включают все R1 lemmas, не выбранный «первый» parse. Immutable R-X payload позволяет обновлять индекс только при добавлении записей; status transitions проверяются в момент чтения. Retrieval ограничен limit: переполнение → пустые optional priors + RX_PRIOR_LIMIT, не произвольный удачный префикс. Read payload и diagnostic фиксируются в canonical run snapshot; replay той же пары не читает новый опыт. `experience_metrics()` и `profile-rx` показывают records indexed/considered/returned/stale, бюджет, index/lookup/liveness time и payload bytes. Offline profile читает фактический snapshot и корпус, не генерирует память и не пишет AH.

**Как должно быть.** На реальных больших snapshot провести profile по фиксированному корпусу. Пользу измерить отдельно: одинаковые исходные память/ресурсы/входы/budgets, контролируемый selector replay, прогон с prior и без него; сравнить unresolved/coverage/selector calls/cost и отсутствие false commits. Метрики retrieval не подменяют semantic benefit.

**Причина.** Индекс сужает retrieval, но `ledger.paths()` и snapshot-WAL могут по-прежнему иметь стоимость от всей памяти. Отдельный liveness counter делает этот предел видимым.

**Состояние:** механизм индекса/измерения реализован; значения большой памяти и semantic benefit **не измерены** — нужных production данных нет.

## 4. Release boundary и доверие

**Недочёт.** Внешнее совпадение review-записи не являлось криптографической проверкой подписи; произвольные resource fields не имели единой закрытой схемы.

**Как исполнено сейчас.** `resources.schemas` проверяет все зарегистрированные resource record kinds и Emit schemas посредством JSON Schema 2020-12. Semantic validator проверяет IDs, roles, sense refs, dependencies, duplicate keys, cycles, policy limits, compiled AST и actual AH mappings. Unknown kind/variant — RESOURCE_MISSING. CandidateSchema не может ослабить обязательную схему Emit и не загружает внешние JSON refs. `signatures.verify_review` сверяет exact release pin, key_id→reviewer, revocation, key/signature size и Ed25519 signature над review envelope, привязанным к full content+coverage hash. Доверенный публичный key registry хранится вне release. Старый bare attribution registry требуется перевыпустить; silent downgrade на pin-only отсутствует.

**Как должно быть.** Operator получает trust registry независимым каналом; reviewer key хранится и отзывается по принятой модели доверия. Криптография и validation проверяются пользовательскими тестами; подпись не объявляется доказательством качества смысла.

**Причина.** Данные релиза не могут сами сделать свой ключ доверенным. «Поддержан runtime формат» также не означает исполнение отключённых EventIdentityRule/ReportBridgingRule и любого будущего ресурса.

**Состояние:** поддержанная runtime boundary усилена; полного поведенческого/криптографического аудита в этой работе не было.

## 5. Массовые миграции и grounded reference linking

**Недочёт.** Per-source replacement не составляла общей resumable job; identity опиралась главным образом на host bindings.

**Как исполнено сейчас.** `plan_mass_migration` фиксирует source set, input hashes, target versions и run IDs в MIGRATION_PLANNED. `InterpretationRunBinding` резервирует эти версии за job. `resume_mass_migration` использует отдельный job mutex, не удерживает общий AH lock при provider calls и пишет неизменяемые per-source MIGRATION_ITEM_RESULT. Crash до receipt повторяет тот же canonical run/marker. Atomicity — на каждую замену; отказ не отзывает предыдущие факты. LinkOpenTemplate требует explicit source/target T refs, reviewed mapping и живые evidence IDs; он остаётся audit relation, не reasoner alias.

CorefPolicy resolver читает только declared observation window и прежние совместимые entity arguments. Snapshot candidate paths фиксируется до run binding. Hard morphology conflicts отсекаются с trace; missing feature не является конфликтом. Ранжирование лишь упорядочивает, KEEP_ALL ties сохраняет альтернативы. Выбор одного кандидата имеет D/P/M interpretation grounds (не truth ground текущего факта) и concrete antecedent support IDs; отзыв основания инвалидирует binding обычным каскадом. Speaker/addressee Ref берётся только из явного context. Одинаковое имя не запускает merge. Event identity/report bridging не включены.

**Как должно быть.** Вызывающая сторона предоставляет explicit source/context windows и declared migration trigger; после новой версии ресурса запускает нужный job. Независимые изменения контекста требуют нового declared plan. Зависимые источники не переинтерпретируются самопроизвольно. Event identity требует отдельного registered proof contract, а не lexical equality.

**Причина.** Миграция связывает интерпретации и аудиторный след, но не может угадать семантическое тождество новых терминов или сущностей.

**Состояние:** entity linking и mass workflow подключены; production runs/качество данных не измерены. Общее event identity остаётся намеренно выключенным.

## Проверка этой доработки

Python source compilation; импорт новых production модулей после установки объявленных зависимостей; JSON Schema meta-validation всех зарегистрированных схем; сверка call sites, typed operands и manifest boundaries; `git diff --check`. Проверены структура разделов архитектуры и сохранность A01–A39/DR1–DR31. Это не crash/race/oracle/corpus test.

Архитектура обновлена под исполнимый DSL, numeric operands, full-scope query goals, temporal proposition operands, signed release и declared migration/reference contracts. **G0 BLOCKED**: нормативные байты изменились, старый манифест не подписывает текущий текст. G1–G5 остаются BLOCKED без требуемых доказательств.
