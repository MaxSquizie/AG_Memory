# Аудит всех статически найденных границ

Версия источников зафиксирована в inventory_v2.json. Проверены все 116 записей реестра, включая обёртки и несмысловые вызовы. Проверка исходников не означает исполнения всех режимов. Точное выражение вызова и статические callers: CALLSITE_CARDS.md.

Общие исходы: один выбор не означает RESOLVED; 0, ?, альтернативы, совместное множество, лимит и ошибка различаются. Их свёртка в None безопасна лишь если потребителю достаточно оставить результат неполным. Для смены маршрута требуется исходный статус.

## CONTENT по ресурсу — attitude_composition.py

Места: P001 (строка 88).

Вход и домен: AttitudeMap, морфология владельца, границы цитаты/союза; перечисление ограничено ресурсом и концами по запятым.

Потребление: Два рекурсивных ребёнка; ровно один владелец; internalize; native_frontend/T5.

Заключение: F05: не полный языковой генератор. holder_role берётся из ресурса; отказ блокирует весь родитель, ребёнок не становится фактом.

- P001: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Лексическая конструкция — component_clause.py

Места: P002 (строка 64).

Вход и домен: Связанные морфочтения, роли, временная и именная принадлежность; enumerate_candidates.

Потребление: Выбранные frames → именная/модификаторная сборка → native_frontend.

Заключение: F01/F04: singleton допускается при requires_attachment_probe=False; доказательство применимости лежит на генераторе. Сырые morph_bindings в подписи — отдельная нагрузка на исполнителя.

- P002: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Именные зависимости — component_dependency_reduction.py

Места: P003 (строка 86).

Вход и домен: Домены dependency_domains, сеть совместимости, фиксированные роли/чтения; отдельная проба при смысловой привязке.

Потребление: project → roots/dependencies/attributes/pp_readings → frame; дальнейшая аттестация морфологии.

Заключение: F05/F06: полнота ограничена генератором; несколько чтений переносятся только при общей ROOT-структуре. Вычисленный paragraph context_range не передаётся напрямую choose_domain; действует общий probe_context.

- P003: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Инфинитив — component_infinitives.py

Места: P004 (строка 18), P005 (строка 27), P006 (строка 63).

Вход и домен: Морфологические INFN-starts; source_set; произведение опубликованных отношений и контроллеров родителя.

Потребление: InputSlot.controller → рекурсивный ребёнок → proposition_args → scope/T5.

Заключение: F05/F09: в infinitive_link нет независимого контроллера, если нужная связь вне перечисленных parent controllers — блок. Общий CONTENT имеет INDEPENDENT_CONTENT, гарантии путей различны.

- P004: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P005: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P006: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Именная координация — component_nominal_groups.py

Места: P007 (строка 49).

Вход и домен: Соседние именные чтения около ScopeLexicon-союза; согласованные падежи; вопрос NOMINAL/OTHER.

Потребление: component_refinement: False блокирует; None вызывает coordinate; merged → один групповой слот.

Заключение: F02 подтверждён: OTHER возвращает False, а не неприменимость маршрута. Полнота соседних пар не доказана.

- P007: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Именные чтения/хозяева — component_nominal_questions.py

Места: P008 (строка 10), P009 (строка 27), P010 (строка 69), P011 (строка 114).

Вход и домен: Covers, единицы, nominal_host_views; связанные чтения в DomainNetwork; head-specific subtree.

Потребление: graph.restrict; hosts → именная сборка; NOMINAL_HOST_QUESTION → следующий текст ограничений.

Заключение: F01/F07: singleton без основания; смена вопроса чистит clarification, но не общий retirement. Контракт жизнеспособности строк не общий.

- P008: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P009: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P010: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P011: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Опущенный участник — component_participants.py

Места: P012 (строка 110).

Вход и домен: Подготовленные anonymous/mention/chain/bound/memory/group варианты; признаки, локальное окно, target predicate.

Потребление: implicit_bindings → implicit_plan; цепь должна уже иметь разрешённый target, bound var внутри scope.

Заключение: F03/F05: подписи обычных mentions могут совпадать; окно ограничено, anonymous сохраняет неизвестность. Поздний текст не всегда входит в context_range, хотя вопрос разрешает использовать later clauses.

- P012: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Выбор составного разбора — component_predication.py

Места: P013 (строка 187).

Вход и домен: Полные bundles после совместимости и coalesce; roles/readings/hosts/scope в подписях; отдельные partial domains.

