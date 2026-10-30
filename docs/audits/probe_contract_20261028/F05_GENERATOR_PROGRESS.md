# F05: формирование гипотез — границы генераторов

29 октября 2026. Статус: открыта. Работа переключена с F07/F12 на F05.

## Исправленные исключения исходных кандидатов

### Связанное упоминание квантора

Цепочка: relation_quantifiers.compose → structural_binder_head → compose_child → quantifier_composition.bind.

До изменения structural_binder_head допускал только owned-вхождения с вариантом NOUN/NPRO. На этом уровне ещё не построен дочерний разбор. Отсутствие такого варианта у OOV или контекстуального употребления не доказывает невозможность именного употребления. Правильный адрес мог отсутствовать ещё до запроса.

Теперь binder_candidates перечисляет все owned-вхождения, сохраняя их разные адреса даже при одинаковом написании. Установленное владение материалом сохраняется: исключённые из owned слова не возвращаются. Выбор адреса не устанавливает морфологию. bind по-прежнему требует соответствующее аргументное вхождение и именное чтение в дочернем разборе. Если дочерний алгоритм не построил такое чтение, остаётся QUANTIFIER_HEAD_UNRESOLVED.

Необходимость: вхождение без NOUN/NPRO могло иметь допустимую функцию, но не попадало в вопрос. Локальная достаточность: каждый owned-адрес достижим в перечислении независимо от морфологии. Это не доказательство полноты дочернего морфологического/аргументного генератора и не расширение модели ограничения квантора за пределы NOUN/NPRO.

### Пространственные ссылки на исходные якоря

Цепочка: spatial_references.prepare → options/context_range → resolve → выбранное место.

До изменения набор ограничивался якорями перед ссылкой внутри половины context_chars. Отсутствие далёкого или последующего якоря не отражалось в search_incomplete: лимит проверялся уже после отсечения. Это могло оставить единственный удобный вариант вместо полного набора известных исходных мест.

source_candidates теперь сохраняет все произведённые исходные якоря, кроме собственного вхождения ссылки. Контекст включает их общий диапазон и целевую область. Прежние ограничения количества и размера теперь применяются к расширенному набору и дают SEARCH_INCOMPLETE; кандидаты не удаляются ради помещения в бюджет. Само включение последующего якоря не устанавливает тождество: выбор остаётся за пробой с контекстом, а resolve требует установленного якоря.

Локальная достаточность: расстояние/направление больше не отсекает произведённый якорь. Не доказаны полнота производства якорей, доступность всей памяти или разрешимость произвольной взаимной ссылки. При длинном источнике новая версия может честно остановиться там, где старая выбирала по неполному окну. Постраничная обработка такого контекста ещё не реализована.

## Карта следующих обязательств F05

| Генератор | Фактическая область и компенсация | Остаток |
|---|---|---|
| ScopeLexicon | Ограниченные словарные совпадения. В structural-режиме relation_composition до лексического маршрута предлагает типы связей без требования совпадения слова с ресурсом | Типы RELATIONS сами конечны; наличие общего маршрута не доказывает полноту их представления. Legacy-режим не получает автоматически этих гарантий |
| Именная координация | component_nominal_groups: соседние слова вокруг словарного AND, согласуемые падежи. OTHER переводит к coordinate | Общего генератора произвольных составных именных участников этим не доказано. AND в RELATIONS означает связь пропозиций и не компенсирует автоматически именную группу |
| Уточняющее описание | NOMINAL_DESCRIPTION вызывает general_boundary/source_set; адресные начала и концы доступны без списка маркеров. Legacy select использует морфологические начала | Проверить три типа binding, представимость безглагольных описаний, ограничения хозяев после дочернего разбора. Общая граница не гарантирует полноту всех этих потребителей |
| Кванторы | Общий structural маршрут выбирает FORALL/EXISTS и исходный материал; адрес связанного упоминания больше не ограничен предварительным NOUN/NPRO | Морфологический NUMR/Anum guard, дочерние чтения и head_pos в bind остаются ограничениями. Арифметические кванторы явно отложены; произвольную полноту не заявляем |
| Пространственные ссылки | Общая spatial_function проба дополняет ресурсные правила; все произведённые исходные якоря теперь доступны до бюджета | Полнота якорей, grounded-фильтр, общий механизм больших контекстов, циклические ссылки |
| Именные ссылки | nominal_reference_memory объединяет local_rows и активную память, явно останавливается при лимите | local_rows пока только предыдущие пространственные якоря; это не все исходные сущности. Полнота объединения с памятью не доказана |

## Проверки

check_f05_source_domains использует настоящий choose/codec со сценарным ответом: два одинаково написанных OOV сохраняют разные варианты, выбран второй адрес, но без дочернего именного чтения restriction не создаётся. Проверены далёкий, близкий и последующий пространственные якоря, исключение собственного вхождения, независимость копии и превышение бюджета полным диапазоном.

Повторно прошли check_spatial_source_context и три check_content_reference_contrasts. Это локальная проверка доменов и сценарные сквозные контрасты; живой исполнитель, полноценный кванторный OOV-разбор до записи и GUI не проверялись. F05 не закрывается этими результатами.

## Продолжение: корректность отсечения по падежам координации

Обнаружен разрыв producer/consumer: component_phrases.role_choices допускает именное CONTEXTUAL-чтение с неизвестным падежом, но component_nominal_groups.select, dependency_constraints.compatible и component_candidates трактовали отсутствие падежей как несовместимость. Это исключало вариант не из-за доказанного конфликта, а из-за недостающей информации.

Введён единый критерий совместимости падежных доменов. None означает неизвестный домен, пустое пересечение известных доменов — противоречие. Неизвестность допускается только у CONTEXTUAL-чтений, как и в role_choices; пустые DICTIONARY/PREDICTED чтения этим изменением не лицензируются. Все три границы используют согласованный смысл. Ограничение группы может содержать известный общий падеж, но не присваивает его отдельному неизвестному чтению. Установление роли остаётся отдельным обязательством.

Объединение предложенных рёбер одной AND-группы теперь вычисляет все связные компоненты, а не объединяет только с первой пересекающейся группой. Контрольный порядок AB, CD, BC прежде оставлял перекрывающиеся ABC и CD; теперь образуется ABCD. Это проверка общего сборщика, а не утверждение о воспроизведённом таком порядке в нынешнем последовательном генераторе соседних слов.

