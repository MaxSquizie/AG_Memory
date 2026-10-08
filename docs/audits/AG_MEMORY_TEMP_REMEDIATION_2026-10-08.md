# AG_Memory / temp — проверка исполнения аудита и остаток

**Дата:** 2026-10-08. **Исходный аудит:** `6f50c5f2cf2379359b6b13a662116a67658669f3`. **Прочитанный temp до этой работы:** `63790a6a71c59b6bec94da675df0249b87502fa6`.

**Проверенная реализация:** `cd8ac931864005c1ff67f2a83ebe28ff7021617e` в `temp`. **Предыдущая реализация и отчёт:** `2bba520bc136c62c8580c955d876e0a1c3636e5e`. Нормативный файл и его SHA256 между этими коммитами не изменялись.

Проверялись исходный код, архитектура и документы. **Тесты не читались, не анализировались, не запускались и не изменялись.** Проверка синтаксиса Python и импортов не является проверкой поведения. «КОД» ниже означает внесённую реализацию и статическую сверку, а не доказательство PASS.

## Что изменилось относительно предыдущего отчёта

В предыдущей редакции было 43 карточки. В последнем проходе обновлены **6 прежних карточек**, добавлены **7 новых**, а **37 карточек сохранили состояние предыдущего прохода**. Всего теперь 50. Рост реестра сам по себе не означает закрытие недочётов. Ниже отдельно показаны изменения реализации и оставшиеся границы; это сравнение именно `2bba520 → cd8ac93`.

### Изменения по прежним находкам

| Находка | Как было в предыдущем коммите | Как исполнено в `cd8ac93` | Что осталось |
|---|---|---|---|
| I02 — вопрос и логический scope | Запрет записи вопроса был внесён; составной query scope заканчивался `QUERY_SCOPE_NOT_COMPILED`. | Sealed question tree передаётся native compiler; сохраняются операторы и локальная временная область вместо сведения к leaf EXISTS. | Неподдержанные виды целей возвращают UNKNOWN. Полное покрытие специальных целей отсутствует. |
| I04 — общий структурный путь | Released JSON SyntaxRules уже работал; многословные anchors и TIME/QUERY_SLOT оставались в остатке. | Добавлены многословные lexical units с явным head, released `anchor_pattern`, TIME_SCOPE и QUERY_SLOT. Исходные токены и spans сохраняются. | Текстовый DSL/all CandidateSchema, полная реконструкция эллипсиса, числовые и CAUSAL scope. |
| I20 — типизированное дерево операторов | SOM и составные proposition-аргументы были подключены; временные anchors BEFORE/AFTER/DURING — неполностью. | `TimeLiteral` проходит план, writer, persistence и runtime comparison; временные операнды не получают proposition UsageLink. | Numeric scope и все поверхности GoalSpec ещё не замкнуты. |
| I34 — доказательная видимость запросов | Concrete proof/time reader работал; составные query surfaces оставались неполными. | Подключены native formula/WH/COUNT с чтением живых путей и времени; COUNT различает нижнюю границу и доказанный точный результат. | Counterfactual overlay, произвольные WH под несколькими операторами и другие специальные цели. |
| I38 — кванторы в запросах | FORALL/EXISTS сохранялись при записи; runtime projection не компилировала все quantified goals. | Native query сохраняет квантор; поддержаны чтение явных корней и ограниченный поиск положительного EXISTS-свидетеля. | General nested quantifier/WH joins. Универсальность не доказывается конечным перебором примеров. |
| A04 — переход open→known | OPEN/UNLINKED сохранялся; declared reinterpretation workflow оставался незавершённым. | Добавлен `reinterpret_observation`: frozen input под v+1, declared trigger/release, атомарная замена старой версии и audit-link open→known. | Общая identity/CorefPolicy и получение подтверждённых sense equivalences. Audit-link сам по себе не является alias. |

### Новые находки и результат последнего прохода

| Находка | Внесённое исправление или текущий исход | Статус на уровне исходников |
|---|---|---|
| I39 — положительное P могло доказывать NOT(P) | Reader отрицания использует собственный proof path; общий conflict key не подменяет доказательство. Исправлена полярность вложенного NOT. | Исправление внесено. |
| I40 — прежняя версия отзывалась до успешной замены | Retirement и replacement входят в одну store/WAL-границу; полный отказ сохраняет старую версию. | Исправление внесено. |
| I41 — повторный отзыв переписывал терминальный статус | Source-wide retraction/supersede изменяют только LIVE записи, сохраняя прежний терминальный исход. | Исправление внесено. |
| I42 — counterfactual читает мировой proof без фильтрации | Compiler выдаёт `COUNTERFACTUAL_NATIVE_SCOPE_NOT_IMPLEMENTED`. Hypothetical proof overlay не реализован. | Не завершено; внесён явный отказ. |
| I43 — COUNT без доказательства полноты | Добавлены CountGoal и scoped DomainCertificate с конкретными живыми источниками полноты; без сертификата — нижняя граница/UNKNOWN. | Механизм внесён; реальные reviewed данные отсутствуют. |
| A06 — неисполняемая BNF полезной нагрузки Emit | Выявлено отсутствие нормативных capture/output productions. Исполняется JSON AST; нормативная грамматика требует доработки. | SPEC_GAP остаётся открытым. |
| A07 — numeric scope и общий identity resolver | Entity-count и host bindings поддержаны; это не закрывает AT_LEAST_N/EXACTLY_N/AT_MOST_N и общую CorefPolicy. | Не завершено. |

Основание этих различий — diff исходников и точки вызова: `native_queries.py` → `association_session_goal.py`, `temporal_order.py`/`TimeLiteral` → plan/persistence, `migration.py` → `ah_adapter.commit_transaction`, `canonical_ledger.query_proposition/retract/supersede`. Проверка поведения отложена по указанию пользователя.

## Что было сделано между аудитом и началом этой работы

На temp уже находились семь коммитов: удаление legacy adaptive stack (`955f602`), typed mutation/support corrections (`c5f70fe`), запрет пустых goal premises (`2ad63e1`), V7 runner/seam (`19ce737`, `d113f6d`), полный PerceptionResult (`774ede8`) и переключение agent loop (`63790a6`). Они закрывали части I01/I02/I19/I25, но оставляли demo candidate pipeline, legacy graph writer без полного native ledger, неатомарный WAL/recovery и memory-only goal decision. Наличие seam не доказало соответствие всей архитектуре.

## Текущее состояние

Внесены native frontend/plan, CanonicalLedger, COW+WAL AH writer, durable goal channel, строгий journal/provider replay/run binding, support/time/SOM/retraction readers, resource loader и защита от второго legacy fact commit. Добавлены diagnostic-only GATE_PRECHECK и lifecycle integrity validation. Перед публикацией проверены source compilation/imports и diff; G1–G5 не объявляются PASS.

Последующая доработка: native SRL/T2 читает released SyntaxRules через общий JSON AST interpreter вместо preview Python-правил. Whole-variant bindings сохраняются до T3; UNKNOWN не становится отрицательным доказательством; priority только упорядочивает полный поиск; budget exhaustion сохраняет trace и не использует неполный успешный префикс. Типизированный ARGUMENT/ATTITUDE принимает целую пропозицию N/G; SOM материализует её структуру без поддержки истинности содержимого. Явный RawInput request_kind не теряется на factual gate/projection.

Текущий SHA256 архитектуры: `8da66250fe043c0488f1b35af60957ce68fae3ad2b93e1aa4e48c2d67587e580`. **G0 BLOCKED**: прежняя подпись относилась к другому SHA256; новые нормы §7.6 требуют независимой проверки. Это исправляет I36, а не подделывает новую подпись.

## Что ещё не сделано в проверенной реализации