Потребление: composition_domain/decision → select_child → native_frontend/T5.

Заключение: F04/F06: иногда вопрос о целом bundle остаётся; выбрать только local contrast можно не всегда. Неоднозначность сохраняется; incomplete_search блокирует все варианты. Перенос старых ограничений связан с F07/F12.

- P013: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Общая граница проб — component_probe.py

Места: P014 (строка 68), P015 (строка 125).

Вход и домен: ID+label, source, question; память/родитель/feedback; явный codec; неразличимые подписи блокируются.

Потребление: Decision provisional → replay/dispatcher → вызывающий потребитель; не выдаёт семантический RESOLVED.

Заключение: F04/F08/F13: контракт слота не типизирован; не вся память обязательна. Проверка формата и identical labels есть; смысловая истинность ответа не проверяется.

- P014: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P015: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Диспетчер и описание имени — component_refinement.py

Места: P016 (строка 193), P017 (строка 278), P018 (строка 382), P019 (строка 420), P020 (строка 446).

Вход и домен: Общая relation task или ресурсные пути; пересмотр только при явных failures; host из аргументов принятого родителя.

Потребление: compose_area recursively; InputSlot/attachment; nominal_args; partial propagation; roots.

Заключение: F07/F09: bounded revision не доказан полным; discard_attempt очищает reads, не общую транзакцию side effects. Минимальная scope assumption явно помечается ASSUMED_UNRESOLVED, её нельзя выдавать за RESOLVED источником.

- P016: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P017: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P018: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P019: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P020: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Временная область — component_temporal_scope.py

Места: P021 (строка 20).

Вход и домен: relative_temporal каждого дочернего frame; SOURCE_ASSERTED/EMBEDDED.

Потребление: Только весь разрешённый набор переносится в relative_time_targets; native_plan отдельно запрещает nested scope.

Заключение: F09: корректный EMBEDDED ведёт в UNSUPPORTED. Это предел компилятора, не ошибочный ответ и не повод требовать SOURCE_ASSERTED.

- P021: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Ресурсная внешняя связь — composition_boundaries.py

Места: P022 (строка 52).

Вход и домен: ScopeLexicon, предикативные признаки с двух сторон, unary/quantified matches; INTERNAL как отложить.

Потребление: CONNECTIVE → coordinate; UNARY → operator; INTERNAL → дальнейший лексический маршрут.

Заключение: F05: конечный ресурсный домен. INTERNAL не является отрицанием всех внешних связей; отказ/лимит → False → блок.

- P022: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Приёмка ребёнка — composition_children.py

Места: P023 (строка 40), P024 (строка 44).

Вход и домен: roots или сохранённые composition_domain; allowed roots; parent contract + контекст; resume pending child.

Потребление: Выбранные frame_refs снимают structural_unresolved; другие источники rejected; дальше потребляет родитель.

Заключение: F04/F07: singleton root здесь не равен singleton гипотезе — опирается на roots/allowed. Полная связь readiness receipt с каждым принимаемым snapshot не доказана; запрет частичной записи есть ниже.

- P023: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P024: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Обёртка морфологии — composition_morphology.py

Места: P025 (строка 63).

Вход и домен: Оригинальные readings, parent revision/imported restrictions, input/context/feedback.

Потребление: AGREEMENT → MORPHOLOGY dispatcher → project; publish_recoveries только финальных frames.

Заключение: P025 — локальная функция select, не вызов LLM. Здесь есть реальные подписки dispatcher.read и запрет наследовать свои старые ограничения как новые факты.

- P025: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Отсылка к содержанию — content_reference_functions.py

Места: P026 (строка 18), P027 (строка 26), P028 (строка 38), P029 (строка 75), P030 (строка 87), P031 (строка 160).

Вход и домен: Presence → pointer source_set → owner → завершённые локальные источники → role/attitude → mode/control.

Потребление: copy_use; receipt с source/current frame bases; validate_reference перед лексикой; proposition_args → T5.

Заключение: F09/F15: OTHER_SOURCE блокирует, внешняя память не входит в available; поддержаны same-content/subject-control, прочие substitutions исключены. Сильная проверка всех proofs существует; holder_role всё равно subject_role.

- P026: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P027: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P028: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P029: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P030: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P031: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Исправление согласования — contextual_agreement.py

Места: P032 (строка 54).