Проверка check_f05_coordination_domains независимо перебирает все комбинации трёх падежных доменов над {nom, acc, dat}, включая неизвестные и ограничения группы. Эталон — существование конкретного падежа, удовлетворяющего всем известным ограничениям. Проверены оба направления: каждый совместимый набор сохраняется, каждый несовместимый отсекается. Дополнительно проверены все порядки трёх рёбер, неподмена исходных данных, реальный DomainNetwork, запрет двух негруппированных ROOT в одном слоте, а также producer с контролируемым ответом NOMINAL. Последний сценарий не является живым модельным вызовом.

Локальная достаточность относится только к существованию общего падежа в уже заданных доменах. Совпадение падежей не доказывает языковую координацию. Неизвестное ещё не означает подтверждённое; отсутствие конфликта оставляет гипотезу для следующей проверки. Полнота самого набора чтений, несоседние/составные именные группы и отсутствие словарного маркера остаются открытыми. F05 не закрыта.

## Структурный режим: адресованный состав именной координации

Для CLOSED_RELATIONS_V1 component_nominal_groups больше не строит группу из before[-1]/after[0]. После обнаружения конкретного исходного AND-маркера nominal_coordination_scope устанавливает его функцию (именная группа либо другая область). Затем общий source_set собирает головы всех участников этой группы, включая разрывный набор и более двух участников. Участники перечисляются по исходным адресам без предварительного POS-фильтра. Описания остаются вне выбранного набора голов и доступны последующему разбору. Формулировка не объявляет одинаковые имена одним референтом.

Место этапа: после выделения текущей области, до именных функций, морфологических уточнений и назначения ролей. Известны исходные вхождения и конкретный маркер; ещё нет установленных именных чтений и ролей. Поэтому сборщик проверяет принадлежность адресов, исключение занятого маркера и минимум двух участников, а не выдумывает их падежи. cases=None сохраняется до проверки реальных чтений в потребителе. Ложный положительный ответ исполнителя не превращает неименное чтение в именное: соответствующие участники должны пройти обычный clause/dependency контур.

OTHER возвращает управление прежнему маршруту другой области. Неопределённый ответ либо незавершённый сбор возвращает False и блокирует текущую композицию; fallback к ближайшим словам отсутствует. Для legacy-режима прежний контракт сохранён явно: эта миграция относится к структурному режиму.

Каждая группа сохраняет scope proof и CollectionReceipt, включая отрицательное подтверждение завершения. При объединении пересекающихся групп сохраняются все свидетельства. Проверка live сопоставляет точный состав участников/маркеров со свидетельствами; compose_alternatives проверяет их до использования, frame_live — на существующих границах последующих проб и native_plan. Отзыв подтверждения завершения блокирует также сохранённую копию группы. Служебные source_evidence исключены из языковой сигнатуры composition_equivalence, но сохраняются на выбранном представлении.

Контекстуальный производитель падежных чтений вызывается после выбора участников; его прежние предложения не потеряны. contextual_name_case.overlay теперь объединяет предложения от всех участников, а не перезаписывает по token_ref последней строкой. Эти предложения по-прежнему не являются установленными морфологическими фактами.

check_f05_addressed_coordination проверяет реальный choose/source_set/числовой codec: несоседние головы, три участника, OOV, повторное написание, запрет завершить группу с одним участником, различие OTHER и ?, изменение копии, отзыв отрицательного завершения, сохранение альтернативных контекстуальных чтений. Это сценарные ответы, не живая LLM. Дополнительно прошли проверки падежных доменов, три content-reference контраста.

Остаток: запуск пока зависит от найденного словарного AND-маркера. Бессоюзные группы, другие типы именной координации и произвольная вложенная структура групп этим не покрыты. Не доказан полный разбор описаний всех выбранных участников до записи: здесь доказаны достижимость адресов и согласованность нового контракта с проверками потребителей. F05 остаётся открытой.

## Продолжение: обнаружение без словарного маркера

Предыдущее ограничение запуска снято в CLOSED_RELATIONS_V1: component_refinement вызывает генератор в каждой текущей лексической области, а component_nominal_groups передаёт управление discover до обращения к ScopeLexicon. Legacy-путь остался отдельным. Пустой словарь не исключает ни явную неизвестную связку, ни бессоюзную группу.

nominal_coordination_discovery — типизированный NEXT: очередная плоская группа совместных участников, неподдержанная вложенная/альтернативная структура либо отрицательное завершение. После выбора группы source_set собирает её головы. Затем nominal_coordination_marking выбирает наличие отдельного связующего материала; SOURCE вызывает сбор всех его вхождений вне голов, NONE сохраняет пустой marker_refs. Гипотеза совместной группы не предполагает заранее наличие слова «и» или запятых. Отрицательный исход на этапе обнаружения не заменяет неизвестный ответ.

Пересекающиеся группы не объединяются молча: повтор того же состава даёт NO_PROGRESS, иной пересекающийся состав — STRUCTURE_UNSUPPORTED. Несколько непересекающихся групп сохраняются отдельно. Вложенная/альтернативная семантика явно распознаётся как пока непредставимая данным производителем, без сведения её к плоскому AND. Это фиксация ограничения, а не реализация вложенных групп.

После отрицательного завершения все группы сохраняют coordination_completion. Проверки потребителей требуют это основание вместе с исходными коллекциями; его удаление/отзыв блокирует копию. Во время внутреннего сбора разрешена только явная проверка collecting=True, которая не используется потребителями. Завершение зависит от положительных оснований всех предшествующих групп. Бюджет числа групп даёт SEARCH_INCOMPLETE, а не ложное завершение. Для области без групп добавляется одна адресованная проба обнаружения.

Расширенный check_f05_addressed_coordination выполняется с пустым ScopeLexicon и реальными choose/source_set/codec. Проверены явная связка, отсутствие связки, два независимых состава, отрицательное завершение, неподдержанная структура, неизвестный ответ, минимальная мощность, отзыв завершения, подмена состава и отсутствие морфологического продвижения OOV. В синтетическом state поднят только лимит вызовов до 100, чтобы проверить цепочку из более восьми шагов; runtime-политика бюджета не изменялась. Подтверждены также прежняя проверка падежных доменов, три content-reference сценария и PARTIAL без записи. Эталоны этих сквозных сценариев не изменены: их существующий сценарный исполнитель отвечает 0 на новую необязательную задачу, что соответствует их текстам.