1. **Данные G2:** заполненный reviewed resource release, реальные TemplateMap refs, внешний review record и coverage corpus/report. Без них production выдаёт RESOURCE_MISSING. Новые anchor_pattern, TIME_SCOPE, QUERY_SLOT и certificates требуют версии/hash/review, а не вставки defaults в старый релиз.
2. **DSL/CandidateSchema — SPEC_GAP и реализация:** §16 называет BNF полной, но Emit повторно использует production `fields` для stage/reads/when, не задавая fields полезной нагрузки и объявления captures. Поэтому JSON AST не выдаётся за текстовый BNF parser. Нужна однозначная нормативная грамматика captures/output fields и manifest CandidateSchema всех emit kinds; затем — parser/loader. SRL orthography/ellipsis proposals сохраняются, но полного разрешения всех реконструкций ещё нет.
3. **Специальные цели:** native counterfactual proof должен фильтровать canonical derived paths по runtime assumptions, а не спрашивать старый reasoner о реальном мире; текущий compiler выдаёт COUNTERFACTUAL_NATIVE_SCOPE_NOT_IMPLEMENTED. CAUSAL mapping, произвольные WH под несколькими операторами, general nested quantifier joins и end-to-end AT_LEAST_N/EXACTLY_N/AT_MOST_N scope-reader ещё не завершены. Модальное/IMPLIES утверждение читается, но это не общий вывод его операнда. Неизвестная цель не превращается в EXISTS.
4. **Identity policy:** host bindings с конкретными основаниями поддержаны; общего Resource/CorefPolicy resolver ещё нет. Совпадение имён или написаний не доказывает identity. Без разрешения сущностей cross-observation вывод может честно остаться UNKNOWN.
5. **Проверка:** пользователь отложил тесты. Race/crash/DR/oracle/live-model/unseen corpus не выполнялись. Компиляция, импорты, сверка исходников и diff не валидируют поведение.
6. **Масштабирование:** snapshot-WAL и bounded ledger/index reads требуют измерения на большой памяти. Delta-WAL/checkpoint допускаются только при сохранении атомарности, replay и неизменяемого audit.

В этой работе не создавались фиктивные ресурсы, signatures, corpus coverage или oracle outputs.

## Реестр: Недочёт / Как исполнено сейчас / Как должно быть / Причина

Поле **«Недочёт»** фиксирует исходную проблему карточки; её текущее состояние задают **«Статус»** и **«Как исполнено сейчас»**. Полный реестр сохраняет причины и требования прежнего аудита. Изменения именно последнего прохода вынесены в таблицы выше.

### I01 — Рабочий вход не проходит полный цикл V7

**Статус:** КОД / ДАННЫЕ BLOCKED. **Приоритет исходного аудита:** P0.

**Недочёт.** FormalizerAdapter.parse запускает T0–T4, превращает результат в старый PerceptionResult и передаёт его прежнему IntegrationService. C/T5/T6 и GoalExecutor существуют отдельно. В bootstrap новый адаптер включается флагом AH_FORMALIZER; ошибка его построения допускает возврат к legacy. Наличие модулей не означает, что пользовательский ввод проходит через их проверки.

**Как исполнено сейчас.** Production perception вызывает interpret_full → resource-driven T0/TP/T4 → typed C/T5 → AHStoreAdapter. Legacy parse помечен noncommittable preview; downstream получает receipt и не утверждает те же факты повторно. Без проверенного release и trusted review запуск останавливается явно.

**Как должно быть.** Единственный прослеживаемый production-маршрут: наблюдение → V7 IR → C → T5 → T6 → канонические опоры/свидетельства/маркеры. Legacy-маршрут должен быть явно выбранным режимом, а не незаметной заменой гарантий V7.

**Причина.** Разрыв orchestration: новые механики реализованы преимущественно изолированно. Исправление отдельных helpers не обеспечивает архитектурного контракта на реальном вводе.

**Точки проверки:** bootstrap.py; formalizer/v7_pipeline.py; perception/llm_parser.py; integration/service.py.

### I02 — Отрицание и вопрос превращаются в положительное утверждение

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** При допустимом ответе селектора LIKE ввод «Вороны не любят червей.» даёт положительный AssertionCandidate(любить). «Вороны любят червей?» тоже даёт assertion; SPEECH_ACT_QUERY добавляется лишь как диагностика. Интеграция отрицательного примера действительно записывает положительный N без логической области.

**Как исполнено сейчас.** Query/command не получают root support; NOT материализуется как G(NOT,P), его операнд — SOM без root truth. Legacy assertions из native receipt не проходят второй writer. Sealed native scope передаётся общему query compiler; неподдержанная цель остаётся явным UNKNOWN, а не leaf EXISTS.

**Как должно быть.** NOT должен быть утверждённым G-корнем, P — структурным операндом без truth-support. QUERY не должен создавать asserted-факт о своём содержании. Эти ограничения обязательны на write boundary независимо от ответа селектора.

**Причина.** runtime_adapter строит assertions из выбранных значений без обязательной проверки scope и speech act. Это повреждение смысла записи, а не неполнота словаря.

**Точки проверки:** formalizer/native_plan.py; formalizer/runtime_adapter.py; integration/service.py.

### I03 — Роли и предикат извлекаются по позиции, а не по frame

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** _assign_roles назначает первому номиналу SUBJECT, остальным OBJECT; _build_predicate ищет первый VERB во всём evidence. «Червей любят вороны» получает обратные роли. Две клаузы могут дать повторяющиеся роли и ValueError TemplateCandidate.roles must be unique. Генератор также собирает номиналы предложения без надёжной привязки к конкретному глагольному frame.

**Как исполнено сейчас.** Предикат и роли берутся из конкретного frame, typed TP и совместимого R-V. Позиционный fallback в production удалён. Предложенная роль должна пройти valency validation; неопределённая группа/кардинальность блокирует только зависимый фрагмент.

**Как должно быть.** Переносить в итоговый IR уже разрешённые frame-local роли и якоря; сохранять неоднозначные альтернативы до выбора. Несколько клауз должны независимо замыкаться без потери связи актантов с предикатами.

**Причина.** Повторная эвристическая интерпретация в адаптере обходит CandidateIR и возвращает прежний тупик раннего выбора предиката/ролей.

**Точки проверки:** formalizer/native_frontend.py; formalizer/native_plan.py; formalizer/runtime_adapter.py.

### I04 — Общий структурный и open-lexical путь не подключён к основному pipeline

**Статус:** КОД / ПОКРЫТИЕ ОГРАНИЧЕНО. **Приоритет исходного аудита:** P1.

**Недочёт.** Основной FrameGen ограничен глагольными/копульными ветками; COORD содержит заглушку, есть фиксированная бинарная арность. Встроенная schema содержит демонстрационные V1–V4. TP и open-set helpers не составляют обязательный путь run(). «Мне холодно» возвращает пустой результат без диагностики.

**Как исполнено сейчас.** Native SRL/T2 читает released SyntaxRules capture/predicate AST: все общие predicate operations, целые R1 variants, typed graphs, declared schema lookups, bounded joins и durable trace. Preview callbacks и private morphology correction не участвуют в native. Одинаковые графы объединяют rule provenance, разные пересекающиеся варианты сохраняются до разрешённого выбора. TP до seal вызывается для gaps/ambiguity; дополнительная проверка deterministic frames явно включается policy. OPEN_LEXICAL создаёт occurrence-local UNLINKED T/N без alias. Многословные единицы с explicit head и TIME/QUERY_SLOT подключены. Текстовый BNF/all CandidateSchema, полный numeric/counterfactual/CAUSAL scope остаются PARTIAL; blanket DONE отменено.

**Как должно быть.** До seal исчерпывать общие структурные операции и ограниченный TP, затем пять T3-источников. При нехватке данных выдавать частичное покрытие/BLOCKED/NO_CANDIDATE с причиной. DR21 обязан проходить через тот же entry point, что обычный ввод.

**Причина.** Пока расширение покрытия требует добавления специальных веток и ручного соединения модулей. Это противоречит цели пользователя — расширять данные и композиции, не обработчики предложений.

**Точки проверки:** formalizer/syntax_rules.py; formalizer/native_frontend.py; formalizer/native_plan.py; formalizer/tp_proposer.py; formalizer/resources/loader.py.

### I05 — Теряется идентичность наблюдения и контекст входа

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** В состоянии source_uid вычисляется из текста, версии задаются константами; нет полноценного source_id/revision/range на входе. Делегирование в formalizer_adapter передаёт text без interaction_context. T0 удаляет пунктуацию/кавычки, span токена представлен строкой, а не однозначными смещениями. Одинаковые тексты разных наблюдений и повторные одинаковые слова не различаются надёжно.

**Как исполнено сейчас.** RawInput сохраняет source_id/revision/range, текст, interpretation version, контекст, declared reads и time_anchor. O-ID вычисляется по типизированному hash источника/ревизии/диапазона; token ID и offsets сохраняются. Повтор с изменённым snapshot не выдаёт новую интерпретацию под прежней парой.

**Как должно быть.** Передавать ObservationRecord с идентичностью источника, revision, диапазоном, declared context/timestamp; сохранять исходные offsets и все значимые знаки. Контекст — версионированный вход, а не скрытая глобальная память.

**Причина.** Нельзя надёжно реализовать provenance, отзыв по наблюдению, анафору, цитаты и replay, если вход уже потерял адресность.

**Точки проверки:** formalizer/v7_pipeline.py; formalizer/pipeline.py; perception/llm_parser.py.