Вход и домен: Только dictionary ADJF/NOUN, независимые inflect предложения, edit distance ограничивает предложения; KEEP.

Потребление: RECOVERED variant → morphology_domain и final publish; исходное написание сохраняется.

Заключение: F05: частный объявленный класс морфологической коррекции; не общий исправитель языка. KEEP/отказ не разрешает замену. Ошибка формата тоже не заменяет слово.

- P032: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## OOV-функция — contextual_oov.py

Места: P033 (строка 63).

Вход и домен: Все объявленные POS с исходной поверхностью; inherited use constraints и целевые координаты; choose_domain.

Потребление: MORPHOLOGY_FUNCTION_RESTRICTION → project; feature-unknown reading licensed; богатые варианты отдельно.

Заключение: Сохранение неизвестных lemma/features защищено. F05/F06: конечная POS-схема и поддержка нескольких функций ограничивают представимость; неизвестность не означает опечатку.

- P033: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Явная ссылка — coreference.py

Места: P034 (строка 258).

Вход и домен: Подготовленные source/memory/context/bound/event/group варианты; bounded reference_goal; target occurrence.

Потребление: Решение + путь основания → entity/event/group/bound bindings → native_plan и binding validators.

Заключение: F03 подтверждён проекцией: label+type теряет различающие вхождения/контекст. CONTEXT singleton имеет самостоятельное основание и не относится автоматически к F01.

- P034: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Совместное направление — directional_goal.py

Места: P035 (строка 36).

Вход и домен: Ресурсные destination rules + goal PREP/case; вопрос тождественного локального назначения или SEPARATE.

Потребление: Объединённые refs и referent_constraint → nominal composition → spatial roles.

Заключение: F05: правило не покрывает все пространственные отношения. SEPARATE сохраняет оба слота; 0/?/ошибка блокируют. Совпадение назначения не утверждает прибытие.

- P035: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Речевой акт/адресат — discourse_scopes.py

Места: P036 (строка 72), P037 (строка 119).

Вход и домен: Целое принятое дерево; запрос пользователя; CONTENT edges; quote holder role; parent arguments для адресата.

Потребление: Speech act/quoted/speaker/addressee → coreference.prepare и native_plan guard.

Заключение: F15: generic CONTENT пишет holder_role=subject_role без отдельного основания. Адресат ограничен аргументами родителя + UNSPECIFIED; 0/? оставляют неизвестность, не выбирают ближайшего.

- P036: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P037: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Документная область даты — document_scopes.py

Места: P038 (строка 44).

Вход и домен: Кандидаты календарных строк по document_scopes.rules; HEADER/INLINE; bounded following context.

Потребление: Принятые/неразрешённые барьеры → region_forest; inherit date, не подменяет explicit unresolved time.

Заключение: F05: заголовки вне ресурса не входят в домен. INLINE убирается из barriers; UNKNOWN сохраняется как барьер. Frozen path требует тот же release; это не новая проба.

- P038: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Демонстрационный селектор — fake_selector.py

Места: P039 (строка 183).

Вход и домен: Пример вызова в __main__.

Потребление: Печать примера; не самостоятельный production semantic consumer.

Заключение: Исключён из числа смысловых проб. Сценарный ответ проверяет маршрутизацию, не качество модели.

- P039: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Встраиваемый исполнитель — kernel.py

Места: P040 (строка 54), P041 (строка 58).

Вход и домен: ProbeLimits, чужой ProbeExecutor; max_calls/input/prompt/time; select/propose_local forwards.

Потребление: run_native возвращает state/metrics; ядро само не пишет память.

Заключение: Транспортная граница. Временной лимит проверяется между вызовами; timeout одного вызова — обязанность host transport. Внешний executor остаётся предпосылкой.

- P040: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P041: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Ранжирование лексики — lexical_embedding.py

Места: P042 (строка 66).

Вход и домен: После seal только KNOWN candidates; vector scores, размерности, протокол receipt.

Потребление: Порядок вариантов в predicate_value; OPEN сохраняется; все IDs остаются.

Заключение: Не смысловая проба. Сходство не выбирает значение; failure возвращает исходный порядок, integrity error не маскируется. client.embed — отдельная внешняя граница AUX1.

- P042: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Вспомогательный naming API — naming_probe.py

Места: P043 (строка 83).

Вход и домен: Selected source ranges/values + контекст; JSON NAME_VALUE/OTHER_PREDICATION/UNCLEAR.