F05 остаётся открытой: вложенные/альтернативные именные группы, полнота дочернего разбора участников, ограничения кванторов/описаний/референции. Для нового бессоюзного состава проверена реальная цепочка генерации и лицензирования, но не сквозная запись с живой моделью.

## Кванторное значение и именные альтернативы

Согласованное пользователем представление именных альтернатив: логическая область над вариантами пропозиции, с сохранением общих участников, описаний и областей действия; не выбор одного участника и не совместная K-группа альтернатив.

### Кванторы

Удалён NUMR/Anum-veto из relation_quantifiers: наличие любого числительного морфологического варианта больше не объявляет выбранное употребление арифметическим. structural_quantifier_kind выбирает смысл конкретного исходного выражения (NONNUMERIC/ARITHMETIC) с сохранением proofs его границ. Арифметический исход по-прежнему явно отложен; 0, ?, множественность не становятся нечисловым прочтением. Выбор функций источника зависит от этой пробы. quantifier_composition проверяет основание до построения restriction и при последующем licensed. Прежний снимок общего квантора без такого основания требует пересчёта.

check_f05_quantifier_kind проверяет настоящий codec: нечисловое употребление при наличии NUMR/Anum, числовое значение без такого морфологического варианта, отрицательный/неизвестный/множественный ответы и отзыв основания. Четыре целевых сквозных проверки (Каждый/Любой/Некоторый и Два) прошли. В их сценарии добавлены ответы на новую пробу и уже существующий quantifier_source_functions; обновлена ранее изменённая подпись выбора головы. Семантические ожидания и запрет записи арифметического разбора не изменялись.

### Общий исходный материал альтернатив

Ранее binary-разбиение требовало непересекающихся исходных частей. В «Иван или Пётр придёт» это оставляло предикат лишь одному ребёнку; второй ребёнок не имел полного исходного содержания. Удалить запрет пересечения без основания было бы ошибкой.

Теперь после выбора частей OR/XOR и уточнения внешних связующих слов structural_shared_material спрашивает о материале, выраженном один раз, но принадлежащем внутрь каждой альтернативы. source_set адресованно собирает этот материал; вопросы явно запрещают копировать оператор, относящийся к альтернативе в целом. Общие вхождения добавляются обоим детям без генерации нового текста. У каждого ребёнка обязательно остаётся собственный материал. Отсутствие ответа не запускает догадку; отрицательный ответ сохраняет прежнее непересекающееся разбиение.

PartitionProposal хранит shared_material. confirm_partition разрешает повторное вхождение только для OR/XOR, при живом proof и CollectionReceipt, точном совпадении множества повторов с выбранным материалом и его наличии во всех детях. Произвольные повторы, исчезновение общего вхождения и ребёнок без собственного материала отклоняются. Предикат не превращается во внешний маркер. Подтверждение разбиения получает эти основания как prerequisites, поэтому отзыв распространяется на его proof. Дети рекурсивно проходят общий compose_area, результат собирается существующим G-оператором OR/XOR.

check_f05_shared_alternative выполняет два сценария до реальной native-записи: «Иван или Пётр придёт» → один OR из ARRIVE(Иван) и ARRIVE(Пётр); «Иван и Мария или Пётр и Анна придут» → один OR над двумя ARRIVE с отдельными совместными группами. Анна в используемом ресурсе остаётся исходно введённой M без канонического имени; это не заявление об установлении её тождества известной сущности. Проверены также запрет неподтверждённого пересечения, пустой отличающейся ветви, утраты общего вхождения и отзыв proof. Исполнитель сценарный, не живая LLM. Content-reference контрасты повторно прошли.

### Незакрытый остаток

Этот блок устраняет конкретное препятствие общего разбиения и поддерживает проверенную вложенность OR над совместными группами. Он не доказывает полноту любого дерева именных отношений. Внутренний COMPLEX-исход плоского производителя по-прежнему не создаёт несуществующее представление; корректная внешняя логическая область должна быть выбрана раньше. Не проверены все случаи общих описаний, разных уровней модальности и кванторного связывания при повторном использовании исходного материала.

По reference-семейству остаётся ограничение nominal_reference_local: только предыдущие пространственные якоря и активная память, не все упоминания текущего источника; durable-валидатор требует соответствующее основание. Его нельзя безопасно расширить одним добавлением строк в options. Полнота host/reading-генераторов описаний тоже требует дальнейшей проверки. F05 полностью не закрыта.

### Дополнение: домен владельцев описания

`refinement_boundaries.agreeing` теперь использует общий контракт падежных доменов: CONTEXTUAL без падежа — неизвестность; непересекающиеся установленные домены — конфликт. `refinement_group_hosts` сохраняет это различие при сборке целого владельца-группы и допускает владельца после описания в структурном режиме. Исходные чтения не изменяются; неизвестный падеж не записывается как установленный. Старый postnominal-маршрут остаётся явно ограниченным.

`check_f05_refinement_hosts.py`: независимый конечный перебор доменов для отдельных и групповых владельцев, известный конфликт числа/падежа, неизвестность, препозиция и отсутствие мутаций — PASS. Это проверка генератора, не доказательство сквозной поддержки всех типов описаний.

Дополнительные проверки: 7 адресованных сценариев бинарных связей и относительного ограничения квантора — PASS; сквозной сценарий NOT(OR(ARRIVE(Иван), ARRIVE(Пётр))) — PASS: внешнее отрицание не распределено по ветвям. Ранее выполнены 4 проверки семантики кванторов, контрасты CONTENT/reference и сохранение PARTIAL. Живая модель и GUI в этом изменении не проверялись.

F05 остаётся открытой: обычные именные ссылки требуют расширения локального домена вместе с его доказательствами и потребителем записи; произвольное рекурсивное сочетание групп и описаний пока не покрыто. Подмена этого остатка флагом завершения недопустима.

## F05: объединение источников именной ссылки и актуальность результата

Обнаружено и исправлено в `nominal_reference_local`, `nominal_reference_memory`, `nominal_reference_binding`:

- Пространственный кандидат исключался по позиции целого frame относительно начала предложения ссылки. Это удаляло независимые якоря в том же предложении и после ссылки. Теперь исключается собственное вхождение из anchor_refs/head_ref. Валидатор записи использует ту же границу; терминальная привязка SPATIAL_ANCHOR остаётся обязательной, поэтому временной порядок текста не заменяет защиту от самоподдержки.
- Генератор требовал точного sense_id и терял уже установленные generic spatial slots. Он теперь учитывает их generic-контракт и проверяет актуальность функций/владельцев frame.
- Отсутствующее чтение памяти ошибочно считалось завершённым пустым источником. Теперь отсутствие receipt, неполное чтение, превышение лимита кандидатов и контекста не разрешают выбор из усечённого объединения.
- Производная nominal_reference_bindings сохраняла прошлую привязку после неудачного повторного выбора или удаления задачи. Проход пересобирает её; при пропуске пробы снимает прежний успешный статус решения, сохраняя историю.
- Потребитель плана проверяет выбранного кандидата, исходное ограничение, сигнатуру структуры, зафиксированное чтение и актуальность конкретного локального/внешнего основания. Изменённый результат не превращается в прежнюю известную идентичность. Старые незаписанные снимки без этих свидетельств требуют повторного разрешения.

Место механизма: после определения функций/структуры и разрешения пространственных якорей, на объединении локального источника и frozen active-workspace read; непосредственно перед C/T5 выполняется повторная проверка использованных оснований. Здесь доступны и типизированные исходные кандидаты, и receipt памяти. Лексическая генерация не должна решать межупоминательную идентичность.

Проверки: `check_f05_nominal_reference_domain.py` использует реальный reference probe/codec над явно построенными frames, выбирает последующий generic-якорь, проверяет валидатор записи, самоадресацию, отсутствующее/изменённое чтение, отзыв решения, изменение структуры, неразрешённый якорь, ответы 0/?/несколько альтернатив и удаление задачи — PASS. `check_spatial_source_context.py` — PASS. Два адресованных native-сценария shared_function_and_head_remain_selectable — PASS. Это не живой прогон модели и не сквозная запись нового разговорного примера.

Остаток F05: генератор обычных локальных именных референтов (не только пространственных), поддержка их оснований вплоть до записи; рекурсивное сочетание групп и описаний. Карточка не закрыта. Расширение пространственного домена не выдаётся за полноту всех локальных референтов.

## F05: обычные исходные сущности и описание целой группы

Обычные терминальные ENTITY-упоминания из принятого разбора теперь доступны `nominal_reference_memory` вместе с пространственными якорями и памятью. `nominal_reference_source` берёт установленные аргументные роли без предварительного NOUN-фильтра и без ограничения по позиции/расстоянию. Разные вхождения одинакового написания сохраняются. Кандидат содержит frame/token/mention, текущую сущность и сигнатуру исходных оснований. Это область терминальных введений M: связанные переменные, EVENT/K-ссылки, неразрешённые ссылки и другие referential constraints требуют своих маршрутов и этим изменением не объявляются поддержанными.

`nominal_entity_plan.operations` выделен из native_plan без изменения обычного представления сущности: он сохраняет исходную идентичность, свойства величины/группы, морфологические признаки и основания. Один и тот же компилятор используется для обычного аргумента и предварительной материализации выбранного локального основания. Поэтому ссылка на более позднее упоминание не зависит от порядка обхода frames. Сначала создаётся терминальная привязка, затем NOMINAL_REFERENCE на неё. Проверяется актуальность производителя до плана и тип/идентичность/основания терминальной привязки в durable-валидаторе; reference-binding не может служить терминальным якорем этого маршрута. Сохраняются все premise_support_refs, а не только первый.

На границе группы и описания обнаружены три несогласованности. Целая группа предлагалась только для PARTICIPLE, хотя BOUND_DESCRIPTION умеет задавать невыраженную роль владельца. При переносе группы очищались marker_refs, из-за чего терялось соответствие source_evidence. Представление структуры показывало служебный host_token_ref группы как несуществующее слово. Теперь BOUND_DESCRIPTION допускает целого владельца-группу, переносит его состав и свидетельства, а последующие вопросы видят реальные исходные вхождения всех участников. Это не реализация всех видов рекурсивной координации или группового RELATIVE_PRONOUN.

Проверки: `check_f05_source_nominal_write` — три сквозные native-записи: Иван до ссылки; Иван после ссылки; новая неназванная канонически сущность «студент». В каждой ARRIVE и SLEEP используют одну и ту же M, без второй сущности для «этот человек». `check_f05_source_nominal_domain` — повторяющиеся OOV, отсутствие выдуманной морфологии, тождество обычных/якорных операций, исключение собственной ссылки и запрет подменить связанную переменную либо неразрешённую ссылку терминальной M; отзыв исходного решения. `check_f05_group_description` — native-запись «Прочитавшие книгу Иван и Мария спят» с общей K-группой и NOMINAL-связью описания на K в журнале, без самостоятельного утверждения READ. Сценарные ответы; живого исполнения моделью не было.

Общий остаток ведётся в F05_STATUS.md. Ни первый блок целиком, ни вся F05 этим изменением не закрыты.

## F05: группа как владелец относительного описания

Генератор владельцев теперь предлагает целую установленную группу для RELATIVE_PRONOUN. Выбранная группа передаётся в relative_pronoun.compose и в общий механизм проекции владельца; состав и исходные lexical_units сохраняются вместо обращения к синтетическому group id как к одному слову. Групповая проекция сохраняет marker_ref и выбранное чтение относительного слова. role_readings использует его при проверке внутренней роли каждого члена, не переписывая исходный падеж участников в родительской конструкции.

Выявлен сопутствующий разрыв: пробы роли/чтения проверялись только сразу после дочерней композиции. Теперь их proofs сохраняются на refinement_binding; frame_hosts_live проверяет актуальность обоих оснований, совпадение роли и чтения, назначения всем членам. Отзыв основания, удаление сохранённых proofs или подмена роли не дают повторно использовать такой результат. Это распространяется и на обычного одиночного владельца структурного относительного описания; legacy ресурсный путь остаётся отдельным.

check_f05_group_relative: два сквозных сценария без пунктуационных подсказок — «Иван и Мария которые прочитали книгу спят» и «Иван и Мария которых Пётр видел спят». До native-записи дошёл SLEEP с одной K-группой; журнал содержит NOMINAL-связь на эту K с внутренним SUBJECT/OBJECT соответственно. Исходные morph_bindings членов совпадают с родительскими. На реальном захваченном state после прогона проверены удаление proofs, подмена роли, supersede основания и отказ frame_hosts_live. Проверка одиночного относительного ограничения квантора также прошла. Исполнитель сценарный, живой модели не было.