### I06 — Исчерпание T3 декларируется без выполнения всех источников

**Статус:** КОД / ПРИОРЫ БЕЗ TRUTH. **Приоритет исходного аудита:** P1.

**Недочёт.** Pipeline передаёт build_source_traces главным образом schema_candidates. Остальные источники по defaults становятся пустыми/неприменимыми; open_path_verified=True по умолчанию. CHECKED_EMPTY может означать отсутствие вызова, а не отрицательный результат реальной проверки.

**Как исполнено сейчас.** Пять источников реально читаются: PredicateSchema/expansion, R-S, released R-X3 prior, declared W/C reads, OPEN policy. Prior/read IDs добавляются до R-V, а не фильтруются уже готовым списком. BLOCKED/незамкнутая валентность не выдают NO_CANDIDATE. Динамический R-X также пишется только вместе с committed root support; stage-isolated reads ограничены живыми/version-matching записями и закреплены в run snapshot. R-X1/2 меняют только порядок полной кандидатной структуры, R-X3 добавляет совместимые известные sense candidates; кэш не становится truth ground.

**Как должно быть.** Терминальный trace каждого применимого источника должен ссылаться на выполненное чтение/проверку, версию ресурса и результат. Не подключённый источник — BLOCKED/NOT_CHECKED, не доказанное исчерпание.

**Причина.** Ложный NO_CANDIDATE маскирует недоделанную интеграцию под отсутствие знаний.

**Точки проверки:** formalizer/native_frontend.py; formalizer/t3_sources.py; formalizer/resources/loader.py.

### I07 — Валидатор TP пропускает недопустимые предложения структуры

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** Принимается hypothesis с пустым anchor_spans, посторонним полем UID и циклическим ARG ребром узла на себя. Декодирование не обеспечивает весь контракт whitelist/sort/alignment/структурных ограничений.

**Как исполнено сейчас.** TP проверяет whitelist полей/видов/ролей, непустые anchors внутри собственного alignment, typed edges (включая N/G-пропозициональный аргумент), operator arity и [bound_var,body], обязательные scope triggers, cycles/depth/node/edge budgets и закрытую cardinality proposition slot. Тот же validator проверяет resource graph emission. Alternatives, выбор и причины исключения сохраняются в sealed/durable trace; selection protocol запрещает посторонние/пропущенные поля и дубли ID. Неподдержанное чтение не исчезает ради «однозначного» успешного префикса.

**Как должно быть.** До принятия TP отклонять неизвестные поля, неякорённые узлы и запрещённые циклы; проверять типы слотов, границы, морфологическую совместимость и бюджеты. Разрешённые виды циклов, если нужны, перечислить отдельно.

**Причина.** Модель получает возможность обходить формальную границу допустимого предложения. Bounded proposal без строгой валидации не является проверенной структурой.

**Точки проверки:** formalizer/tp_proposer.py; formalizer/native_frontend.py.

### I08 — Контекстная роль союза решается по одному слову

**Статус:** КОД. **Приоритет исходного аудита:** P2.

**Недочёт.** TagSource вызывает subord_probe(word) и кэширует ответ по слову. «пока» в «пока он спит» и «пока всё спокойно» получает один результат независимо от окружающей структуры; текст предложения в probe не передаётся.

**Как исполнено сейчас.** Subordinator probe получает слово, контекст и диапазон; cache key включает эти входы. Production clause boundaries дополнительно привязаны к release ScopeLexicon.

**Как должно быть.** Контекстное решение должно получать предложение/диапазон и версии evidence; кэшировать по этому входу. Словарное свойство и роль конкретного употребления должны быть разными сущностями.

**Причина.** Проблема не устраняется расширением pymorphy-словаря: один лексический элемент допускает разные синтаксические функции.

**Точки проверки:** formalizer/tag_source.py; formalizer/native_frontend.py.

### I09 — Нет полного загрузчика подписанного resource release

**Статус:** КОД / G2 BLOCKED. **Приоритет исходного аудита:** P1.

**Недочёт.** Есть registry и флаги released, но не найден исполняемый общий контракт проверки reviewed_sha256 канонического манифеста, транзитивного dependency_versions и загрузки согласованного snapshot. IMPLEMENTATION_MAP_V7 помечает signed release DONE.

**Как исполнено сейчас.** Добавлен загрузчик versioned manifest, хеша содержимого и coverage report, dependency closure/cycles, sense/role/mapping/policy references и внешне закреплённой review-атрибуции. SyntaxRules обязателен, AST/typed outputs валидируются до использования. Manifest копируется в каноническом порядке; его неизменность проверяется на native/C boundary. CLI создаёт только unsigned draft. Это pinned review record, не криптографическая проверка подписи; полный CandidateSchema всех §2.1 и фактический подписанный release ещё требуют G2.

**Как должно быть.** Загрузчик должен проверять версию схемы, содержимое и хеш релиза, review-атрибуцию, ссылки и транзитивные зависимости; pipeline должен фиксировать этот snapshot. До этого статус механики PARTIAL/BLOCKED, независимо от размера словаря.

**Причина.** Булево released не доказывает происхождение и воспроизводимость ресурсов. Отсутствие релиза G2 само по себе честно заявлено, но DONE механизма не подтверждён.

**Точки проверки:** formalizer/resources/loader.py; formalizer/resources/release_cli.py; bootstrap.py.

### I10 — EVENT identity сталкивается между наблюдениями

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** C-consolidation добавляет fragment_id к event-ключу, но не observation/version. Независимые O1/F1 и O2/F1 с одинаковым содержанием получают один идентификатор N:COME|SUBJECT=M1|COME#F1. Сигнатуры собираются строковой конкатенацией без типизированного кодирования.

**Как исполнено сейчас.** EVENT/PROCESS/TRANSITION/UNKNOWN прямого утверждения имеют observation/version/occurrence key; STATE использует RelationKey. Ключи — каноническая JSON-сериализация. Для derived EVENT определён отдельный occurrence на новый proof path (§7.6).

**Как должно быть.** EVENT/PROCESS occurrence key обязан включать область уникальности наблюдения/вхождения; STATE использует RelationKey. Использовать каноническую типизированную сериализацию, а не неоднозначные разделители.

**Причина.** Локальный F1 не уникален глобально; независимые события и их отзыв могут смешаться.

**Точки проверки:** formalizer/c_consolidate.py; formalizer/native_plan.py; formalizer/goal_channel.py.

### I11 — Identity conflict блокирует не все зависимые фрагменты

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** unify_identity выбирает первого владельца mention через next(). При m→M1 в F1 и m→M2 в F2 заблокирован только F1; конфликтующий F2 остаётся вне blocked_fragments.

**Как исполнено сейчас.** Consolidation блокирует всех owners конфликтующей identity, а native plan откатывает closure заблокированного фрагмента и сохраняет независимые.

**Как должно быть.** Построить множество всех фрагментов, зависящих от неоднозначного binding, и блокировать/пересчитывать весь соответствующий dependency closure.

**Причина.** Результат зависит от порядка перечисления фрагментов; недоказанная идентичность может пройти в AH.

**Точки проверки:** formalizer/c_consolidate.py; formalizer/native_plan.py.

### I12 — T5 принимает interpretation ground как truth ground

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** evaluate_fragment проверяет только непустоту truth_grounds. FragmentT5Input с единственным M успешно committable=True. Флаги integrity/dependencies также принимаются как готовые внешние утверждения.

**Как исполнено сейчас.** evaluate_fragment требует O/C/W для факта; AddRootSupport проверяется на write boundary. M остаётся value-specific interpretation ground и не подменяет прямую опору наблюдения.

**Как должно быть.** На доверенной write boundary валидировать типы и реальные ссылки O/C/W; R/D/M/A/P не могут самостоятельно утверждать факт. Если helper предназначен только для валидированного типа, создать такой тип и обязательного вызывающего валидатора.

**Причина.** Комментарий «только O/C/W» не является исполняемым инвариантом; возможен коммит интерпретации модели как факта.

**Точки проверки:** formalizer/t5_batch.py; formalizer/ah_adapter.py; formalizer/canonical_ledger.py.

### I13 — Batch hash не фиксирует фактически исполняемый план

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** t5_batch._batch_hash хеширует сводные поля фрагментов, не MutationPlan и ресурсный snapshot; known_mapping_missing не входит в payload. commit_stage._batch_hash перечисляет ID frames/лексемы, но не полное семантическое содержимое и операции. Успешная ветка чистого T5 не возвращает полноценную BATCH-запись плана, а production commit не соединяет этот шаг с durable T5.