Потребление: Возврат NamingReading; штатный caller run_naming; production caller из src не найден.

Заключение: Отдельный протокол, не 0/?. В NAME_VALUE выбирается строка, не ID вхождения; для цели value это может быть эквивалентно, для identity provenance недостаточно. Сфера применимости должна быть явно ограничена.

- P043: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## TP и финальная лексика — native_frontend.py

Места: P044 (строка 548), P045 (строка 570), P046 (строка 1076).

Вход и домен: legacy TP bounded schema/graph; current predicate specs после структуры, references и release checks.

Потребление: _validate hypotheses → frames; prepared lexical candidate → RESOLVED; build_plan.

Заключение: F05/F08: accepted TP singleton обходит дополнительный semantic selector, корректность лежит на producer+validator. OPEN singleton сохраняет исходный предикат и не доказывает словарную эквивалентность. Лексические definitions обязательны для KNOWN.

- P044: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P045: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P046: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Инвентарь именных функций — nominal_functions.py

Места: P047 (строка 34), P048 (строка 52), P049 (строка 58), P050 (строка 79), P051 (строка 86).

Вход и домен: Function kind → exact function source_set → head → reference identity/external case; завершение DONE.

Потребление: prepositions/reference_groups/quantity_groups/predicate exclusion/constraints.

Заключение: F11/F12/F14: signature/prepared, retirement и отрицательное завершение. Многословная функция может быть разрывной; запрет повторения ограничен occurrence+function.

- P047: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P048: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P049: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P050: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P051: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Референтная именная группа — nominal_reference_groups.py

Места: P052 (строка 82).

Вход и домен: При prepared — rows; иначе ресурс determiner/identity markers и вопрос REFERENCE/OTHER.

Потребление: Морфологическая маркировка → lexical unit.reference_constraint → memory resolver.

Заключение: F11/F12 для общего маршрута; F05 для ресурсного. OTHER сохраняет исходные токены, не отождествляет с UNKNOWN. SAME — ограничение, не установленный референт.

- P052: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Память референтной группы — nominal_reference_memory.py

Места: P053 (строка 68).

Вход и домен: Local spatial anchors + frozen active memory; максимум 32; label/type/features; SAME/CONTEXTUAL constraint.

Потребление: nominal_reference_bindings с receipt → native_plan → nominal_reference_binding.validate.

Заключение: F03: source_context/memory_excerpt обычных rows не выводятся явно в options, хотя вопрос ссылается на excerpts. Полный сырой источник не заменяет прошлый источник. Unresolved может стать типизированным placeholder, а не новой установленной идентичностью.

- P053: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Вспомогательное расширение словаря — open_set_probe.py

Места: P054 (строка 65).

Вход и домен: Gate NO_CANDIDATE + slot meaning + определения существующих значений; один JSON proposal.

Потребление: maybe_extend → verify_proposal → provisional ValueProposal; не auto schema/write.

Заключение: F08: propose_value сам не проверяет вхождение grounding_text, это делает verify_proposal. Обход maybe_extend требует явного статуса UNVERIFIED; название/докстринг promise сильнее постусловия функции. Production caller из src не найден.

- P054: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Граница разбиения — partition_domain.py

Места: P055 (строка 108).

Вход и домен: Источник, relation proof, owner, constraints, marker proofs; complete/partial predicates без языковой догадки.

Потребление: source_set → confirm_partition → dispatcher PARTITION; ContentRequired/revise loop.

Заключение: F07/F14: часть read_proof подписок есть, но empty proof может переживать отзыв страницы. resolve callbacks раскрыты в CLOSURE; finite loop не доказывает полноту всех разбиений.

- P055: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.

## Пересмотр функции — partition_role_revision.py

Места: P056 (строка 58).

Вход и домен: Exhausted restricted first-piece domain; только исключившие occurrences proofs; исходный источник.

Потребление: Меняет branch-local constraints/markers; supersede и dispatcher invalidation → новый partition.

Заключение: Нет права выводить ошибку из одного failed search; вопрос это сохраняет. F07: доступен лишь для данного триггера, не всех поздних конфликтов.

- P056: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Пересмотр владения — partition_sequences.py

Места: P057 (строка 24), P058 (строка 55).

Вход и домен: Уже выбранные части, последняя EXHAUSTED область, исходные roles и доступные refs.

Потребление: callback select(index,groups) → новое назначение; retirement suffix; preserve prefix; feedback.

