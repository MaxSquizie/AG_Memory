# P00 — исходные сбои и контракт дальнейшей проверки

Версия: `6ee7e64`; историческая база: `9b15de4`. Это завершение инвентаризации, не исправление runtime и не закрытие F05. Все 19 исторических failures воспроизведены: 19 failed / 17 passed (три целевых файла). Исторические 22 passes включали другой набор файлов; числа passes несопоставимы.

Команда, SHA256 исходников фикстур/проверок и фактический release hash и исходные журналы — `p00/manifest.json`. Полные окончательные prompts, raw responses, probe returns и native результаты всех 36 запусков: `p00/current_capture.json.gz` (JSON-массив, поиск по nodeid). Файл получен наблюдением, без замены ответов и без изменения assertions. Значения адресов Python в traceback не являются устойчивыми идентификаторами.

## Классификация

Ниже подтверждается первая причина текущего падения проверки. Она не доказывает исправность последующих стадий. INVESTIGATE отдельно обозначает незавершённую проверку семантики; её владелец и следующий эксперимент обязательны. Исходное ожидание сохраняется в указанном test node и в traceback capture. Нормативная база: V7 §§4.2–4.7 (целые чтения, структура, контекст), §5.2 (закрытый выбор), §§6.1–6.3 (смысл и область), §7 (запись). Порядок внутренних проб нормативным свойством не является.

## B01
`tests/test_composition_dispatcher.py::test_resolved_probe_rechecks_changed_parent_and_retains_exact_attempt`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший прямой вызов: _probe получает slot=test без inputs и без зарегистрированного семейства. PROBE_INPUT_CONTRACT содержит INPUT_CONTRACT_MISSING и PROBE_FAMILY_UNDECLARED; возврат None до selector. Prompt и ответа нет.

**Native:** не запускался; direct API probe отвергнут до модели.

**Следующее действие:** P00/P23: построить корректный адресованный вход через объявленное семейство, сохранив сравнения количества вызовов, зависимостей и revisions. P04/P19: затем проверить инвалидацию при смене parent/context и независимость descendant. Текущий failure ничего не говорит о корректности кеша после допуска.

## B02
`tests/test_composition_dispatcher.py::test_new_context_reopens_child_and_probe_but_unchanged_unknown_is_cached`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший прямой вызов: _probe получает slot=test без inputs и без зарегистрированного семейства. PROBE_INPUT_CONTRACT содержит INPUT_CONTRACT_MISSING и PROBE_FAMILY_UNDECLARED; возврат None до selector. Prompt и ответа нет.

**Native:** не запускался; direct API probe отвергнут до модели.

**Следующее действие:** P00/P23: построить корректный адресованный вход через объявленное семейство, сохранив сравнения количества вызовов, зависимостей и revisions. P04/P19: затем проверить инвалидацию при смене parent/context и независимость descendant. Текущий failure ничего не говорит о корректности кеша после допуска.

## B03
`tests/test_composition_dispatcher.py::test_real_agreement_repair_reaches_native_memory`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Неполный selector: correction выбирает красивую, predicate=читает, nominal_dependency выбирает ATTRIBUTE к книгу; последующий predicate_argument_role для красивый получает default 1 (OBJECT), хотя корректный ответ в wire — вариант 19 NO_DIRECT_ROLE. Затем COMPONENT_DEPENDENCY_CONTRADICTION и незапланированный structural_revision → ?.

**Фактический native:** `[{"diagnostics": {"codes": ["COMPONENT_DEPENDENCY_CONTRADICTION", "SPEECH_ACT_UNRESOLVED"]}, "assertions": []}]`

**Следующее действие:** P23: явно выбрать NO_DIRECT_ROLE для зависимого прилагательного и проверить исходный oracle записи correction. P02/P04/P16: INVESTIGATE — почему повторный выбор роли допускает конфликт с принятой ATTRIBUTE; проверить prerequisites/совместный домен, не запрещать читать зависимое в контексте.

## B04
`tests/test_composition_dispatcher.py::test_parent_feedback_does_not_reask_unchanged_descendant`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший прямой вызов: _probe получает slot=test без inputs и без зарегистрированного семейства. PROBE_INPUT_CONTRACT содержит INPUT_CONTRACT_MISSING и PROBE_FAMILY_UNDECLARED; возврат None до selector. Prompt и ответа нет.

**Native:** не запускался; direct API probe отвергнут до модели.

**Следующее действие:** P00/P23: построить корректный адресованный вход через объявленное семейство, сохранив сравнения количества вызовов, зависимостей и revisions. P04/P19: затем проверить инвалидацию при смене parent/context и независимость descendant. Текущий failure ничего не говорит о корректности кеша после допуска.