F05 остаётся открытой; текущий остаток всех шести блоков — F05_STATUS.md. Это расширение одного общего маршрута, не доказательство полноты произвольной рекурсии.

## 2026-10-29 — produced nominal domain, page evaluation, consumer evidence

Root gaps: nominal_reference_memory discarded a union over 32 rows; its late consumer checked the frozen memory read and selected local anchor, but did not compare other produced local candidates. A competing source candidate could change without invalidating the identity choice. The fixed 2048-character gate also rejected context independently of the executor's actual prompt budget.

Placement: after accepted structure/lexical source introductions and frozen memory reads are available, before publishing nominal_reference_bindings. `nominal_reference_domain.snapshot` freezes the actual entity/place/memory row union plus constraint/read. The same producer runs after evaluation and in `nominal_reference_binding.payload` before native plan construction. No source is generated from a model response.

`nominal_reference_pages` assesses all supplied candidates in pages (initial size 32), retaining full source and structural inputs. NONE_FIT rejects a page only; unknown, failed, or budget-limited pages cannot support union uniqueness. Different admissible identities remain alternatives; proofs with the same established entity_ref may select a representative. Oversized prompts split only candidate lists; even one candidate with irreducibly excessive context remains incomplete. The failed oversized request stays in its page audit record; successful subdivision removes its provisional terminal diagnostic. No model call is spent on a rejected oversized prompt.

The parent result retains every evaluated leaf page, including negative pages. Before write, both page records and decision evidence must remain live. Dispatcher machine-state/lifecycle/search bookkeeping does not count as changed evidence. Changed selected grounds, superseded records and withdrawn results do. An explicit speaker choice is a separate C ground and must still match the current produced domain.

Validation (scripted, not live model): `check_f05_nominal_pages.py` covers late candidate, competing positive pages, ?, all 0, multiple on one page, equivalent identities across pages, retired negative proof, adaptive prompt splitting, irreducible prompt limit, and exhausted call budget after a positive page. `check_f05_nominal_reference_domain.py` covers the real owner/codec/payload over 67 rows and context >2048 characters, competing-source changes, mutation during a call, stale page/read/selection, and removed tasks. `check_f05_source_nominal_write.py` passes all three prior native write scenarios (known/new source M, earlier/later source). `git diff --check` passes.

Scope: exhaustive evaluation of the PRODUCED_REFERENCE_UNION only. `search_complete` is deliberately not set as a language/interpretation completeness certificate. Whole K candidates, reference chains, bound variables, unfinished source introductions, and completeness of source production remain F05 work. Other producers' explicit search_incomplete flags, including the spatial reader's own cap, still block identity selection; this change does not silently override them. No GUI or live Luna result is claimed.

## 2026-10-29 — whole terminal K referents from source through memory/write/query

Root mismatch: nominal-reference memory could already supply GROUP rows, but the native write/compiler path treated every nominal reference as M. Current-source groups had no nominal-reference producer or durable member-dependent introduction. Adding an option alone would leave a selectable but unwritable target.

Placement and domain: `nominal_group_source` consumes accepted flat nominal coordination, the resolved predicate's exact same-role membership, and terminal M rows from the existing entity producer. It preserves individual options and adds the whole K. No grouping is inferred from adjacency, spelling, plurality alone, or an alternative proposition. No positional window is used. Missing members, bound/reference-dependent members, retired source grounds and self-containing candidates do not manufacture a K introduction. Unknown morphology is not a veto: distinct OOV occurrences remain distinct members.

The existing native K uid/content convention is reused. A NOMINAL_GROUP_ANCHOR carries source/member anchors and durable member binding refs. Normal group writes publish this introduction even without a reference in the same input. Referencing an earlier/later source group uses the same terminal member compiler; writing the reference preserves K instead of attempting ENSURE_ENTITY. Adapter validation checks target type, group contents and live member bindings. CanonicalLedger propagates member withdrawal through the group anchor and its dependent nominal references. The produced-union/page certificates introduced in the previous change include group rows automatically.

Frozen active-workspace GROUP rows retain their type and membership through nominal selection and receipt validation. Query projection now uses the established nominal binding; the compiler accepts a K only with the declared exact member set and canonical K identity. A group query does not assert a group event. This also fixes the existing ordinary GROUP_REFERENCE query path's unconditional M-only check.

Evidence: `check_f05_group_nominal_domain.py` checks repeated OOV members, individual+whole candidates, self exclusion, exact role membership, bound member exclusion, retired coordination/source evidence and durable transitive member withdrawal. `check_f05_group_nominal_write.py` checks both source orders for «Иван и Мария пришли и эти люди спят», then a second observation with the real frozen active K (explicit attention seed), then query compilation of that K without a new assertion, plus rejection of altered query membership. The script explicitly chooses the indicative прийти reading of ambiguous «пришли»; default option 1 was imperative прислать, which is not an oracle for this sentence. All are scripted native/codec checks, not live Luna or GUI trials.

Regression scope: prior 3 ordinary-M source writes, group bound description, 2 group relative-role writes, produced-domain 67-row check and page-contract checks. Remaining: nonterminal/member-reference chains, mutual references, bound-variable targets, recursive groups, source production completeness and broader query construction are not solved by this flat terminal K extension. F05 stays open.

## 2026-10-29 — source mention chains and established function ownership

Root cause: the reference domain required an already grounded terminal identity, so a referential source mention could never be selected as an intermediate antecedent. Resolving mentions in traversal order would make forward dependencies fail and tempt ungrounded cycle promotion.

The domain now separately represents REFERENCE_MENTION candidates, addressed by source occurrence and selected structure. Their `selection_target` is an internal mention key, never an M/K identity and never written as one. They are produced before reference results, so the union snapshot does not recursively depend on the very bindings it is trying to establish. Probes explicitly distinguish selecting an expression's referent from establishing that referent's terminal identity. Existing terminal options remain present. Shared heads are retained; a mention cannot select itself via overlapping owned occurrences.

After every nominal choice has been evaluated, `nominal_reference_chain.finish` propagates grounded terminal M/PLACE/K bindings through uniquely selected mention edges with a dependency queue. Processing order is irrelevant; no model answer or arbitrary iteration/depth cap establishes identity. Unsupported or ambiguous parents remain unavailable. Rootless cycles preserve their supported mention choices and dependency trace but produce no grounded nominal binding. These are partial interpretation outcomes, not proof of no viable linguistic reading.