Заключение: P057 — callback производителя частей, не внешний LLM. F07: repairs только после конкретного исчерпания; несколько номеров означают альтернативные следующие ремонты, не совместную правку.

- P057: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P058: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Старый schema pipeline — pipeline.py

Места: P059 (строка 626).

Вход и домен: Все schema candidates заданной arity; фиксированные participants/context; bounded attempts.

Потребление: T3 Decision → T4 cluster/value grounds/search completeness; run возвращает state, не native write.

Заключение: F08: отдельный путь повтора и отчётности. Не смешивать его T4 с native_frontend. Прямой импорт API возможен; bootstrap native использует v7_pipeline.

- P059: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Предикат/роль/чтение — predicate_functions.py

Места: P060 (строка 21), P061 (строка 76), P062 (строка 99), P063 (строка 123).

Вход и домен: Source predicates, excluded owned refs; roles из registry минус reserved; linked morphology; omitted subject presence.

Потребление: role retention → binding domain → frames; head proof; subject slot → implicit resolver.

Заключение: F05/F12: исключение по stale function inventory возможно на локальной границе. Owner-derived singleton имеет проверяемый LexicalRoute, не F01. Роль и личное употребление разделены.

- P060: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P061: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P062: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P063: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Транспорт провайдера — provider_adapter.py

Места: P064 (строка 163).

Вход и домен: Capability, budget, ordinal, prompt/params digests; replay exact bytes; self.transport.

Потребление: ProviderUnavailable/IntegrityError/raw → выбранный codec; WAL received/failed.

Заключение: Не доказывает семантику. Внешний callback transport обязан возвращать str. Общая запись transport не означает, что вспомогательные public APIs используют этот adapter.

- P064: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Количество — qualitative_quantity.py

Места: P065 (строка 52).

Вход и домен: Общий источник из nominal_functions либо ресурсные candidates; OTHER; сохраняется выражение, не вычисленное число.

Потребление: Внешний падеж, quantity expression и internal readings → nominal units → qualitative group entity.

Заключение: F11/F12 для общего пути; F05 для ресурсного. Числовой смысл и неизвестные члены не выдумываются. Полнота quantity-expression семантики отдельно от границ.

- P065: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Квантор — quantifier_composition.py

Места: P066 (строка 117).

Вход и домен: Released или structural marker/head/partition proof; source binder variable; distinct binder constraints.

Потребление: restriction+body с одной bound_var → quantifier licensed → native compiler.

Заключение: Положительная защита: singleton с head_license реально проверяется. F05/F09: nonnumeric ENTITY-domain; нельзя распространять достаточность на числа/высшие кванторы. Старый ресурсный путь зависит от lexicon.

- P066: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Системный prompt и backend — real_backend.py

Места: P067 (строка 92), P068 (строка 115), P069 (строка 118).

Вход и домен: SelectionPrompt.selection_audit выбирает отдельный system; generation parameters; per-run adapter.

Потребление: backend.generate → ProviderAdapter → codec; immutable logging identity.

Заключение: AUX transport; проверка должна включать system+prompt, не один question. Live reliability этой модели не проверена статическим аудитом. Число output tokens не меняет допустимые IDs.

- P067: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P068: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.
- P069: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Описание имени — refinement_boundaries.py

Места: P070 (строка 9), P071 (строка 14), P072 (строка 23), P073 (строка 30), P074 (строка 74), P075 (строка 105).

Вход и домен: Общий source_set + binding kind + marker/extend; legacy morphology starts/endpoints.

Потребление: Выбранный boundary → parent → host → child → nominal_args.

Заключение: F05: legacy ограничивает starts/endpoints; общий маршрут сохраняет source_set. Отказы блокируют refinement, не подтверждают отсутствие описания. Контракт binding kind не равен выбранному host.

- P070: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P071: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P072: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P073: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P074: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P075: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Совместимость старых структур — region_probes.py

Места: P076 (строка 45).

Вход и домен: Одинаковые node inventories/morph, максимум восемь и четыре delta edges; различимые labels.

Потребление: Выбранная гипотеза отсекает другие accepted; caller в production src не найден.

Заключение: Compatibility-only; отсутствие найденного caller не доказательство недостижимости public API. Морфологические отличия явно блокируются, не скрываются.

- P076: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Общее внешнее отношение — relation_composition.py