## B05
`tests/test_oov_paradigm_forms.py::test_native_unproved_forms_do_not_merge_symbols_or_events`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший словарь scripted selector: ожидается VERB: либо NOUN:, а wire показывает finite verb: либо noun:. Script.generate не находит startswith, возвращает 0 и НЕ снимает шаг. Следующая structural_relation получает ?. Первое нарушение — перевод семантического сценария в wire-ответ, а не порядок вопросов.

**Фактический native:** `[{"diagnostics": {"codes": ["OOV_GRAMMAR_UNRESOLVED", "OOV_KEEP_AS_IS", "STRUCTURAL_TASK_UNRESOLVED", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P00/P23: адресовать финальные человекочитаемые варианты функции (finite verb/noun), запрещать незаявленный default на семантических слотах. Сохранить все проверки отсутствия predicted lemma, отдельных wordforms, query/NOT и persistence. P01–P03/P16: повторить после корректного selector; downstream остаётся INVESTIGATE.

## B06
`tests/test_oov_paradigm_forms.py::test_analyzer_predictions_never_enter_semantic_prompts`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший словарь scripted selector: ожидается VERB: либо NOUN:, а wire показывает finite verb: либо noun:. Script.generate не находит startswith, возвращает 0 и НЕ снимает шаг. Следующая structural_relation получает ?. Первое нарушение — перевод семантического сценария в wire-ответ, а не порядок вопросов.

**Фактический native:** `[{"diagnostics": {"codes": ["OOV_GRAMMAR_UNRESOLVED", "OOV_KEEP_AS_IS", "STRUCTURAL_TASK_UNRESOLVED", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P00/P23: адресовать финальные человекочитаемые варианты функции (finite verb/noun), запрещать незаявленный default на семантических слотах. Сохранить все проверки отсутствия predicted lemma, отдельных wordforms, query/NOT и persistence. P01–P03/P16: повторить после корректного selector; downstream остаётся INVESTIGATE.

## B07
`tests/test_oov_paradigm_forms.py::test_predicted_lemma_and_features_cannot_change_the_interpretation[change0]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший словарь scripted selector: ожидается VERB: либо NOUN:, а wire показывает finite verb: либо noun:. Script.generate не находит startswith, возвращает 0 и НЕ снимает шаг. Следующая structural_relation получает ?. Первое нарушение — перевод семантического сценария в wire-ответ, а не порядок вопросов.

**Фактический native:** `[{"diagnostics": {"codes": ["OOV_GRAMMAR_UNRESOLVED", "OOV_KEEP_AS_IS", "STRUCTURAL_TASK_UNRESOLVED", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P00/P23: адресовать финальные человекочитаемые варианты функции (finite verb/noun), запрещать незаявленный default на семантических слотах. Сохранить все проверки отсутствия predicted lemma, отдельных wordforms, query/NOT и persistence. P01–P03/P16: повторить после корректного selector; downstream остаётся INVESTIGATE.

## B08
`tests/test_oov_paradigm_forms.py::test_predicted_lemma_and_features_cannot_change_the_interpretation[change1]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший словарь scripted selector: ожидается VERB: либо NOUN:, а wire показывает finite verb: либо noun:. Script.generate не находит startswith, возвращает 0 и НЕ снимает шаг. Следующая structural_relation получает ?. Первое нарушение — перевод семантического сценария в wire-ответ, а не порядок вопросов.

**Фактический native:** `[{"diagnostics": {"codes": ["OOV_GRAMMAR_UNRESOLVED", "OOV_KEEP_AS_IS", "STRUCTURAL_TASK_UNRESOLVED", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P00/P23: адресовать финальные человекочитаемые варианты функции (finite verb/noun), запрещать незаявленный default на семантических слотах. Сохранить все проверки отсутствия predicted lemma, отдельных wordforms, query/NOT и persistence. P01–P03/P16: повторить после корректного selector; downstream остаётся INVESTIGATE.

## B09
`tests/test_oov_paradigm_forms.py::test_surface_lexeme_keeps_negation_and_query_anchor`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший словарь scripted selector: ожидается VERB: либо NOUN:, а wire показывает finite verb: либо noun:. Script.generate не находит startswith, возвращает 0 и НЕ снимает шаг. Следующая structural_relation получает ?. Первое нарушение — перевод семантического сценария в wire-ответ, а не порядок вопросов.

**Фактический native:** `[{"diagnostics": {"codes": ["OOV_GRAMMAR_UNRESOLVED", "OOV_KEEP_AS_IS", "STRUCTURAL_TASK_UNRESOLVED", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P00/P23: адресовать финальные человекочитаемые варианты функции (finite verb/noun), запрещать незаявленный default на семантических слотах. Сохранить все проверки отсутствия predicted lemma, отдельных wordforms, query/NOT и persistence. P01–P03/P16: повторить после корректного selector; downstream остаётся INVESTIGATE.

## B10
`tests/test_oov_paradigm_forms.py::test_nominal_oov_preserves_mention_without_inventing_a_paradigm`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Устаревший словарь scripted selector: ожидается VERB: либо NOUN:, а wire показывает finite verb: либо noun:. Script.generate не находит startswith, возвращает 0 и НЕ снимает шаг. Следующая structural_relation получает ?. Первое нарушение — перевод семантического сценария в wire-ответ, а не порядок вопросов.

**Фактический native:** `[{"diagnostics": {"codes": ["OOV_GRAMMAR_UNRESOLVED", "OOV_KEEP_AS_IS", "STRUCTURAL_TASK_UNRESOLVED", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P00/P23: адресовать финальные человекочитаемые варианты функции (finite verb/noun), запрещать незаявленный default на семантических слотах. Сохранить все проверки отсутствия predicted lemma, отдельных wordforms, query/NOT и persistence. P01–P03/P16: повторить после корректного selector; downstream остаётся INVESTIGATE.

## B11
`tests/test_nominal_predication_tasks.py::test_nominal_predicate_uses_subject_and_copula_agreement[\u0418\u0432\u0430\u043d \u2014 \u0432\u0440\u0430\u0447.-ivan]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первый семантически неверный ответ сценария: predicate_function получает незаявленный default 1 → «Иван» вместо «врач». В фактическом component_attachment меню нет предиката врач: сценарий уже выбрал другую голову. Первый pytest failure — неизрасходованный шаг component_attachment в helper. Вторичная латентная несовместимость [NOUN] / [noun] установлена статически, но её вклад надо проверять после исправления выбора головы. QUERY/CONTENT не исправляет неверный дочерний выбор.

**Фактический native:** `[{"diagnostics": {"codes": []}, "assertions": [{"predicate": "OPEN:иван", "roles": {"AGENT": {"unbound_ref": "M:2e25d5496bfbc2f7445ce22afebf8953c25be5dcb6dab86dccf506a4e800a370", "kind": "M"}}}]}]`

**Следующее действие:** P23: явно задать врач на predicate_function, затем адресованные роли и noun attachment; сохранить DOCTOR/THEME, QUERY без assertion и CONTENT только внутри SAY. P09/P10/P16: downstream INVESTIGATE, особенно copula и STRUCTURAL_IMPLEMENTATION_GAP; успешный сценарный ответ не доказывает source closure.

## B12
`tests/test_nominal_predication_tasks.py::test_nominal_predicate_uses_subject_and_copula_agreement[\u041c\u0430\u0440\u0438\u044f \u0432\u0440\u0430\u0447.-maria]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первый семантически неверный ответ сценария: predicate_function получает незаявленный default 1 → «Мария» вместо «врач». В фактическом component_attachment меню нет предиката врач: сценарий уже выбрал другую голову. Первый pytest failure — неизрасходованный шаг component_attachment в helper. Вторичная латентная несовместимость [NOUN] / [noun] установлена статически, но её вклад надо проверять после исправления выбора головы. QUERY/CONTENT не исправляет неверный дочерний выбор.

**Фактический native:** `[{"diagnostics": {"codes": []}, "assertions": [{"predicate": "OPEN:мария", "roles": {"AGENT": {"unbound_ref": "M:34f7cd5ebe31ffa49240e03ca857196869812f93e9980a40f167cc3d110ea823", "kind": "M"}}}]}]`

**Следующее действие:** P23: явно задать врач на predicate_function, затем адресованные роли и noun attachment; сохранить DOCTOR/THEME, QUERY без assertion и CONTENT только внутри SAY. P09/P10/P16: downstream INVESTIGATE, особенно copula и STRUCTURAL_IMPLEMENTATION_GAP; успешный сценарный ответ не доказывает source closure.

## B13
`tests/test_nominal_predication_tasks.py::test_nominal_predicate_uses_subject_and_copula_agreement[\u041c\u0430\u0440\u0438\u044f \u0431\u044b\u043b\u0430 \u0432\u0440\u0430\u0447\u043e\u043c.-maria]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первый семантически неверный ответ сценария: predicate_function получает незаявленный default 1 → «была (быть)» вместо «врач». В фактическом component_attachment меню нет предиката врач: сценарий уже выбрал другую голову. Первый pytest failure — неизрасходованный шаг component_attachment в helper. Вторичная латентная несовместимость [NOUN] / [noun] установлена статически, но её вклад надо проверять после исправления выбора головы. QUERY/CONTENT не исправляет неверный дочерний выбор.

**Фактический native:** `[{"diagnostics": {"codes": []}, "assertions": [{"predicate": "OPEN:быть", "roles": {"AGENT": {"entity": "maria"}, "EXPERIENCER": {"unbound_ref": "M:ee84d7a939a387a5acf849345d5abaf20c057cef7025813b1c649d28e5dfa0fc", "kind": "M"}}}]}]`

**Следующее действие:** P23: явно задать врач на predicate_function, затем адресованные роли и noun attachment; сохранить DOCTOR/THEME, QUERY без assertion и CONTENT только внутри SAY. P09/P10/P16: downstream INVESTIGATE, особенно copula и STRUCTURAL_IMPLEMENTATION_GAP; успешный сценарный ответ не доказывает source closure.

## B14
`tests/test_nominal_predication_tasks.py::test_nominal_predicate_uses_subject_and_copula_agreement[\u0418\u0432\u0430\u043d \u0431\u044b\u043b \u0432\u0440\u0430\u0447.-ivan]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первый семантически неверный ответ сценария: predicate_function получает незаявленный default 1 → «был (быть)» вместо «врач». До component_attachment выполнение не дошло; native сообщает STRUCTURAL_IMPLEMENTATION_GAP. Первый pytest failure — неизрасходованный шаг component_attachment в helper. Вторичная латентная несовместимость [NOUN] / [noun] установлена статически, но её вклад надо проверять после исправления выбора головы. QUERY/CONTENT не исправляет неверный дочерний выбор.

**Фактический native:** `[{"diagnostics": {"codes": ["STRUCTURAL_IMPLEMENTATION_GAP", "STRUCTURE_NOT_COVERED"]}, "assertions": []}]`

**Следующее действие:** P23: явно задать врач на predicate_function, затем адресованные роли и noun attachment; сохранить DOCTOR/THEME, QUERY без assertion и CONTENT только внутри SAY. P09/P10/P16: downstream INVESTIGATE, особенно copula и STRUCTURAL_IMPLEMENTATION_GAP; успешный сценарный ответ не доказывает source closure.

## B15
`tests/test_nominal_predication_tasks.py::test_nominal_predicate_under_question_is_not_forced_to_be_event_noun`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первый семантически неверный ответ сценария: predicate_function получает незаявленный default 1 → «Иван» вместо «врач». В фактическом component_attachment меню нет предиката врач: сценарий уже выбрал другую голову. Первый pytest failure — неизрасходованный шаг component_attachment в helper. Вторичная латентная несовместимость [NOUN] / [noun] установлена статически, но её вклад надо проверять после исправления выбора головы. QUERY/CONTENT не исправляет неверный дочерний выбор.

**Фактический native:** `[{"diagnostics": {"codes": ["SPEECH_ACT_QUERY"]}, "assertions": []}]`

**Следующее действие:** P23: явно задать врач на predicate_function, затем адресованные роли и noun attachment; сохранить DOCTOR/THEME, QUERY без assertion и CONTENT только внутри SAY. P09/P10/P16: downstream INVESTIGATE, особенно copula и STRUCTURAL_IMPLEMENTATION_GAP; успешный сценарный ответ не доказывает source closure.

## B16
`tests/test_nominal_predication_tasks.py::test_reported_nominal_predicate_is_only_content`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первый семантически неверный ответ сценария: predicate_function получает незаявленный default 1 → «Мария» вместо «врач». В фактическом component_attachment меню нет предиката врач: сценарий уже выбрал другую голову. Первый pytest failure — неизрасходованный шаг component_attachment в helper. Вторичная латентная несовместимость [NOUN] / [noun] установлена статически, но её вклад надо проверять после исправления выбора головы. QUERY/CONTENT не исправляет неверный дочерний выбор.

**Фактический native:** `[{"diagnostics": {"codes": []}, "assertions": [{"predicate": "SAY", "roles": {"AGENT": {"entity": "ivan"}, "CONTENT": {"predicate": "OPEN:мария", "roles": {"AGENT": {"unbound_ref": "M:8eb2b79b86157ab2e523be6109edf89ef8aed2e3754a90443ad79252075c0a28", "kind": "M"}}}}}]}]`

**Следующее действие:** P23: явно задать врач на predicate_function, затем адресованные роли и noun attachment; сохранить DOCTOR/THEME, QUERY без assertion и CONTENT только внутри SAY. P09/P10/P16: downstream INVESTIGATE, особенно copula и STRUCTURAL_IMPLEMENTATION_GAP; успешный сценарный ответ не доказывает source closure.

## B17
`tests/test_nominal_predication_tasks.py::test_incomplete_or_mismatched_nominal_predication_cannot_assert[\u041c\u0430\u0440\u0438\u044f \u0432\u0440\u0430\u0447\u043e\u043c.]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Первое pytest падение — helper assert not script.steps: DEFER остался в очереди. Семантический assert not assertions ещё не исполнен. Отдельное native наблюдение против ожидаемого no-write: Мария врачом. записывает DOCTOR(THEME=maria), хотя сценарий ожидает DEFER. component_candidates: условие проверки instrumental без copula защищено not general, поэтому общий путь его обходит. Это подтверждённая смена допуска, но не доказательство ошибочности русского прочтения.

**Фактический native:** `[{"diagnostics": {"codes": []}, "assertions": [{"predicate": "DOCTOR", "roles": {"THEME": {"entity": "maria"}}}]}]`

**Следующее действие:** P15/P16/P23, архитектурный вопрос: допускается ли эллиптическая связка в изолированном ASSERTION и каким основанием? Сопоставить полное/эллиптическое/неопределённое употребление, явный отказ и ?; не превращать один падеж в универсальный запрет. До уточнения oracle и correctness — INVESTIGATE, менять ожидаемую запись запрещено.

## B18
`tests/test_nominal_predication_tasks.py::test_incomplete_or_mismatched_nominal_predication_cannot_assert[\u0412\u0440\u0430\u0447.]`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Неполный сценарий: predicate_subject_presence получает default OMITTED; итог STRUCTURAL_IMPLEMENTATION_GAP/SPEECH_ACT_UNRESOLVED без записи. structural_revision вообще не вызвана, объявленный DEFER остаётся в очереди.

**Фактический native:** `[{"diagnostics": {"codes": ["SPEECH_ACT_UNRESOLVED", "STRUCTURAL_IMPLEMENTATION_GAP"]}, "assertions": []}]`

**Следующее действие:** P23/P15/P16: ответить на наличие подразумеваемого субъекта явно; сохранить no-write для неразрешённости, не требовать конкретную внутреннюю revision-пробу. Различить фрагмент-описание и предикацию. Дальнейшая реализация отсутствующего пути INVESTIGATE.

## B19
`tests/test_nominal_predication_tasks.py::test_model_can_reject_nominal_predication`

**История:** FAILED на 9b15de4; **сейчас:** FAILED на 6ee7e64.

Отказ component_attachment=0 получен; результат без записи, STRUCTURAL_IMPLEMENTATION_GAP/SPEECH_ACT_UNRESOLVED. Падает требование израсходовать structural_revision=DEFER, которого текущий маршрут не спрашивает.

**Фактический native:** `[{"diagnostics": {"codes": ["SPEECH_ACT_UNRESOLVED", "STRUCTURAL_IMPLEMENTATION_GAP"]}, "assertions": []}]`

**Следующее действие:** P23: сохранять отрицательный oracle no-write; доказать состояние открытого/отвергнутого домена по trace вместо обязательного DEFER. P08/P20: проверить отсутствие скрытого завершения и возможность адресованного пересмотра.

## Почему P00 не сводится к зелёному pytest

Три direct API сценария не дошли до модели; шесть OOV остановлены ошибочным wire matching; шесть положительных nominal-сценариев не задали выбор головы; agreement имеет конфликт двух заданных ответов; два отрицательных nominal-сценария остановились без записи, но ждут другой маршрут; один instrumental-сценарий реально записал факт вопреки oracle. Итого 19. Ни одна проверка не удалена и ожидания не изменены. Прогон с исправленным селектором обязателен в P23 и профильных карточках, прежде чем делать вывод о runtime после первой границы.

Связь с registry: direct/cache → C-GROUNDS/C-CACHE; OOV → C-OOV/C-READINGS; nominal/agreement → C-LEXICAL/C-ROLES/C-CHILD/C-CLOSURE; отрицательные исходы → C-RETRACT/C-PUBLICATION.

## Приёмка

2026-11-01, тот же судья `/root/f05_coordinator`: **ACCEPT — P00, инвентаризация**. Проверены 52 capability, 20 relations, 19/19 failures и hashes. Блокеров P00 нет. Runtime и assertions не исправлялись; downstream INVESTIGATE остаётся открытым. Следующий этап — P20-contract, затем P01.