**Как исполнено сейчас.** Batch hash содержит observation, resource snapshot, structural hash и фактические StoreOps с fragment_refs/deps. Ops digest повторно сверяется с journaled plan; execute другого плана под тем же hash запрещён.

**Как должно быть.** Единый канонический batch_hash должен покрывать нормативный план и зафиксированные входы; T5 сохраняет восстанавливаемый BATCH до T6. Один hash не должен обозначать разные операции или основания.

**Причина.** Идемпотентность по неполному ключу может скрыть другое решение; из сводки невозможно воспроизвести план после сбоя.

**Точки проверки:** formalizer/commit_stage.py; formalizer/ah_adapter.py.

### I14 — Подключённый admission нарушает глобальный head-only контракт

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** t6_core терминально отвергает не-head; commit_stage присваивает новому batch минимальный seq существующих pending, а затем использует tie-break по ID. В R24 не-head получает REJECTED_CONFLICT_ADMISSION и записанный marker. Реального скана несовместимости против AH и восстановления conflict reports через полный D в этом пути нет.

**Как исполнено сейчас.** Не-head batch возвращает PENDING_ADMISSION_ORDER без append/терминального отказа и без AH мутаций. Recovery дренирует pending BATCH по глобальному seq; claim проверяет durable run owner. Конфликт определяется текущим AH на окончательном admission.

**Как должно быть.** Seq выдаёт durable журнал. Не-head → PENDING_ADMISSION_ORDER без записей/маркера. На head — повторная проверка binding/актуальности/конфликтов и фрагментное plan\E; отказ не-head не является конфликтом содержания.

**Причина.** В проекте несколько несовпадающих admission-реализаций, а commit_stage подключён к неверной. Правильный отдельный helper не исправляет рабочую цепь.

**Точки проверки:** formalizer/ah_adapter.py; formalizer/t6_core.py; formalizer/commit_stage.py.

### I15 — STALE_SUPERSEDED записывается после мутации графа

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** commit(..., superseded=True) применяет операции хранилища и лишь затем выбирает терминальный STALE_SUPERSEDED. В журнале уже есть commit, а граф изменён.

**Как исполнено сейчас.** Проверка stale identity premises, существования ссылок и статуса самого ObservationRecord выполняется до применения операций. Ожидающий batch отозванного/superseded наблюдения не создаёт новую root-опору при recovery; write boundary также запрещает опору мёртвого наблюдения. STALE_SUPERSEDED терминален, COW draft не публикуется.

**Как должно быть.** Актуальность плана должна проверяться до любых канонических записей внутри границы admission; STALE_SUPERSEDED означает отсутствие операций AH и маркера этой попытки.

**Причина.** Проверка исхода расположена после эффекта, который должна запрещать.

**Точки проверки:** formalizer/ah_adapter.py.

### I16 — Граф и durable-журнал коммитятся неатомарно

**Статус:** КОД / НЕ ПРОГНАНО. **Приоритет исходного аудита:** P0.

**Недочёт.** AHCanonicalStore.commit_transaction сначала завершает _apply_ops через AHCore.transaction(), затем вызывает journal.append. Инъекция OSError в append оставляет изменённый граф и пустой журнал.

**Как исполнено сейчас.** Writer готовит COW AH; один checksummed canonical_unit с полным AH snapshot, marker/D/proof records fsync-ится до публикации. Это WAL commit boundary: сбой после fsync восстанавливает именно этот снимок. Все native каналы делят одну process-shared lock. Crash-доказательство G1/G4 не запускалось.

**Как должно быть.** План/marker/COMMIT_DECISION и соответствующие audit-записи должны иметь общий доказанный commit boundary либо полноценный WAL-протокол, обеспечивающий нормативную атомарность и replay.

**Причина.** COW-транзакция AH защищает только граф; последовательные операции двух хранилищ не становятся одной транзакцией от названия метода.

**Точки проверки:** formalizer/ah_adapter.py; core/journal.py; core/persistence.py; core/store.py.

### I17 — Recovery сообщает восстановление, но не восстанавливает AH

**Статус:** КОД / НЕ ПРОГНАНО. **Приоритет исходного аудита:** P0.

**Недочёт.** recover_from_head сканирует commit/terminal и возвращает RecoveryReport. Он не проигрывает операции в новом AH, не дописывает недостающий terminal и не восстанавливает _status. Журнал хранит digest, но не весь план и excluded_evidence. После штатного durable commit открытие нового core даёт recovered APPLIED при пустом графе.

**Как исполнено сейчас.** Recovery импортирует фактический AH snapshot с UID, supports, links, assertions, marker/D; из D завершает APPLIED с evidence без повторного admission. Snapshot hash и lifecycle audit проверяются; damaged audit даёт INTEGRITY_ERROR, не ремонт истории.

**Как должно быть.** Восстанавливать каноническое состояние и терминальные исходы из durable источников; при marker+D завершать ровно состоявшееся решение, включая кандидатов/отчёты. Проверять marker/hash и не выдавать успешный replay без фактического эффекта.

**Причина.** Реализован анализ записей журнала, а не recovery протокол §8.3.

**Точки проверки:** formalizer/ah_adapter.py; core/persistence.py; formalizer/canonical_ledger.py.

### I18 — Неизвестные операции и незамкнутые аргументы молча пропускаются

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** AH adapter игнорирует op_type без handler, но может вернуть UID как applied. ir_to_graph пропускает неподдержанные роли/аргументы; commit_stage не использует возвращённый отчёт о покрытии как обязательный гейт. Таким образом частичный перевод может завершиться успешным коммитом.

**Как исполнено сейчас.** Native writer допускает только перечисленные typed ops; legacy ADD_* и unknown ops отклоняются. незамкнутый аргумент блокирует родителя. plan\E сохраняет shared operations только через admitted fragment ownership/closure.

**Как должно быть.** Неизвестная операция → явный ADAPTER_NOT_COVERED/INTEGRITY_ERROR и атомарный отказ соответствующего фрагмента. Замыкание всех обязательных typed refs проверять до записи.

**Причина.** Успешный результат описывает входной список UID, а не доказанно применённые операции.

**Точки проверки:** formalizer/ah_adapter.py; formalizer/native_plan.py; formalizer/store_interface.py.

### I19 — Фактический writer создаёт граф без канонических опор и нужных типов

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** ADD_NODE handler материализует entity-актант как S, не M, и вызывает add_hypernode без SupportRecord/IdentityBinding/TimeAssertion/temporal_mode. Два одинаковых EVENT-ввода сливаются core-дедупом в один N; supports пусты. В mapping также нет полноценного пути EXPERIENCER/SURFACE_ARG и Ref(G) для proposition.

**Как исполнено сейчас.** ENTITY материализуется как M, пропозициональный аргумент как N/G; ROOT/DERIVED support и TimeAssertion пишутся в том же COW/WAL коммите. EVENT не дедупится legacy signature index; native visibility — CanonicalLedger, не occurrence_count.

**Как должно быть.** Исполнять MutationPlanV2 с EnsureEntity/Binding/EnsureNode/AddRootSupport/AddTimeAssertion, сохраняя типы M/N/G, режим EVENT/STATE и связь с наблюдением.

**Причина.** V7 IR сведён к прежнему графовому API с потерей контрактов §14/§17; это центральный пробел интеграции AH.

**Точки проверки:** formalizer/graph_ops.py; formalizer/native_plan.py; formalizer/canonical_ledger.py.

### I20 — Материализатор scope не реализует полную типизированную композицию

**Статус:** КОД / ПОКРЫТИЕ ОГРАНИЧЕНО. **Приоритет исходного аудита:** P1.

**Недочёт.** ADD_SCOPE сначала создаёт обычный базовый N, затем оболочки; нет SOM/UsageLink и отдельной опоры asserted-корня. Неизвестные function_id/IF могут пропускаться; quantified-ветка строится от base, не всегда от уже вложенного current. Реестр операторов helper и действующего AH различается.

**Как исполнено сейчас.** Native plan собирает поддерживаемый operator tree с SOM links, directional operands, quantifier pair и bound variables. ARGUMENT/ATTITUDE может закрываться целым N/G-деревом; дочерние leaves не получают root support и не экспортируются compatibility projection как факты. Неизвестная attitude сохраняется UNKNOWN, не лицензирует истинность содержимого. Неизвестный оператор/неполная типизация — явный отказ. BEFORE/AFTER/DURING typed TimeLiteral проходят C/T6/persistence и runtime comparison без UsageLink. Numeric scope и все GoalSpec-поверхности пока не полностью встроены.