Места: P077 (строка 119), P078 (строка 168), P079 (строка 195), P080 (строка 235), P081 (строка 320), P082 (строка 357), P083 (строка 372), P084 (строка 411), P085 (строка 457).

Вход и домен: RELATIONS → partition/owner/role/governor/control/typed child; lexical route отдельно.

Потребление: Рекурсивная структура → scope validations → lexical specs → native_plan.

Заключение: F05/F07/F15: полный домен лишь для перечисленных типов; content_role сужает roles/attitudes по неполной лексике; generic holder subject не выбран пробой. Отказ конкретного partition не доказывает неверность relation.

- P077: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P078: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P079: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P080: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P081: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P082: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P083: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P084: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P085: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Функция отдельного вхождения — relation_markers.py

Места: P086 (строка 43).

Вход и домен: ONE source token; relation/owner/parts; сохранённые marker proofs.

Потребление: RELATION_ONLY сохраняется; CONTENT → ContentRequired → partition recompute.

Заключение: Хорошо адресованный предмет вопроса, не утверждение готовности всего split. F07/F14 требуют полного основания read_proof и его page closure.

- P086: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Производители частей — relation_partitions.py

Места: P087 (строка 14), P088 (строка 43), P089 (строка 73), P090 (строка 82), P091 (строка 104).

Вход и домен: unary, binary/IF_ELSE, content owner-first, group; excluded/covered/must_include и source_set.

Потребление: PartitionProposal → confirm_partition → recursive children.

Заключение: F05/F07: физическое покрытие токенов не равно смысловой полноте. QUERY удаляет знаки вопроса, GROUP допускает конкретную пару скобок; эти области должны оставаться явными.

- P087: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P088: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P089: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P090: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P091: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.

## Общий nonnumeric binder — relation_quantifiers.py

Места: P092 (строка 12), P093 (строка 19), P094 (строка 35).

Вход и домен: Quantifier words, shared occurrence vs separate mention, nominal head; PartitionDomain.

Потребление: Вызов quantifier bind → restriction/body; descriptions перенесены в restriction.

Заключение: F09: NUMR/Anum в marker даёт ARITHMETIC_QUANTIFIER_DEFERRED. Правильный ответ нельзя принуждать к другой категории ради успешной сборки.

- P092: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P093: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P094: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Временное событие-имя — relative_composition.py

Места: P095 (строка 40).

Вход и домен: ScopeLexicon TEMPORAL_NOMINAL, preposition+nominal cases, bounded endpoints.

Потребление: EVENT_DESCRIPTION child + PROPOSITION parent → BEFORE/AFTER/DURING + source_projection.

Заключение: F05: ресурсный генератор; source_projection отдельно guard-ится assertion scope в source_assertions. Номинальный якорь не становится автоматически фактом.

- P095: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Относительная роль — relative_pronoun.py

Места: P096 (строка 21), P097 (строка 27), P098 (строка 42).

Вход и домен: Заданный host; general semantic role, whole marker reading либо legacy case role combinations.

Потребление: Projected host binding → child → ровно один host_frame; identity исходного mention сохраняется.

Заключение: F05/F06: роль и чтение выбираются раздельно; второй вопрос не явно повторяет выбранную роль. Нужна семейная обязанность достаточности входа, иначе повторное свободное решение.

- P096: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P097: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P098: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Область модификатора — scope_assignment.py

Места: P099 (строка 190).

Вход и домен: Existing typed tree positions + peer modifiers, atomic boundaries, graph constraints.

Потребление: Выбранные immediate edges → assembled topology/contents → frame scopes/native_plan.

Заключение: F16: SHARED_COORDINATION_V1 просит предпочтение при нескольких совместимых scopes. Это policy preference, не доказанное исключение локального прочтения; final contract должен сохранять этот статус.

- P099: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Формат ответа — selection_exchange.py

Места: P100 (строка 16).

Вход и домен: Исходный SelectionPrompt, schema/ids; один explicit format repair; total calls charged.

Потребление: Validated reply либо exception → _live_probe outcome; raw/failed попытки в history.

Заключение: Положительная граница: формат можно исправить, содержательный 0/? не переопрашивается как ошибка. Не доказательство правильности ответа.

- P100: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Ресурсные мягкие границы — soft_clause_boundaries.py

Места: P101 (строка 34).

Вход и домен: FINITE_SUBJECT_HINT_V2 или CAPITAL_FINITE_HINT_V1; morphological proposals, full sides.