Consumers validate the full upstream chain iteratively: every parent selection/page/domain, source anchor and binding hash must remain live. The common reference writer emits parents before dependents and preserves M/K types. Dependency writes reuse entity compilation and the same selected measure mapping as ordinary writes. Durable NOMINAL_REFERENCE receipts validate the exact parent binding and retain the ledger anchor edge. CanonicalLedger.binding_live now uses iterative DAG traversal, distinguishes a shared dependency from a cycle, and propagates withdrawal without Python recursion depth limits.

A new native K-chain scenario exposed a separate F05 generator violation: after source probes assigned «те» to the reference function of «те люди», morphology still generated dative «ты» as a RECIPIENT and changed READ to an open three-role predicate. Fixed at candidate generation: established non-head reference-function occurrences cannot independently become clause predicates/arguments or nominative utterance heads/dependencies. The exclusion comes from live addressed function ownership (including OOV), plus the existing legacy functional projection, not a marker-word list. The source stays readable, identical spelling elsewhere stays selectable, and shared function/head bearers remain nominal candidates.

Validation, all scripted/static rather than live Luna: `check_f05_reference_chains.py` passes two M source orders and a K chain through native write, then verifies parent-selection withdrawal; native mutual-cycle and unknown-parent scenarios produce no grounded nominal bindings. `check_f05_chain_dependencies.py` covers 1200 reversed source dependencies, K type retention, missing parents, cycles, 1600 durable links, shared DAG join and root retirement. These large checks exercise graph mechanisms, not natural-language parsing at that size. `check_f05_nominal_function_ownership.py` covers OOV ownership, a distinct identical occurrence and a shared head. Prior ordinary-M native writes, source-domain contracts, 67-row union contract, direct K source/memory/query writes and group-relative scenarios were checked for regressions.

Remaining: selection with multiple alternative mention edges is still ambiguous even if a future joint analysis could prove their terminal referents equivalent; this change does not silently pick an edge. Joint hypothesis search/revision, groups with nonterminal members, bound-variable reference targets, recursive groups and completeness of all source producers remain open. A rootless cycle's equality constraints remain in the interpretation trace; no new canonical identity is invented for it. F05 is not closed.

## 2026-10-29 — common dispatcher contract and scoped constraint-set reads

Following the review of distributed generators, work moved to the common composition boundary rather than another sentence-specific producer patch.

1. Dispatcher.run cached a task by its ordinary inputs but only stored ProducerContract on initial creation. A changed output sort/applicability/completion contract with unchanged inputs could reuse the old result and keep its consumers valid. Contract declarations now participate in invalidation, the stored kind/declaration is replaced, and a declaration whose kind disagrees with the task is rejected before execution.
2. Existing role/reading/host proofs were read individually. That does not subscribe a generator to a constraint added later, especially when its first read found no constraints. CONSTRAINT_SET is now a typed dispatcher read: exact region, current input-hypothesis scope, complete set of established role/partial-reading/nominal-host records and their liveness. Insertion, removal, replacement and retirement invalidate that read. Another region/hypothesis does not. A change during computation is caught before publication by the existing dependency-recheck loop. The checks and wording consumers register this read at their common access point.
3. Component alternatives checked roles/readings, while the grammar/component union additionally checked nominal functions. Both now call accepts_bundle for the same existing obligations. Function/quantity choices cannot disappear merely because no grammar alternative was present and the union's component-only route returned early.
4. produced() inferred search_complete=True from a plain return value or one root. It now leaves search completion false unless the producer returns an explicit TaskResult. Result shape and structure flags remain distinct from enumeration proof and write eligibility. Dispatcher traces state whether completion came from an explicit result or remains undeclared. This is not a blanket claim that every generator has now declared/proved its domain.

Placement: contract identity belongs in Dispatcher.run, not individual callers; dynamic constraint membership belongs in a scoped read, not a global syntax-trace hash or manual invalidation trigger; bundle obligations are shared before candidate selection/union. Existing producer algorithms and their separate search domains are retained.

Evidence: check_f05_dispatch_contracts.py covers contract changes and consumer invalidation, declaration-kind mismatch, plain versus explicit completion, an initially empty constraint set, insertion/removal/changed value/retired proof, unrelated areas/hypotheses, independent branches and mid-compute insertion. Six targeted dispatcher tests pass. One test adapter still expected the old dependency reducer's dict return: it now inspects every alternative in the already-existing list contract; its cache/revision expectations were not weakened. Native chain scenarios, cycles/unknown parents, direct K source/memory/query scenarios and two group-relative scenarios pass. No live-model/GUI claim.

Remaining integration obligations: explicit domain receipts for grammar/morphology/composition producers, coverage of constraints read outside these common helpers, reconciliation of producer applicability/completion at every union/early-return boundary, and transport of relevant obligations past the structural seal to final consumers. CONSTRAINT_SET currently covers role, partial-reading and nominal-host records; nominal/temporal inventories retain their own typed reads. Do not describe this as all generators already unified under a complete contract.


## F05: готовность дочернего результата при resume (29 октября 2026)

Причина: `ChildTasks.resume` снимал диагностики по одному корню; перед этим Dispatcher уже удалял диагностики предыдущего вычисления. Единственный корень мог содержать незакрытый CONTENT, цикл, частичный выбор или нерешённую пробу.

Изменение общего контракта: обычный возврат больше не объявляет структурную готовность, включая непроверенный partial record. ChildTasks выдаёт явный TaskResult после проверки выбранного дочернего графа существующим composition_tree.validate (слоты, ссылки, циклы, scope boundaries). Pending/blocked и частичные домены не получают готовность. Это проверка структуры на границе дочернего вычисления, где уже доступен граф, а не проверка лексической готовности или разрешение записи. Полнота поиска остаётся неизвестной. При незавершённом resume основания старой диагностики сохраняются в состоянии и учёте диспетчера; при закрытом результате снимаются.

Доказательства: check_f05_child_readiness.py проверяет закрытый результат и контрасты с отсутствующей/циклической ссылкой, незакрытым слотом, partial/domain, pending, budget; воспроизведена потеря диагностики до исправления. check_f05_dispatch_contracts.py PASS; 6 адресных тестов диспетчера PASS; check_f05_reference_chains.py PASS (сценарные ответы, native запись M/K, порядок зависимостей, цикл и неизвестный родитель). Живых вызовов модели и GUI не было.