**Как должно быть.** Строить обратимо типизированное дерево G с правильным порядком операторов/BoundVar, структурными операндами и поддержкой только лицензированных корней. Неподдержанный оператор блокирует фрагмент с диагностикой.

**Причина.** Набор частных обработчиков оболочек не равен общей композиции ScopeTree и может изменить область действия.

**Точки проверки:** formalizer/native_plan.py; formalizer/tp_proposer.py; formalizer/runtime_adapter.py; logic/function_registry.py.

### I21 — Глобальный seq журнала не защищён от конкурирующих экземпляров

**Статус:** КОД / НЕ ПРОГНАНО. **Приоритет исходного аудита:** P0.

**Недочёт.** Два JournalChannel на одном файле держат собственный head и оба выдают seq=1. Нет общего атомарного счётчика/межэкземплярной сериализации append. Head увеличивается до успешной durable-записи.

**Как исполнено сейчас.** JournalChannel использует shared RLock по пути и OS file lock. Seq вычисляется заново внутри lock, head публикуется после fsync; все процессы/экземпляры должны пользоваться этим каналом. Конкурентный прогон не выполнялся.

**Как должно быть.** Один сериализованный durable writer с уникальным монотонным seq, общей блокировкой и определённым результатом ошибки append.

**Причина.** Head-only admission и тотальный порядок DB-N нельзя построить на счётчике внутри отдельного Python-объекта.

**Точки проверки:** core/journal.py.

### I22 — Повреждение середины журнала приводит к молчаливому удалению хвоста

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** Recovery обрезает файл на первой некорректной записи. Повреждение второй строки из трёх удаляет и третью корректную durable-запись; INTEGRITY_ERROR не возникает.

**Как исполнено сейчас.** Полная повреждённая frame, checksum/schema/seq mismatch в середине — INTEGRITY_ERROR без удаления последующих записей. Обрезается только незавершённый последний frame без newline; legacy checksum-less frames читаются как исторические, без заявления о защите их содержимого.

**Как должно быть.** Различать допустимый незавершённый последний append и повреждение уже зафиксированного префикса. Для последнего — fail-safe INTEGRITY_ERROR, без уничтожения доказательств. Проверять порядок и уникальность seq.

**Причина.** Логика восстановления torn tail применяется к любому повреждению и превращает corruption в скрытую потерю данных.

**Точки проверки:** core/journal.py.

### I23 — Provider replay путает ordinal, attempt и область запуска

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** Кэш использует run_id+prompt без ordinal и полного model/params snapshot: два одинаковых запроса в одном run превращаются в один вызов. Повтор того же prompt под новым run получает IntegrityError. ProviderCallLog не содержит достаточных durable данных для полного восстановления ответа; real backend использует постоянный run_id и переводит ряд ошибок в unavailable.

**Как исполнено сейчас.** Provider log различает run_id/ordinal/attempt, сохраняет prompt/model/params/raw response/timing и fsync PENDING→RECEIVED/FAILED. Replay возвращает recorded bytes либо recorded failure. Незавершённый PENDING допускает новый attempt. Смена exchange identity/terminal rewrite запрещена.

**Как должно быть.** Различать (run, stage/call ordinal, request hash, model/params) и attempt. Новый run допускает новый ответ; повтор конкретного RECEIVED обязан воспроизводить сохранённые bytes. INTEGRITY_ERROR нельзя маскировать под недоступность провайдера.

**Причина.** Ключ replay привязан к тексту prompt вместо конкретного разрешённого вызова.

**Точки проверки:** formalizer/provider_adapter.py; formalizer/provider_call_log.py; formalizer/real_backend.py.

### I24 — InterpretationRunBinding не является durable CAS

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** Владелец хранится в памяти, не восстанавливается из журнала и не защищён общей блокировкой. Новый объект на прежнем файле не видит runA и разрешает runB занять ту же пару observation/version; release также освобождает пару без обязательной новой версии.

**Как исполнено сейчас.** Run binding — append+fsync CAS под общей journal lock до model call. Владелец и snapshot неизменяемы; recovery восстанавливает их, foreign owner investigation-only. Holder не снимается обычным release.

**Как должно быть.** Атомарный durable binding до провайдера, восстановление по журналу, запрет незаявленной смены владельца и проверка полного snapshot. T5 не должен считать отсутствие binding достаточной eligibility.

**Причина.** Существование записи bind в логе не помогает, если holder() читает лишь пустой словарь нового процесса.

**Точки проверки:** formalizer/run_binding.py; formalizer/v7_pipeline.py.

### I25 — GoalExecutor принимает произвольное правило и недоказанное заключение

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** GoalRequest(MADE_UP, premises=(), conclusion=anything) возвращает APPLIED. Нет обязательного registry lookup, проверки формы OR/FORALL, покрытия всех n−1 отрицаний и соответствия conclusion содержанию premises. Проверяется преимущественно наличие ID в live_premises.

**Как исполнено сейчас.** Production goal channel разрешает только OR_ELIMINATION/FORALL_INST, непустые живые concrete premises, конкретные temporal assertion refs и типизированную форму заключения. OR требует NOT каждого другого disjunct; FORALL связывает только собственный bound_var и совпадающую restriction.

**Как должно быть.** Заключение должен строить/проверять зарегистрированный modus над типизированными доказательствами. Пустые/чужие premises и незарегистрированный rule_id отвергаются до мутации.

**Причина.** Исполнитель доверяет строке заключения вызывающего кода; в проекте не найден обязательный валидирующий production-слой перед ним.

**Точки проверки:** formalizer/goal_channel.py; formalizer/goal_executor.py.

### I26 — Goal dedup не различает временные доказательства

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** Ключ содержит rule_id, support IDs и conclusion_signature; temporal_premise_assertion_refs отсутствует. Два вывода в 15:00 и 16:00 от тех же опор дают APPLIED затем APPLIED_NOOP, остаётся один путь. Request не содержит нормативного request_window и идентификаторов свидетельств для повторной проверки.

**Как исполнено сейчас.** Dedup key = rule + sorted support IDs + conclusion signature + sorted assertion IDs. request_window не входит: та же опора может дать NOOP и UNKNOWN для другого окна. У разных assertion refs отдельные пути.

**Как должно быть.** Четырёхкомпонентный ключ с конкретными assertion refs; request_window хранить в запросе, но не включать в дедуп пути. Проверять покрытие ответа отдельно от наличия пути.

**Причина.** Опора и её временное свидетельство — разные уровни provenance; их смешение ломает DR29/DR30.

**Точки проверки:** formalizer/goal_channel.py; formalizer/goal_executor.py.

### I27 — GOAL_DECISION и DB-N существуют только как in-memory модель

**Статус:** КОД / НЕ ПРОГНАНО. **Приоритет исходного аудита:** P0.

**Недочёт.** GoalStore — словари/списки; создание узла, пути, decision и terminal выполняется последовательно без store-транзакции. Нет durable PENDING, общего lock с отзывом, атомарной пары derived support+TimeAssertion. Recovery-helper по найденному decision возвращает результат, но не завершает обязательный durable terminal.

**Как исполнено сейчас.** GOAL_PENDING durable; APPLIED records+GOAL_DECISION в одном canonical WAL unit; NOOP/ABORTED decision fsync под DB-N без AH mutations. R0 исторический decision; R1/R2 recheck paths/license; terminal append once. Crash/race доказательства не запускались.

**Как должно быть.** Реализовать GoalExecutor поверх того же canonical store и status writer, с PENDING/fsync, APPLIED commit boundary, DB-N и recovery R0→R1→R2. In-memory модель допустима как отдельный backend того же контракта, но сама по себе не обеспечивает durable-свойства.

**Причина.** Комментарии об атомарности описывают желаемое поведение; dict assignment не реализует crash/concurrency contract.

**Точки проверки:** formalizer/goal_channel.py; formalizer/ah_adapter.py; formalizer/recovery.py.

### I28 — TemporalLedger вводит неутверждённое продолжение состояния

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** temporal.assert_true с началом 9 создаёт удержание в неопределённое будущее: holds(1000000)=True. Модель не выражает нормативное различие POINT/EXISTENTIAL/CONTINUOUS и полную двухосевую provenance; параллельно существуют другие несовместимые temporal helpers.

**Как исполнено сейчас.** Нет даты → support без TimeAssertion. Датированный путь использует только выраженный POINT/EXISTENTIAL/CONTINUOUS; no implicit [t,∞). Относительная дата требует declared anchor/timezone, неоднозначное civil time не угадывается. Сложные temporal expressions могут остаться PARTIAL.

**Как должно быть.** Свидетельство только в явно утверждённой области; без датировки — вообще без TimeAssertion. POINT не превращается в [t,∞), EXISTENTIAL не становится непрерывностью. Один канонический контракт для всех потребителей.