Потребление: SPLIT→children; V2 unknown/limit→block; V1 unknown/limit→keep original area.

Заключение: F05/F08: mode-dependent guarantees; KEEP не следует из ?, но V1 лишь сохраняет исходную область для следующего разбора. Не объявлять само сохранение ошибочным утверждением.

- P101: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Первичные области — source_areas.py

Места: P102 (строка 41).

Вход и домен: SENTENCE windows + delimiter containment; JOIN/SEPARATE; calendar barriers.

Потребление: Combined area with pending flag → components; unknown не утверждает отдельные дети.

Заключение: F04/F05: контекст конечен; pending сохраняется. Общая source boundary проба не покрывает зависимости через неограниченный документ при конечном бюджете.

- P102: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Утверждаемость вложенного — source_assertions.py

Места: P103 (строка 58).

Вход и домен: Только существующие UNKNOWN modifier contents в asserted tree; не проходит через NOT/OR/report.

Потребление: SOURCE_ASSERTED receipt → roots → native_plan; tree equality проверяется.

Заключение: Положительные guards есть. F07: selected_candidate сам по себе не проверяет retirement; перенос источника и semantic scope должны быть зависимостями receipt. Не доказано, что stale projection достигает записи.

- P103: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Пространство — spatial_references.py

Места: P104 (строка 27), P105 (строка 42), P106 (строка 126).

Вход и домен: Function NONE/anchor/reference → role → source/memory places; grounded source anchor filter.

Потребление: selected_place → spatial_plan; coordinates UNKNOWN; explicit role conflict blocks.

Заключение: F04/F05: roles question не предъявляет явно уже занятые roles, проверка конфликта стоит после выбора. Это позднее обнаружение, а не разрешение модели заново менять назначения; нужна передача ownership.

- P104: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P105: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P106: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.

## Пагинация и source set — structural_tasks.py

Места: P107 (строка 103), P108 (строка 225), P109 (строка 243), P110 (строка 260), P111 (строка 264), P112 (строка 283), P113 (строка 299).

Вход и домен: Полный переданный iterator; per-page protocol; start/end/continuations; отдельный domain receipt.

Потребление: choose→value+proof; choose_domain→SupportedDomain; source_set→occurrences+proofs; licensed→consumer.

Заключение: F14 подтверждён: EMPTY хранит page_refs в STRUCTURAL_TASK, а licensed ищет связь через TASK_DOMAIN; retirement отрицательной страницы пропускается. Обычная положительная domain closure эту проверку имеет.

- P107: Один supported → provisional ID; 0/?/несколько/ошибка/лимит → None, различие в Decision/history/diagnostics. Эквивалентные refs могут иметь один доказанный entity_ref. Потребитель обязан прочитать статус, если маршруты различны.
- P108: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P109: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P110: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P111: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
- P112: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P113: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.

## Внешний boolean callback — tag_source.py

Места: P114 (строка 91).

Вход и домен: Injected subord_probe(word,context,occurrence,resource_version); морфологические/лексические gates.

Потребление: CONJ_SUB или coarse POS → clause_detection; if_bridge создаёт TagSource без callback.

Заключение: Не wire 0/?. Нет валидации типа callback; contract требует bool. hardcoded auto subordinators не соответствуют общему открытому языковому решению; не приписывать этот путь native GUI.

- P114: Собственный интерфейс или обёртка: результат и исключения описаны в семейной карточке; общий протокол 0/? сюда автоматически не переносится.

## Временная функция — temporal_functions.py

Места: P115 (строка 17), P116 (строка 35).

Вход и домен: First time occurrence → source_set; нормализация только после выбора; NONE завершает inventory.

Потребление: owned_refs excludes lexical tokens; frame snapshots; normalize → temporal_attachment/scope.

Заключение: F12/F14: active inventory/negative proof liveness. Нормализация отсутствующего формата возвращает UNSUPPORTED, не отвергает временную функцию. Частота/длительность могут требовать отдельной представимости.

- P115: Один supported → value+proof после закрытия страниц; 0 отвергает страницу, после всех страниц — empty/EXHAUSTED; ?/ошибка/лимит → None с отдельным журналом; несколько → pending или SupportedDomain только choose_domain.
- P116: Start/end/continuations дают конечный набор occurrences+proofs; UNKNOWN/неполнота не закрывают набор; 0 на continuation закрывает только проверенный остаток. Неполученная граница возвращает None.