Границы: не доказана полнота генераторов. Не изменён допустимый перенос частичных структур родителю; structure_complete означает проверенное закрытие выбранного графа, не полноту интерпретации. Явные основания исчерпания каждого производителя, все объединения и обязанности после seal остаются открытыми.


## F05: объединение производителей и неуспешная проекция грамматики (29 октября 2026)

Два общих разрыва. (1) composition_source_union удалял все новые диагностики при наличии корня; маршрут без grammar не проходил общую проверку ограничений и блокировок. Теперь обе ветки проверяют BLOCKED/SEARCH_INCOMPLETE общим контрактом produced, сохраняют кандидатов как незавершённые и проверяют accepts_bundle. Без grammar сохраняется прежняя передача компонентного домена без повторного выбора. Объединение не снимает чужие диагностики: для снятия требуется адресное основание у породившего их алгоритма. (2) CompositionSources отмечал проекцию выполненной до вычисления, а cached failure возвращался без диагностики при повторном входе. Успешная отметка перенесена после публикации; сохранённый SearchLimit/ProtocolError восстанавливает причину неполноты без повторного исполнения того же поиска. Неожиданное исключение не публикует успех.

Место изменений: объединение уже имеет результаты обоих источников и локальные диагностики; здесь нельзя превратить отказ источника в отрицательное свидетельство. Кэш проекции обязан сохранять результат вместе с причиной остановки независимо от последующей инвалидации диспетчера. Эти изменения не доказывают полноту открытого языкового домена.

Проверки: check_f05_source_union.py (контролируемые производители: обе ветки, бюджет/ресурсы/ошибка пробы, общие ограничения, чужая диагностика при одном корне, ошибка выбора); check_f05_grammar_failure.py (повторный вход после инвалидации и после неожиданного исключения); 7 адресных тестов диспетчера, включая перепроекцию при изменении чтения. Сценарные check_f05_reference_chains.py и check_f05_group_relative.py проходят до native-записи. Живой модели/GUI не было.

Остаток F05 не изменён по языковому охвату: альтернативные ссылочные зависимости, вложенные группы, расширение описаний, контекстуальные/OOV-кванторы, полнота источников и обязательства после seal. Не все ранние выходы всех производителей проверены.


## F05: чтение ограничения и использования связанной переменной (29 октября 2026)

Причины: legacy-проверка согласования трактовала неизвестный падеж как несовместимость; binder собирал чтения по отдельным использованным кадрам, выбирал одно, но связывал переменную во всех кадрах без проверки совпадения выбранных чтений. Поздний licensed проверял лишь attested, что допускало замену чтения ограничения другим, тоже засвидетельствованным.

Общий алгоритм: отсутствие признака не отсекает кандидата; известные несовместимые падежи отсекают. Неизвестность остаётся в предъявленном чтении, probe по-прежнему нужен. На границе bind уже выбран дочерний граф: кандидат должен сохранять выбранное целое чтение во всех использованиях того же source occurrence. Если общего чтения нет, QUANTIFIER_READING_UNRESOLVED без мутации bound_arguments; это не объявляет языковую гипотезу ложной, поскольку расхождения могут быть неизвестным признаком и его уточнением. Обход учитывает существующий budget. Лицензия сохраняет selected_reading и binding_slot; поздняя проверка сверяет точное чтение и ID выбранного кандидата. Произвольное слияние чтений и POS/лемм из OOV-прогнозов не добавлено.

Проверки: check_f05_quantifier_readings.py — неизвестный падеж доходит до реального codec пробы; 0/? не лицензируют; различающиеся чтения оставляют явную незавершённость без частичной мутации; подмена ограничения другим attested-чтением отклоняется. check_f05_quantifier_oov_write.py — сценарный native-прогон «Каждая флырка пришла.»: FORALL x (OPEN:флырка(x) IMPLIES ARRIVE(x)), совпадение AH/IR/journal, исходная неизвестность сохраняется в OOV_KEEP_AS_IS. Источник номинального чтения CONTEXTUAL. Прошли прежние source_domains/quantifier_kind и два адресных сценария: относительное описание в restriction и координированное тело под модальностью. Живой модели не было.

Остаток: этот пример подтверждает существующий OOV-путь до записи, не полноту всех OOV-употреблений. Совместное уточнение разных чтений одного вхождения, вложенные биндеры, связанные референциальные обращения, арифметические кванторы и полнота производства остаются открытыми.


## F05: шесть блоков и достижимость общего маршрута (29 октября 2026)

F05_STATUS дополнен критериями закрытия всех шести блоков, границами производителей/потребителей, обязательными контрастами и порядком крупных связанных работ 2+3+6, 1+4, 5+6. Карточка не сводится к улучшениям кэша и статусов.

Реализован переход, связывающий блоки 2 и 6: выбранный COMPLEX у плоского номинального производителя создаёт PRODUCER_UNSUPPORTED с актуальными доказательствами выбранного маршрута и capability-вопроса. Это не HYPOTHESIS_CONFLICT и не отрицание жизнеспособности интерпретации. Объединение источников сохраняет незавершённые кадры, но не маскирует такое основание общим PENDING, запрещавшим пересмотр. Существующая адресная проба ревизии решает, поддерживается ли иной структурный маршрут; автоматического OR/fallback нет. conflicts проверяет живость обоих оснований.

check_f05_complex_group_route.py: сценарный LEXICAL→COMPLEX→REVISE→OR с общим предикатом до native-записи; DEFER не пишет; ? при обнаружении группы не вызывает компенсирующего выбора. Это доказательство достижимости конкретного общего маршрута, а не всей рекурсивной грамматики.


## F05: зависимость описания от владельца и границ (29 октября 2026)

Блоки 3/6. component_refinement передавал host_token_ref в nominal_args без сохраняемого основания выбранного владельца; дочернее описание могло оставаться формально пригодным после отмены этого выбора. Теперь выбранная связь содержит receipt с source/version, точным candidate_id, fingerprint решения и структурными premises границы/связки. Receipt наследуют дочерние кадры, включая вложенные результаты. Проверка выполняется до присоединения, через frame_hosts_live у источников референтов и при native-планировании; чтение участвует в инвалидации диспетчера как REFINEMENT_HOST. Отзыв при явной ревизии поддержан discard_reads.