**Причина.** Старый fluent-подход подменяет осторожную временную семантику V7.

**Точки проверки:** formalizer/native_frontend.py; formalizer/native_plan.py; formalizer/temporal.py.

### I29 — Временная лицензия допускает недоказанный OR-вывод

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** POINT(15) корня и EXISTENTIAL{15,16} отрицания признаются LICENSED, хотя отрицание могло держаться только в 16. Другой inference helper для OR берёт простое пересечение CONTINUOUS[0,10] и [5,15] и выводит [5,10], не соблюдая контракт полного покрытия корня.

**Как исполнено сейчас.** Невырождённый EXISTENTIAL не покрывает точку; OR license требует universal coverage отрицания над областью OR. FORALL переносит intersection, mixed dated/undated запрещены. Common-witness license применяется только к доказанной корреляции, а не одинаковым bounds.

**Как должно быть.** Использовать единую нормативную алгебру всех реализаций; недегенеративное existential-отрицание не покрывает конкретный point. В действующей V7 отсутствие покрытия всей области корня означает отказ, не неявное ослабление правила.

**Причина.** Пересечение/наличие точки в возможном множестве ошибочно принимается за гарантированное покрытие.

**Точки проверки:** formalizer/temporal_license.py; formalizer/goal_channel.py; formalizer/canonical_ledger.py.

### I30 — Живость заключения подменяет живость конкретного proof path

**Статус:** КОД. **Приоритет исходного аудита:** P0.

**Недочёт.** ProofGraph хранит premises как node IDs, не обязательные support/binding/assertion refs. effective_visibility TimeAssertion проверяет LIVE записи и общую F-visible заключения. Если derived путь погиб, но Q живёт по независимой root-опоре, старое derived-свидетельство остаётся видимым.

**Как исполнено сейчас.** Path liveness вычисляется по собственным supports, bindings и temporal premise assertions. Свидетельство адресует свой SupportRecord; query_support не заимствует дату другого пути того же N. Отзыв одного assertion рушит только зависящие derived paths.

**Как должно быть.** Эффективность каждого свидетельства вычисляется по его собственному support_record_id и транзитивным конкретным premises/bindings/temporal refs. Другой путь того же N не может оживить это свидетельство.

**Причина.** Узел и доказательство узла смешаны; независимое знание Q ошибочно сохраняет чужую дату/основание.

**Точки проверки:** formalizer/canonical_ledger.py; formalizer/support_som.py; formalizer/fact_query.py.

### I31 — Новое утверждение не восстанавливает доступность канонического узла

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** После отзыва последнего пути Node.status становится SUPERSEDED. Добавление свежей LIVE опоры от нового наблюдения не меняет статус; f_visible по-прежнему исключает N.

**Как исполнено сейчас.** S/F видимость — текущий fixed point, CASCADE_SUPERSEDED — audit event. Новая живая опора даёт REACCESSIBLE; старый terminal support не оживает. Canonical OPERATOR links всегда LIVE и становятся эффективны через доступного родителя.

**Как должно быть.** Статусы старых опор терминальны, доступность N/G вычисляется по текущим путям. CASCADE_SUPERSEDED — историческое событие узла; новая опора допускает REACCESSIBLE без оживления старой записи.

**Причина.** Снова реализован терминальный флаг узла, от которого архитектура явно отказалась.

**Точки проверки:** formalizer/canonical_ledger.py; formalizer/usage_layer.py.

### I32 — UsageLayer не соответствует SOM и транзитивной S-access

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** Kinds представлены N_N/G_N/G_G, а не ATTITUDE/OPERATOR. N→G (SAY→NOT) отвергается. Доступность дочернего N требует asserted=True: структурный неутверждённый операнд живого G не становится S-accessible. Нет нормативных per-observation attitude/holder и canonical OPERATOR lifecycle.

**Как исполнено сейчас.** ATTITUDE links per observation, OPERATOR links canonical; typed N/G slots, parent/position validation и transitive S-access. ATTITUDE отзывается по tag; OPERATOR retract запрещён. Собственные proof paths сохраняют F visibility независимо от link другого родителя.

**Как должно быть.** UsageLink с kind ATTITUDE/OPERATOR, typed parent slot, source-dependent identity. S-access — достижимость от F-visible корней по эффективным links, без требования собственной asserted-опоры у промежуточных узлов.

**Причина.** Графовая форма ребра заменяет семантический вид связи и блокирует вложенные цитаты/операторы.

**Точки проверки:** formalizer/native_plan.py; formalizer/ah_adapter.py; formalizer/canonical_ledger.py; formalizer/usage_layer.py.

### I33 — Отзыв, conflict evidence и lifecycle audit не замкнуты на canonical store

**Статус:** КОД / НЕ ПРОГНАНО. **Приоритет исходного аудита:** P1.

**Недочёт.** T6b-модель TimeAssertion содержит только source_tag и не представляет GOAL_RUN×DERIVED. Нет общего assertion-id отзыва для всех provenance, полного CandidateEvidence/TwoCandidateExcludedEvidence recovery и durable NodeLifecycleEvent потока. Observation map индексируется obs_id; повторный отзыв может дать InvalidTransition. В core SupportLedger инвалидизация удаляет записи вместо нормативного audit-статуса.

**Как исполнено сейчас.** Status channel durable для observation/assertion/binding/ATTITUDE/report; OBS-source A отзываются по tag независимо от ROOT/DERIVED, GOAL A остаются LIVE-неэффективны. Кандидат×committed и кандидат×кандидат отчёты pair-granular; D recovery восстанавливает полное evidence born-closed при отзыве. Lifecycle events атомарны, identity/seq проверяются. GATE_PRECHECK только диагностика с forward refs.

**Как должно быть.** Единая схема двух осей provenance, version-aware наблюдений, per-assertion declared trigger, report closure/dedup и NodeLifecycleEvent; все статусные эффекты одной атомарной границей. Повтор replay не должен менять историю или падать на уже состоявшемся отзыве.

**Причина.** Несколько демонстрационных ledgers не образуют исполняемый протокол §8.2/§17 и не сохраняют полную историю.

**Точки проверки:** formalizer/ah_adapter.py; formalizer/canonical_ledger.py; formalizer/commit_stage.py.

### I34 — Fact reader не обеспечивает доказательную и временную видимость

**Статус:** КОД / ЧАСТИЧНО. **Приоритет исходного аудита:** P1.

**Недочёт.** fact_query проверяет LIVE/kind; не проверяет конкретный proof path, bindings, временную область и конфликтные отчёты. allow_kinds способен разрешить HYPOTHETICAL без зарегистрированного bridging rule.

**Как исполнено сейчас.** Canonical fact query проверяет concrete path и его время. Native Exists/role lookup и formula readers используют adapter; расширение allow_kinds не делает quote/hypothesis фактом. Native compiler сохраняет logical/quantified trees; WH/COUNT читают live proof/time, Counterfactual не делегируется мировому reader. Остальные специальные цели не объявлены full parity.

**Как должно быть.** Обычный factual-query обязан читать через канонический F-visible и эффективные temporal evidence. Доступ к hypothetical/quoted содержимому — отдельный структурный запрос, не утверждение истинности.

**Причина.** Параметр фильтра заменяет семантическую лицензию; низкоуровневый helper нельзя использовать как полный контракт запросов.

**Точки проверки:** formalizer/fact_query.py; inference/engine.py; inference/formula.py; inference/materialization.py.

### I35 — Верхняя числовая граница превращается в нижнюю

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** answer_count(AT_MOST_N,3,без certificate) возвращает UNKNOWN с lower_bound=3; с certificate поле также равно3. Из «не более трёх» не следует «не менее трёх».

**Как исполнено сейчас.** AT_MOST_N отдаёт upper_bound, а не lower_bound; UNKNOWN без DomainCertificate не меняет направление неравенства. Это исправление pure reader; сквозной numeric scope в native path остаётся незавершённым.

**Как должно быть.** Развести lower_bound/upper_bound/exact_count и выводить только логически следующее ограничение. Отдельно решить, когда DomainCertificate нужен для вычисления точности, а когда число прямо утверждено наблюдением.

**Причина.** Общая ветка EXACTLY_N/AT_MOST_N ошибочно переносит нижнюю границу на противоположное неравенство.

**Точки проверки:** formalizer/count_reader.py.

### I36 — G0 PASS относится к другому SHA256 документа

**Статус:** ДОКУМЕНТ / G0 BLOCKED. **Приоритет исходного аудита:** P1.

**Недочёт.** Текущий FORMALIZER_ARCHITECTURE_V7.md: 48dbb3c9e69126ff2ffb4906fccbe8c0fefacf275e7066bea9096a065b9a3a0e. Manifest фиксирует 09e0771d1b710b0e492e0a57b8655858eab7a1906ece07da4b7a93ac84e2dd8f. При этом шапка и §20 заявляют PASS именно этой редакции и требуют нового review при изменении байтов.

**Как исполнено сейчас.** Старый G0 manifest сохранён с явной VOID-пометкой для действующего текста. Architecture больше не переносит исторический PASS на новые байты. Хеш текущего текста указан в этом отчёте; новая независимая подпись не выдумана.

**Как должно быть.** Сохранить старый manifest как историческое доказательство; текущую редакцию проверить заново и выпустить новый manifest либо явно снять текущий PASS до проверки. Простая замена хеша без review недопустима.

**Причина.** Статус доказательства не перенесён вместе с изменениями нормативного текста. Сам этот аудит не является автоматической подписью нового G0 PASS.

**Точки проверки:** docs/G0_REVIEW_MANIFEST_V7_CLEAN.md; docs/FORMALIZER_ARCHITECTURE_V7.md.

### I37 — Legacy projection повторно подаёт вложенную команду как фактическую память

**Статус:** КОД. **Приоритет исходного аудита:** P1.

**Недочёт.** «Проверь утверждение: Крипл — это ИИ» имеет EMBEDDED target, но experience получает speech_act_kinds=(ASSERTION,COMMAND). Guard снимает НЕ ФАКТ только при отсутствии ASSERTION. Реальная проекция: ACTIVE MEMORY → «Ранее пользователь сказал: “Проверь утверждение: Крипл - это ИИ”», без маркировки команды/нефакта.

**Как исполнено сейчас.** Projection исключает command/query/quoted/structural-only content и canonical N без F visibility; native Integration не повторяет assertions как legacy facts. Experience остаётся источником аудита/контекста, а не O support для вложенного действия.

**Как должно быть.** Проецировать эпистемику конкретного утверждения/usage, а не union kinds всего experience. Проверяемое содержание команды не становится фактом мира или доказательством из-за соседнего ASSERTION.

**Причина.** При агрегации speech acts теряется scope. Это подтверждённое поведение действующего AH-контура, не только недоделка нового formalizer.

**Точки проверки:** projection/agent_context.py; integration/service.py; agent/orchestrator_base.py.

### I38 — Legacy parser теряет универсальный квантор

**Статус:** КОД / ГРАНИЦА. **Приоритет исходного аудита:** P1.

**Недочёт.** При воспроизводимом разборе «Каждое животное живое» с неоднозначной морфологией NOUN/ADJF выдаётся одно утверждение, assertion.quantifier=None и logical_propositions отсутствует. Универсальное ограничение не переносится в результат.

**Как исполнено сейчас.** Production не вызывает удалённый legacy parser. FORALL/EXISTS TP tree сохраняет ordered [bound_var,body], SOM body и commit только root; экземпляры — on-demand. Новые malformed/однооперандные quantifiers не пишутся; старые shapes оставлены load-only. Native runtime projection сохраняет quantifier; explicit roots и bounded положительный EXISTS witness поддержаны. General nested quantifier/WH joins не объявлены завершёнными.

**Как должно быть.** Сохранить FORALL и restriction/body в актуальном IR; при невозможности — честный unresolved scope, не простое частное утверждение.

**Причина.** Связь binder с restriction и scope теряется при морфологической неоднозначности. Дефект актуален и для fallback legacy-пути I01.

**Точки проверки:** formalizer/tp_proposer.py; formalizer/native_plan.py; logic/function_registry.py; formalizer/runtime_adapter.py.

### A01 — Не замкнута граница content identity и derived EVENT occurrence

**Статус:** НОРМА УТОЧНЕНА / G0 BLOCKED. **Приоритет исходного аудита:** SPEC_GAP.

**Недочёт.** §7.5(A) делает known структурное содержание общим; EVENT-утверждения occurrence-local и «не сливаются никогда». §7.5(B/C) позволяет AND/OR_ELIMINATION дать фактическую опору существующему структурному операнду. Не определён единый ключ EVENT occurrence при таком переходе для двух независимых датированных корней с одинаковым P.

**Как исполнено сейчас.** §7.6 разделяет content formula и derived EVENT occurrence: новый путевой ключ — новый occurrence с formula_ref; same path — NOOP того же occurrence; STATE — новый support прежнего N. Goal channel и commit-time AND_ELIMINATION следуют этой границе; PROCESS/TRANSITION/UNKNOWN также не получают STATE-слияние. Структурный операнд сохраняется отдельно от утверждённого EVENT-вхождения. Независимая архитектурная трасса ещё требуется.

**Как должно быть.** Нормативно разделить Formula/Content identity и EventOccurrence identity либо задать эквивалентное точное правило ключей и связей. Провести два OR-наблюдения в 15/16, два derived пути к P и независимое прямое EVENT-утверждение: сколько N, где даты, что дедупится, что отзывает каждый источник.

**Причина.** Два текста допускают разные модели для derived EVENT: общий N по содержанию или отдельные occurrence N. Это кандидат на SPEC_GAP с конкретной трассой, а не требование немедленно вводить новый тип графа.

**Точки проверки:** docs/FORMALIZER_ARCHITECTURE_V7.md §7.6; formalizer/goal_channel.py.

### A02 — Не определена корреляция экзистенциального времени конъюнктов

**Статус:** НОРМА УТОЧНЕНА / G0 BLOCKED. **Приоритет исходного аудита:** SPEC_GAP.

**Недочёт.** §6.3 даёт каждому AND-конъюнкту собственное TimeAssertion с общим интервалом; EXISTENTIAL реализации выбирают момент независимо. «Вчера книга одновременно была на столе и мокрой» означает ∃t(P(t)∧Q(t)), что сильнее (∃t P(t))∧(∃u Q(u)). Общих bounds недостаточно, чтобы сохранить это различие.

**Как исполнено сейчас.** §7.6 и ledger сохраняют общий witness AND; производные assertions наследуют его через конкретные premises. Одинаковые bounds независимых наблюдений не доказывают совместный момент. Лицензия/конфликт учитывает доказанную корреляцию без превращения в CONTINUOUS.

**Как должно быть.** Сохранить общий временной witness/constraint либо лицензировать совместный запрос через исходный AND-root с явной корреляцией. Трасса должна отличать одно совместное наблюдение от двух независимых existential-наблюдений, не превращая их в CONTINUOUS.

**Причина.** Потеря зависимости между свидетелями ограничивает корректную композицию времени. Наличие AND-root может сохранить данные, но правило их использования в temporal reader/лицензии не задано явно.

**Точки проверки:** docs/FORMALIZER_ARCHITECTURE_V7.md §7.6; formalizer/native_plan.py; formalizer/canonical_ledger.py; formalizer/goal_channel.py.

### A03 — Недатированный факт не отличён от вневременного общего правила

**Статус:** ПРИНЯТАЯ ГРАНИЦА. **Приоритет исходного аудита:** Ограничение.

**Недочёт.** Смешанное датирование намеренно не лицензируется. Поэтому недатированное «Каждый студент — человек» и датированное R(Иван,09:00) не дают B(Иван,09:00) без дополнительной временной лицензии. Это безопасный default для факта с неизвестным временем, но чрезмерно узкий для логических/таксономических законов.

**Как исполнено сейчас.** §7.6 явно сохраняет безопасный default: недатированное не равно TIMELESS/GENERIC; mixed dating → UNKNOWN. Новый универсальный temporal-law тип не вводился без решения архитектуры.

**Как должно быть.** Если требуется такой класс вывода, ввести объявленную семантику TIMELESS/GENERIC для правил с чётким scope и проверкой основания. Не превращать любое отсутствие даты во всеобщность.

**Причина.** Это ограничение выразительности выбранной нормы, а не противоречие или текущая ошибка реализации.

**Точки проверки:** docs/FORMALIZER_ARCHITECTURE_V7.md §7.6; formalizer/temporal_license.py.

### A04 — Open lexical обеспечивает сохранение ввода, но не общее понимание новых понятий

**Статус:** ПРИНЯТАЯ ГРАНИЦА / ДАННЫЕ. **Приоритет исходного аудита:** Ограничение.

**Недочёт.** Изолированные OPEN/UNLINKED occurrences нельзя сливать по написанию; межнаблюдательные выводы для них запрещены. ReportBridging/EventIdentity и миграции ограничены declared rules/releases. Два новых одинаково написанных отношения могут навсегда остаться несопоставимыми без внешнего подтверждения.