Место механизма — после выбранного владельца и до публикации связи: раньше владельца ещё нет; позже можно потерять зависимость при копировании дочернего графа. Механизм не выбирает владельца и не объявляет область вариантов полной. Ветка явных scope_assumption сохраняет собственный протокол; её полнота здесь не доказана.

Проверки: расширен check_f05_group_relative.py (субъект/объект группы, сохранение морфологии, отдельные отмены владельца, границы и внутренней роли, утрата receipt, изменение host_ref; повторное pure native-планирование после отмены владельца блокирует запись с NOMINAL_HOST_PROOF_RETIRED). check_f05_group_description.py проходит до записи; два адресных сценария кванторного restriction и модального тела прошли до добавления boundary-premises; проверка групп после добавления premises прошла. Проверки сценарные, без живой модели.

Открыто: полнота домена владельцев, несколько допустимых владельцев, прочие относительные связки и произвольная вложенность. Durable-отзыв уже записанного наблюдения остаётся отдельным протоколом версий; это изменение проверяет основания до следующей записи и при runtime-использовании.


## F05: группа — владелец описания через явную связку (30 октября 2026)

Блоки 2/3. Домен group_hosts ранее исключал RELATIVE, хотя существующий IR допускает общую номинальную группу в роли владельца связки. Теперь группа доступна во всех четырёх ветках описаний. В RELATIVE служебный group key остаётся адресом выбора: в participants/arguments, argument_token_refs, morph_bindings и lexical_units проецируются исходные члены существующим refinement_group_hosts.add_host. Сохраняются group membership proofs, многословная связка и вложенное proposition_args с UNKNOWN. Новая языковая эвристика/список связок не введены.

Первая проверка выявила ошибку seal: synthetic «Иван + Мария» оказался в исходных участниках. Исправлено на общей границе проекции группы. Для неоднозначного чтения связки теперь сохраняется relative_connector_reading: последующие frame_hosts_live проверяют актуальность пробы и точное совпадение чтения с выбранным candidate_id.

check_f05_group_connector.py: сценарные native-прогоны «Иван и Мария из-за которых Пётр ушёл спят.» и «Иван и Мария возле которых Пётр уснул спят.»; сохранён K-владелец NOMINAL usage link, полная связка, вложенное содержание без отдельной ассерции, исходные члены группы; отзыв владельца блокирует native-план, отзыв/подмена чтения связки блокирует её использование. Для «возле» ответ задан по реальному тексту пробы после выделения общей леммы. Прежний check_f05_group_relative.py также проходит. Живого вызова модели не было.

Остаток: все допустимые владельцы/несколько владельцев, произвольная вложенность групп и описаний, OOV-связки без подготовленного чтения и остальные пункты F05 остаются открытыми. Открытая лексическая связка не объявляется канонически эквивалентной причине или пространственному отношению.

## 2026-10-30 — адресные окна раскрытия: первая часть

Причина: синхронный вызов дочерней композиции смешивал требование результата
с неограниченным углублением текущего исполнения. На уровне ChildTasks уже
известны адрес, входы и родительский контракт; именно здесь введено окно 3.
Граница выбрасывает внутренний сигнал приостановки, а не пустой домен кандидатов.
Внешний драйвер разрешает только запрошенный путь; префикс переисполняется через
кэш диспетчера. Семантический выбор, pruning и receipts не подменяются разрешением
продолжения. Прерванный dispatcher node остаётся dirty, его результат не публикуется.

Проверки: четыре адресных pytest (глубина 7, смена родительского контракта,
бюджет, цикл); сценарный native до записи четырёх вложенных NOT над ARRIVE,
с фактическим переходом через окно; group_connector, shared_alternative,
child_readiness. В test_composition_dispatcher 13 проходят, 4 падают;
те же четыре сбоя воспроизведены в отдельном worktree исходного a70b95b.
Живой исполнитель не использован.

Остаток: выбор между открытыми структурными гипотезами до дораскрытия,
сохранение общего леса/обязательств и выполнение продолжений без рекурсивного
стека. Текущий demand-driven механизм является первой частью, не закрытием
согласованного алгоритма и не доказательством полноты генерации.

## 2026-10-30 — открытые домены и неизвестные требования родителя

Общий DomainNetwork используется согласованием грамматики, именных ролей,
чтений фраз, областей действия, кванторов и дочерних источников. Добавлен явный
контракт open_domains: отсутствие поддержки в ещё не перечисленном источнике
не отсекает кандидата. Совместимость None сохраняет кандидата и обязательство;
False остаётся доказанным конфликтом. Источник расширяется только пока открыт,
повторная страница не восстанавливает уже опровергнутый ID, изменение значения
под существующим ID запрещено. Явное ограничение выбора закрывает источник;
распространение ограничений сужает только перечисленную часть.

При исчерпании бюджета проверяемое ребро остаётся в очереди. До завершения
проверки этого ребра домен не изменяется. Snapshot разделяет оставшуюся очередь,
открытые источники и неизвестные обязательства. Завершение распространения
ограничений само по себе не доказывает совместную разрешимость/полноту языка.

Конкретный runtime-дефект: CompositionSources.retain исключал голову с
неизвестным падежом, если родитель требовал падеж. Теперь отсекается только
известное непересекающееся множество. Отсутствующее чтение/падеж сохраняет
кандидата с parent_slot_obligation; выбор единственного корня, выбор альтернативы,
проверка дерева и native planner не могут превратить это обязательство в факт.

Проверки: 14 целевых pytest (включая окна); native сценарии ссылочных цепочек,
групповых относительных описаний, OOV-квантора; quantifier_readings и source_union.
В старом test_joint_composition_domains 7 сбоев/3 прохода: те же результаты
в отдельном worktree исходного 54edbfd, ожидания не менялись. В выводе ссылочных
цепочек присутствуют дополнительные корневые AND/READ; идентичный вывод
подтверждён до окон на a70b95b. Поэтому успех проверки цепочек не доказывает
минимальность/правильность полного множества утверждений; этот вопрос открыт.

Граница выполненного: open_domains пока API общего движка, существующие
производители не объявлены открытыми автоматически. Для каждого ещё надо
передать реальные обязательства/продолжения; иначе это было бы выдуманной
полнотой или неоправданным изменением контракта. F05 остаётся открытой.