**Как исполнено сейчас.** OPEN сохраняет новое содержание UNLINKED, но не угадывает sense equivalence. Declared reinterpretation frozen input под v+1 и audit-link open→known теперь подключены. General identity/CorefPolicy и автоматическое предложение/подтверждение sense equivalence не реализованы; spelling остаётся недостаточным основанием.

**Как должно быть.** Сохранять изоляцию до доказательства, но для долгосрочной цели определить исполнимый процесс предложений/подтверждения sense linking, переинтерпретации и измерения semantic coverage. Отличать «ввод сохранён» от «смысл сопоставлен и пригоден для вывода».

**Причина.** Это сознательная граница безопасности. Она не достигает сама по себе цели «понимать практически любой вход»; требуется рост знаний и механизм проверяемого связывания, а не бесконечные handlers предложений.

**Точки проверки:** docs/FORMALIZER_ARCHITECTURE_V7.md §7.6; formalizer/native_plan.py.

### A05 — Первое допущенное противоречащее утверждение получает привилегию

**Статус:** ПРИНЯТАЯ ГРАНИЦА. **Приоритет исходного аудита:** Ограничение.

**Недочёт.** Admission оставляет раннее утверждение фактом, позднее несовместимое — CandidateEvidence в отчёте. После отзыва победителя кандидат автоматически не становится F-visible: ответ UNKNOWN до нового разрешённого действия. Порядок прихода влияет на пригодное для вывода знание, хотя сам admission детерминирован.

**Как исполнено сейчас.** §7.6 сохраняет earliest admission policy и запрет hidden revival. Retraction закрывает conflict report, но CandidateEvidence не становится root fact. Для пересмотра требуется declared trigger и новая версия; это политика, не доказательство объективной истины победителя.

**Как должно быть.** Явно принять эту политику либо определить контекстную/источниковую модель спорных убеждений и declared trigger пересмотра кандидата после разрешения конфликта. Сохранить запрет скрытого revival.

**Причина.** Это не баг head-only порядка, а содержательное ограничение для многоисточниковой памяти и исправлений пользователем. Проверять качество памяти нужно вместе с политикой разрешения споров.

**Точки проверки:** docs/FORMALIZER_ARCHITECTURE_V7.md §7.6; formalizer/ah_adapter.py.

## Дополнительные находки последнего прохода

### I39 — Положительное P могло доказывать неэффективный NOT(P)

**Статус:** КОД. **Недочёт.** Reader использовал общий conflict content_key для N и G(NOT,N), заимствуя положительную опору для другого выражения. **Как исполнено сейчас.** G читается по собственному пути либо явному NOT этого G; положительное N не доказывает NOT(N). Полярность двойного NOT вычисляется вложенно. **Как должно быть.** Conflict content key не является identity/proof key. **Причина.** Общий ключ несовместимости смешивался с ключом заключения. **Точки:** canonical_ledger.query_proposition; native_plan.tree_node.

### I40 — Старая версия отзывалась до успешной замены

**Статус:** КОД. **Недочёт.** interpret_full supersede'ил O/v до T4/T5/T6 нового запуска; неудача оставляла потерю прежних фактов. **Как исполнено сейчас.** C планирует SUPERSEDE_VERSION; T6 на draft отзывает старое, проводит admission и фиксирует replacement+retirement+marker/D одной WAL-границей. Полный отказ отбрасывает retirement draft. Open→known audit-link требует конкретных старых live supports, новых known supports, trigger и release snapshot. Stale evidence получает терминальный STALE_SUPERSEDED. **Как должно быть.** Failed replacement сохраняет старую версию; successful migration атомарна, без revival/alias. **Причина.** Отзыв находился вне commit boundary замены. **Точки:** migration; v7_pipeline; native_plan; ah_adapter.commit_transaction.

### I41 — Повторный отзыв переписывал терминальное состояние TimeAssertion

**Статус:** КОД. **Недочёт.** Source-wide retraction безусловно назначал RETRACTED, supersede затем безусловно SUPERSEDED даже уже отозванным записям. **Как исполнено сейчас.** Меняется только LIVE запись; old terminal reason сохраняется. Supersede задаёт собственный terminal status в той же операции, без промежуточного переписывания. **Как должно быть.** Терминальная конкретная запись не оживает и не меняет исторический исход от повторной команды. **Причина.** Source lookup не проверял прежний статус. **Точка:** CanonicalLedger.retract/supersede.

### I42 — Native counterfactual не замкнут на фильтрацию derived paths

**Статус:** PARTIAL / ЯВНЫЙ ОТКАЗ. **Недочёт.** GroundFormula native branch читает durable мировой proof раньше проверки runtime assumptions; результаты такого чтения нельзя выдавать за hypothetical proof. **Как исполнено сейчас.** Native compiler не делегирует COUNTERFACTUAL в этот reader и возвращает COUNTERFACTUAL_NATIVE_SCOPE_NOT_IMPLEMENTED. Legacy helper сам по себе не доказывает порт. **Как должно быть.** Runtime overlay фильтрует каждый concrete premise path; branch assumptions не создают canonical supports и не переносятся наружу. **Причина.** Каноническая видимость и допустимость предпосылки внутри ветви — разные контракты. **Точки:** native_queries.compile_native_queries; inference/formula._eval; inference/engine._counterfactual.

### I43 — Native COUNT не имел источника доказательства полноты

**Статус:** КОД / ДАННЫЕ BLOCKED. **Недочёт.** Pure count helper не составлял production CountGoal; вычисленное число нельзя объявлять точным только по наличию найденных N или query bool. **Как исполнено сейчас.** CountGoal считает разные entity witnesses, нижнюю границу показывает отдельно. Optional released DomainCertificate фиксирует template/role/known roles/window/release и реальные live support IDs полноты; эти источники входят в premise refs. Без сертификата — INCOMPLETE_DOMAIN. **Как должно быть.** Точный count выводится только по конкретной закрытой области; открытая область не превращается в точную. **Причина.** Перебор совпадений и доказательство исчерпанности не равны. **Точки:** native_queries; contracts.CountGoal; resources/loader; projection/agent_context.

### A06 — BNF §16 не задаёт исполнимую полезную нагрузку Emit

**Статус:** SPEC_GAP. **Недочёт.** `emit := Emit kind { fields }` использует то же `fields`, где разрешены только stage/reads/when/emit/priority/cost; capture declarations, payload field bindings и передача параметров lookup не определены. Полнота грамматики заявлена, но канонического перевода в CandidateSchema из неё не следует. **Как исполнено сейчас.** Работает документированный bounded JSON AST; он не объявлен BNF parser. Нормативный файл в этом проходе не изменён. **Как должно быть.** Задать отдельные capture/output-field/value productions и versioned CandidateSchema manifest с однозначной компиляцией; затем реализовать parser и round-trip. **Причина.** Исполняемую схему нельзя восстановить из перечня общих имён без выбора разработчика. **Точки:** архитектура §16; syntax_rules; FORMALIZER_RUNTIME_RESOURCES.md.

### A07 — Числовой scope и незнакомая identity остаются отдельными границами покрытия

**Статус:** PARTIAL / ДАННЫЕ И ТИПЫ. **Недочёт.** Наличие CountGoal не замыкает запись/чтение AT_LEAST_N/EXACTLY_N/AT_MOST_N из ScopeTree, а одинаковое имя в двух O не даёт grounded identity. **Как исполнено сейчас.** Entity-count и direct host bindings поддержаны; numeric scope-reader и общий CorefPolicy resolver не представлены как DONE. **Как должно быть.** Числовой bound имеет полный registry/operand codec/goal compiler контракт; identity связывается только с доказательством и ресурсной policy. **Причина.** Это общие типовые механизмы и данные, не проблемы, решаемые обработчиком очередной фразы. **Точки:** архитектура §6.5/§17.3; count_reader; native_frontend/native_queries; IdentityBinding.

## Проверка и предел доказательства

- Тесты не читались, не анализировались, не запускались и не изменялись.
- Синтаксис всех 280 production Python-файлов проверен через compile(); проверены импорты 12 runtime-модулей. Это не исполнение сценариев.
- Пройдены статическая сверка call sites и git diff --check. Изменения ограничены src/docs; нормативный файл и его SHA256 сохранены.
- Исходные 43 находки I01–I38/A01–A05 сохранены; добавлены I39–I43/A06–A07. Итого 50 записей, каждая с текущим состоянием и пределом.
- Crash/race/model/e2e/corpus не прогонялись; чужие исторические результаты не выдаются за доказательство текущей реализации.
- Публикация на temp не превращает G0–G5 в PASS.
