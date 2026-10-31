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

## 2026-10-30 — реальный источник групп сообщает незавершённость

Первый подключённый производитель: nominal_group_source. Ранее отсутствие
терминальной идентичности хотя бы одного члена молча исключало всю группу,
а nominal_reference_domain учитывал неполноту только памяти. Теперь domain()
возвращает кандидатов и адресные обязательства: frame/role/member_refs,
pending_member_refs, group_hash и причину. Группа, включающая само разрешаемое
вхождение, исключается по прежнему контракту источников, а не считается
недостающим внешним кандидатом. Неоднозначная структура или неподдержанная
групповая идентичность также не выглядят завершённым пустым источником.

Общий eligible_frames используется источниками сущностей, групп и упоминаний,
чтобы входная готовность/живость не расходилась между производителями.
Объединение возвращает receipt с независимыми обязательствами LOCAL_GROUP
и ACTIVE_MEMORY. Его хеш входит в основание выбора; потребитель дополнительно
проверяет incomplete. resolve не отправляет неполное множество как закрытый
выбор и отзывает старый RESOLVED. Адресные причины доступны в syntax_trace.

Проверки: 4 целевых сценария производителя/объединения/resolve (появление
недостающего члена; самоссылка; независимые источники; отзыв старого результата
без вызова селектора). Сквозные сценарные проверки ссылочных цепочек и их
зависимостей. Без живой модели.

Это продвижение блоков 1/5/6. Формирование группы с нетерминальными членами
и возобновление после их разрешения ещё не реализованы: сейчас такой случай
честно остаётся неполным. Остальные источники не объявлены полными автоматически.

## 2026-10-30 — несколько шагов: зависимая группа до записи и отзыва

Причина прежнего ограничения: генератор требовал identity участников ещё до
выбора группы, а resolver/writer умели проходить только линейную цепочку.
Это смешивало адресованную структурную гипотезу и готовую идентичность.

1. nominal_group_source предлагает GROUP_MENTION, когда каждый недостающий
терминальный участник представлен допустимым reference-mention источником.
Кандидат хранит исходные адреса/роли/свидетельства, не меняется после grounding.
Неподдержанные виды участников сохраняют прежние открытые обязательства.
2. nominal_reference_memory сохраняет выбранную группу как зависимое решение.
Выбор группы не утверждает идентичности её членов.
3. nominal_reference_chain.finish обобщён до нескольких prerequisites: группа
готова только после всех выбранных ссылок. K содержит уникальные targets без
необоснованного разворачивания вложенного K; less-than-two остаётся unresolved.
4. payload и plan.emit обходят DAG итеративно; общий ребёнок не считается
циклом. Все reference-member bindings записываются до group anchor и ссылки.
Автоматическая публикация исходной группы использует тот же anchored K.
5. durable validator проверяет binding-kind/decision/mention/target/source-tag/
захваченный hash/live каждого ссылочного участника. Существующий ledger
member_binding_refs обеспечивает транзитивный отзыв без нового типа binding.

Проверки: целевые graph-тесты нескольких участников, порядка, пропавшего
участника, цикла, схлопывания идентичностей, вложенного K и подмены durable
оснований; прежние reference-source receipts/open domains/expansion tests.
Native сценарии с одним ссылочным участником в обоих порядках и двумя
ссылочными участниками; проверены роли SLEEP/READ, запись K и runtime/durable
отзыв. Негативный сценарий неизвестного участника проверяет отсутствие
группового identity binding. Существующие ссылочные цепочки и проверки
1200/1600 зависимостей сохранены. Живой модельный исполнитель не использован.
Один Astra medium субагент выполнил read-only аудит контрактов/диффа; это
статический анализ, не подмена прогонов.

Известный отдельный вопрос дополнительных корневых утверждений AND/READ
не исправлялся и не скрывается этими проверками. Полный F05 не закрыт.

## 2026-10-30 — сужение общих предикатов и основания частичного результата

Перед расширением частичных доменов обнаружен дефект общего фильтра:
compatible_bundle превращал bundle в dict predicate_token_ref→frame. Общий
предикат в разных ветвях терял все кадры, кроме последнего. Поэтому смена
порядка кадров могла как исключить жизнеспособную ветвь, так и скрыть конфликт.

Теперь сохраняются все кадры одного предикатного вхождения. Ограничение
адресуется использованиям конкретного token_ref через аргументы/выбранные
роли/морфологические привязки, а не всем контекстным токенам ветви. Каждое
такое использование проверяется; отсутствие обязательного использования
не становится успехом. NO_DIRECT_ROLE проверяется как запрет прямой роли;
если предъявлено ещё и чтение, оно тоже должно присутствовать. Для partial
reading domains проверяется также установленная роль, не только чтение.

В partial_composition parent_slot_obligation включено в basis и запрещает
structure_complete=True. validate повторно проверяет живость владельца/
относительной роли/чтения через общий frame_hosts_live. Это нужно именно
на границе передачи частичного результата: завершённая структура с
альтернативными чтениями не равна структуре с невыполненным условием слота.

Проверки: 6 целевых сценариев всех порядков общих кадров, отрицательной роли,
конфликта чтения/роли, открытого родительского требования и отзыва владельца.
Сценарии shared_alternative (OR и общий материал, группы, внешний NOT),
dispatch_contracts, partial_readings и nested_partial проходят. Partial
сохраняет альтернативы и блокирует каноническую запись; SPEECH_ACT_UNRESOLVED
остаётся ожидаемой диагностикой этих двух сценариев. Живой модели нет.

Это исправление существующего сужения и проверки частичности, не реализация
полного выбора между ещё не раскрытыми деревьями. Открытый лес, выбор
обязательства для следующего окна и безрекурсивное продолжение остаются
в остатке F05.

## 2026-10-30 — исполнимые продолжения и ограниченный стек композиции

Прежние окна лишь разрешали более глубокую ветвь и повторяли исполнение от
корня. Логическая глубина всё ещё накапливала стек. Теперь ChildTasks хранит
точный вызов до входа в окно и ведёт итеративный стек заданий: исполняет
запрошенного ребёнка в свежем окне, затем повторяет только приостановленный
корень окна. Завершённый ребёнок проходит через обычный кэш и подписки
диспетчера, не расходуя новый уровень раскрытия. Полный логический путь
сохраняется отдельно; циклы через приостановленных предков обнаруживаются.

Сохранённые входы: callable, inputs, area, эффективная обратная связь и
area_inputs/morphology_scope/domain_feedback. Последние восстанавливаются
контекстным менеджером. Стек диспетчера, active и коллекторы чтений никогда
не подменяются старым исполнением. Унаследованные morphology_scope и
domain_feedback включены в сигнатуру ChildTasks: прежний кэш не различал их.

Исправлен resume: при приостановке незавершённая попытка удаляется из attempted.
Раньше повтор родителя мог принять незавершённую попытку за уже выполненную
и отказаться от продолжения. Существующий диагностический/receipt-контракт
сохраняется: завершение исполнения не удостоверяет интерпретацию.

Для сессионного планировщика снят абсолютный depth cap композиции; остаются
окно 3 и общий dispatcher fuel. Внесессионный прежний путь сохраняет защитный
предел. Это не означает устранения всех рекурсивных обходов во всём формализаторе:
ограничен стек именно композиционных задач.

Проверки: 10 целевых тестов, включая 1101 задачу (не более 3 активных),
цикл к приостановленному предку, перенос контекста и pending-проб, повтор
с feedback после приостановки, изменение inherited-контекста и бюджет.
Native: 4 и 18 вложенных NOT до записи, зависимые группы в обоих порядках,
два ссылочных участника и неизвестный участник. check_f05_child_readiness
сохраняет частичность/диагностику. Один Astra medium сделал read-only аудит
контрактов и реализации; прогоны сценарные, без живого модельного ответа.

Остаток: этот планировщик исполняет востребованные продолжения. Он пока
не выбирает между произвольными ещё не раскрытыми структурными деревьями.
Для этого нужны адресованные частичные домены производителей и их общий
протокол сужения. F05 остаётся открытой.

## 30 октября 2026 — F05-OF1, первый шлюз открытого структурного домена

Режим работы: основной исполнитель → независимый readonly reviewer
(group_contract_audit, Astra medium) → координатор F05 (f05_coordinator,
Astra medium). Координатор выдал OF1 для блоков 2/3/6: домен альтернатив,
оболочки/слоты, начальное breadth-first окно 3, сужение, продолжения и gate записи.
В этой поставке выполнен только первый шлюз и актуализация реестра, не весь OF1.

Раньше relation_composition использовал choose и терял доступ к множественному
поддержанному домену после ответа пробы. Теперь choose_open сохраняет прежний
scalar proof для единственного выбора и возвращает SupportedDomain для
альтернатив. Реальный производитель удерживает все поддержанные пункты меню
в STRUCTURAL_OPEN_DOMAIN с адресами, исходным участком, родительским контрактом,
feedback и основаниями принадлежности. Каждая альтернатива имеет незакрытое
обязательство STRUCTURAL_SHELL_UNEXPANDED. Отдельно указано: меню перечислено,
но producer/frontier/propagation/structure/write не завершены.

Расположение: именно после завершённого выбора relation menu имеются основания
membership, а разбиения и дочерние слоты ещё не установлены. Поэтому здесь можно
сохранить кандидатов, но нельзя исполнять их как выбранные отношения, заявлять
завершённое дерево или публиковать OR. Потребитель пока возвращает [] с явной
STRUCTURAL_FOREST_OPEN; native-путь не записывает утверждений этих альтернатив.

Readonly review обнаружил два пробела: неучтённый parent feedback в адресе и
недостаточную связь membership с участком/типом задачи. Исправлены: адрес содержит
parent feedback; retain/live проверяют structural_relation slot, range/token refs,
source/region/input_scope кандидатов и точную проекцию hypotheses. Повторный
review не нашёл блокеров в диагностическом scope. live проверяет исторические
основания; это НЕ разрешение исполнения и НЕ проверка текущего runtime context.

Проверки (PYTHONPATH=.:src:tests:/workspace/scratch/cbcb79b8cb00/ag_memory_deps):
- python -m pytest -q tests/test_structural_open_forest.py
  tests/test_composition_expansion.py tests/test_f05_open_domains.py
- python tools/recovery/check_f05_expansion_native.py — 4 и 18 NOT → ARRIVE,
  native write; ограничение стека сохранено.
- python tools/recovery/check_f05_dependent_group.py — 4 сценария, в том числе
  неизвестный участник и runtime/durable отзыв; все прошли.
- python tools/recovery/check_f05_shared_alternative.py — 4 проверки общего
  материала/альтернатив/внешнего NOT; все прошли.

Новые проверки идут через execute_native/build_plan: AND/OR, LEXICAL/FORALL,
всё меню RELATIONS сохраняются полностью, отсутствуют scalar licensing и AH
assertions; проверены отзыв страницы, версия, подмена участка/slot/проекции,
parent feedback и независимость адресов от порядка меню. Ответы сценарные;
качество реальной модели не оценивалось. Отдельные отрицательные проверки
контракта не являются доказательством полноты всех естественноязыковых разборов.

F05_STATUS.md переписан как единый актуальный реестр: удалены противоречащие
друг другу исторические остатки про стек и NOMINAL_REFERENCE-участников групп.
Открытые задачи: оболочки всех ветвей, child slots, их изоляция, breadth-first 3,
обоснованное сужение, применимость контекста, continuation и общий publication gate.
Все шесть блоков F05 остаются открытыми.

Итог объединённого targeted-прогона: **27 passed in 5.33s**. Координатор
принял OF1-G1 с учётом отчёта исполнителя и readonly review. Следующий шлюз
OF1-G2: применимость membership к исходному runtime, отдельные условные
основания ветвей, изолированные оболочки AND/OR с обоими child slots, без
исполнения детей и без записи. G3 затем займётся раскрытием в ширину.

## 30 октября 2026 — F05-OF1-G2: условные оболочки AND/OR

Следующая задача координатора выполнена в границах производства оболочек,
без исполнения дочерних разборов. Структурный маршрут при нескольких внешних
связях исследует AND/OR через существующие binary/PartitionDomain.resolve.
Оба child slots создаются вместе; ни child composition, ни select_child для
них пока не запускаются. Остальные отношения явно отмечены неподключёнными,
а не исключены. Подтверждение одного разбиения оставляет обязательство
PARTITION_DOMAIN_UNENUMERATED; producer/structure/write остаются False.

Общие изменения контрактов:
- structural_tasks фиксирует execution_basis при производстве домена.
  structural_conditions различает исходное основание, его историческую живость
  и применимость в текущем runtime. Старое membership нельзя превратить в
  исполняемое основание, просто обернув его новым feedback/parent context.
- ConditionalHypothesis вводит адресованную область условного исследования.
  Все STRUCTURAL_TASK/TASK_DOMAIN в ней получают condition, отдельные ключи
  и честную формулировку «исследуем условно». Изменение входа во время пробы
  запрещает потребление результата; потеря условия не включает безусловный режим.
- Публичный licensed не принимает conditional proofs. Отдельный
  licensed_in_scope используется потребителями границ/коллекций/общего материала
  и accepted prerequisites. CONDITIONAL_PROOF в dispatcher проверяет захваченные
  основания независимо от случайной активной ветви при проверке кэша.
- Каждая оболочка производится на отдельном state/session. Решения, диагностики,
  ревизии и прочие последствия не сливаются с глобальным состоянием. Бюджет
  общий; затраты dispatcher суммируются. Nested evidence хранит решения, страницы,
  context reads, диагностики и живые receipts всех шагов производства.
- AttentionContextReader.fork создаёт отдельный overlay внимания над той же
  замороженной AH, с отдельным replay namespace. Он не публикует внимание в
  родительский live engine. Reader без явного fork оставляет ветвь pending;
  скрытой подмены памяти пустым контекстом нет.
- Историческая проверка оболочки проверяет отзыв membership/разбиения/границ,
  точные operands/markers/shared material, выводимость InputSlot, inherited
  context и адреса детей. Это не сертификат полноты и не допуск записи.

Ревьюер обнаружил три конкретных пропуска при реализации: незарегистрированный
CONDITIONAL_PROOF, безусловный consumer source collection и общий мутирующий
attention reader. Все исправлены. Координатор указал, что перестановка меню
не проверяет реальный порядок исполнения: добавлен отдельный прогон AND→OR и
OR→AND, сравнивающий содержимое оболочек. Дополнительно проверено происхождение
дочерних контрактов, а не только checksum receipt.

Проверки с PYTHONPATH=.:src:tests:/workspace/scratch/cbcb79b8cb00/ag_memory_deps:

```
python -m pytest -q tests/test_structural_conditional_shells.py \
  tests/test_attention_branch_fork.py tests/test_structural_open_forest.py \
  tests/test_composition_expansion.py tests/test_f05_open_domains.py
```

**44 passed in 26.60s.** В том числе real execute_native: два условных разбора,
четыре адресованных ребёнка, отсутствие AH assertions; отзыв membership,
partition и boundary page; несовместимые родитель/морфология/domain/source/version;
0, ?, ресурсный stop и изменение контекста во время вызова; настоящий обратный
порядок ветвей. Fork проверен на непустой AH с записанной книгой Ивана: сущность
доступна в контексте, parent/sibling/live attention не изменяются, одинаковый
fork повторно использует receipt, разные ветви имеют разные namespaces.

Регрессии: check_f05_expansion_native.py (4/18 NOT до ARRIVE),
check_f05_shared_alternative.py (4 сценария), check_f05_dependent_group.py
(4 сценария) — прошли. Исполнители проб сценарные; live LLM не проверялась.
Дополнительные AND/READ-корни прежних dependent-group сценариев остаются ранее
зафиксированным отдельным наблюдением, не выдаются за минимальный результат.

G2 не реализует BFS окна трёх уровней, сужение, раскрытие детей, исчерпание
генераторов разбиений, снятие условности или публикацию леса. Это следующий
связанный этап G3 и последующие шлюзы. Все шесть блоков F05 остаются открытыми.


## 31 октября 2026 — OF1-G3: исполняемое начальное окно в ширину

Место механизма: после подтверждённого меню структурных альтернатив и до
сужения/канонизации. Меню предоставляет membership, оболочка AND/OR — адресованные
дочерние InputSlot и разбиение; frontier исполняет только следующий структурный
уровень. Ни один из этих результатов не доказывает завершённости структуры.

- Условия хранятся в плоском реестре; proofs/оболочки ссылаются на condition_ref.
  Историческая цепочка проверяется итеративно. Применимость дочерней области
  выводится через parent shell → child_ref → InputSlot, а не через равенство
  родительского и дочернего контекста. Условное основание доступно своей ветви
  и потомкам, но не соседу и не безусловному licensed.
- Session владеет заданиями, частными исполнениями оболочек, кешами и checkpoints
  reader. Дочерний runtime наследует morphology/domain context, затем переключает
  область и request. Feedback фильтруется по адресату по контракту ChildTasks.
- Очередь обрабатывает минимальную доступную глубину до 3 включительно. Неизвестный
  или неподключённый sibling сохраняет обязательство, но не блокирует доступную
  работу. Глубина 4 только регистрируется; это не предел языковой вложенности.
- Ресурсный stop сохраняет полученные ответы, остаток и израсходованный бюджет.
  Неизменный повтор не вызывает модель. Изменение доступного ресурса открывает
  только ресурсно остановленные узлы; доказанный префикс воспроизводится из кеша.
- Отзыв membership/page/partition проверяется перед запуском и при resume.
  Недействительные results исключаются из активного snapshot, но сохраняются
  в истории. Локальное разбиение не отзывает независимого sibling.
- Snapshot сохраняется также на раннем выходе; memo проверки оснований ограничен
  одной синхронной проверкой и конкретным evidence state. Вложенный reconstruction
  не может использовать положительный вердикт другого состояния.

Координатор выявил потерю morphology/domain/feedback при создании ребёнка;
исправлен общий переход и добавлены проверки реального runtime и текстов проб.
Ревьюер выявил early-return snapshot, отсутствующий resource stamp и смешение
memo между evidence views; все три исправлены, отрицательный случай вложенного
отзыва включён в проверки. Независимое статическое ревью исправлений — без
оставшихся конкретных блокеров в пределах G3.

Сценарный native trace восьми частей: 1 → четыре задания уровня 2 → восемь
заданий уровня 3; шестнадцать заданий уровня 4 остаются QUEUED. AH assertions
не создаются. Проверены dispatcher/search resource stop/resume, отсутствие
повторных вызовов завершённого префикса, singleton и multiple child, обратный
порядок siblings, локальный и общий отзыв, отзыв после enqueue до старта,
изменение контекста, unknown sibling и reader без fork.

Регрессии check_f05_expansion_native.py (4/18 NOT до ARRIVE),
check_f05_shared_alternative.py и check_f05_dependent_group.py прошли.
Исполнители проб сценарные: это проверка механизма, не качества Luna/локальной LLM.
Прежнее наблюдение дополнительных AND/READ корней dependent-group остаётся открытым.

G3 не сужает домены, не исчерпывает генератор разбиений, не запускает следующее
окно и не публикует открытый лес. OF1 и все шесть блоков F05 остаются открытыми.

Следующий пакет координатора G4 (ещё не реализован): адресовать структурную
комбинацию до CONFIRM, валидировать явное NONE_FIT полного одноэлементного
partition-домена и исключать только эту комбинацию. Отзыв rejection page снимает
исключение; неизвестность и отзыв acceptance не являются опровержением.
После завершённой проверки доступных ограничений разрешать адресованное следующее
окно до трёх уровней; не подменять этот шлюз увеличением общего depth limit.
Это первое конкретное сужение, не доказательство полноты ограничений языка.

Ограничение производительности перед G4: обход condition_ref итеративен, но
составная проверка вызывает shell.live и затем conditional proof checks на
реконструированных evidence views. Весь этот контур пока не доказан bounded-stack
для произвольной глубины; глубокая сценарная проверка текущего окна занимает
минуты. Расширение memo между views без доказанной эквивалентности запрещено:
оно уже скрывало отзыв основания. Требуется отдельная работа перед масштабированием.

Итоговый пакет G3 после исправления наследуемого контекста:

```
PYTHONPATH=.:src:tests:/workspace/scratch/cbcb79b8cb00/ag_memory_deps python -m pytest -q \
  tests/test_structural_frontier.py tests/test_structural_conditional_shells.py \
  tests/test_structural_open_forest.py tests/test_attention_branch_fork.py \
  tests/test_composition_expansion.py tests/test_f05_open_domains.py
```

**56 passed in 305.07s (0:05:05)**. `git diff --check` — без замечаний.


## 31 октября 2026 — OF1-G4-A: отрицательные основания конкретных разбиений

Первопричина: PARTITION_REJECTED использовался как запрет по категории/подписи
диагностики. Живость отказавшей страницы не проверялась. При пересмотре эта
страница могла уже быть отозвана, а запрет продолжал действовать через повторное
подтверждение, подсказки генератору границ и текст истории.

Место механизма: после построения полной комбинации и проверки её адресованных
предпосылок, непосредственно перед CONFIRM. Здесь впервые доступны отношение,
операнды, маркеры, общий материал, владелец, источник, родительский контракт и
условная ветвь. Эти данные задают combination_ref независимо от результата
подтверждения. Дальше его используют оболочки, список исключений и генератор.

- partition_exclusions отделяет адрес комбинации от оснований её принятия/отказа.
  Семантический адрес не включает исход подтверждения и refs его страниц; полный
  предъявленный payload с proof grounds сохраняется отдельно и проверяется.
- Отрицательный receipt требует актуальный singleton CONFIRM-домен, NONE_FIT,
  пустой supported set, полное перечисление, точный page payload hash,
  fingerprints, исходный участок/basis и живую цепочку condition. Не используется
  supported_payloads для привязки отказа: на отрицательном ответе он пуст.
- CONFIRM теперь явно сохраняет использованные основания владельца, функций
  общих вхождений, маркеров, scalar relation и общего материала. Их отзыв
  отзывает зависимый отрицательный receipt. Историческая живость отделена от
  применимости в текущей ветви и области.
- Повтор блокируется только живым отрицательным receipt той же комбинации.
  Другое разбиение того же отношения, в том числе с общей отдельной границей,
  остаётся допустимым. UNKNOWN, бюджет и отсутствие производителя не исключают
  комбинацию. Исчерпание генератора разбиений не выводится из отказа.
- Три прямых потребителя PARTITION_REJECTED используют общий валидатор. Typed
  PARTITION_EXCLUSION read выполняется внутри PARTITION task и span producer:
  отзыв меняет также зависимый кеш, а не только его вызывающего.
- После supersede история revision содержит нейтральное незавершение, без
  отрицательных failures как действующих нарушений. Точные ограничения передаются
  отдельно через проверяемые receipts. Существующий общий механизм supersede не
  отменён: отозванный отказ перестаёт давать запрет.
- Positive shell связывает combination_ref с фактически выбранным payload;
  frontier snapshot содержит отдельные excluded_combination_refs. Родительская
  гипотеза/producer остаются OPEN, открытый лес ничего не записывает.

Независимый reviewer обнаружил недостающий dispatcher whitelist, чтение отказа
вне внутреннего task, несвязанность positive combination_ref, неполные prerequisites
и косвенный перенос отозванного отказа через историю. Все исправлены; финальный
readonly verdict — без конкретных блокеров в пределах G4-A.

Проверки используют реальные native/dispatcher пути со сценарными ответами.
Они не оценивают Luna или локальную модель. G4-B (проверка ограничений и выдача
следующего окна) не реализован. Стоимость/стек всей составной валидации остаются
отдельной обязательной работой перед G4-B. Все шесть блоков F05 открыты.

Итог проверки G4-A (PYTHONPATH как в G3):
- `tests/test_partition_exclusions.py`: 19 passed in 41.11s; после добавления
  обратного порядка и замены ресурсного сценария на реальное исчерпание LLM-бюджета
  выборка `-k 'resource_stop or reversed_execution'`: 3 passed in 8.47s.
  Всего покрыты 20 различных проверок нового модуля; это не два независимых корпуса.
- G2/condition/openforest/attention/expansion/open-domain пакет: 45 passed in 35.16s.
- `tests/test_structural_frontier.py -k native_breadth_three`: 1 passed in 114.34s.
- `check_f05_expansion_native.py`: 4 и 18 NOT до ARRIVE; `check_f05_shared_alternative.py`:
  четыре сценария — прошли после окончательной правки истории пересмотра.
- `git diff --check`: чисто. Сквозные пробы во всех этих сценариях — scripted.

Координатор принял G4-A. Следующий пакет G4-P: измерить взаимный обход
historical → shell.live → evidence_state → conditional proof → historical
(глубина стека, повторные проверки, views/signatures, время и объём evidence),
начиная с доступных глубин без заведомо экспоненциального прогона. При подтверждении
роста стека заменить взаимную рекурсию итеративными проверочными обязательствами,
сохранив разные evidence views, циклы, fingerprints и отзыв ancestor/sibling.
До этого frontier остаётся в окне 1–3; G4-B не подключается.


## 31 октября 2026 — OF1-G4-P: общий итеративный обход оснований

Измерение от 8beabfa разделило производство и проверку готового результата.
Baseline BFS3: 162,8754 с, 68133 вызова historical, 16787 evidence_state,
14149 source signatures. Одна готовая оболочка третьего уровня: 91 historical,
21 evidence view, 14 source signatures, вложенность наблюдаемых вызовов 10;
0,1118 с, повтор 0,1159 с. Повтор полностью повторял обход.

Причина: локальный while в historical не устранял взаимные вызовы shell.live,
conditional proof, forest/domain и prerequisites. Кеш на одном condition_ref
небезопасен: разные evidence views могут содержать разные отказы/fingerprints.

Новый validation_graph исполняет явные обязательства CONDITION/FOREST/DOMAIN/
SHELL/PROOF/EXCLUSION через генераторы и итеративную очередь DFS. Завершённый
результат кешируется только после зависимостей; общий DAG допустим, цикл — нет.
Ожидаемый payload, разрешение условной ветви и visiting-set входят в transient
identity. Сериализация для этого ключа сохраняет типы Python контейнеров и не
затрагивает persistent proof digests; десериализации внешних данных нет.

Private views объединяются лишь по данным, которые читают валидаторы: тот же
неизменный base state, decisions/probes, последние domain/task rows (включая
оба вида адреса task), все retirement events. Текущие записи имеют приоритет
над вложенным packet. Исполняемые states/trace не нормализуются и не переписываются.
Кеш и source signature живут только в одной синхронной read-only проверке.
Повреждённое evidence возвращает False, reentrant entry остаётся ошибкой контура.

Публичные valid_domain/forest.live сохраняют True/False subscriptions через
READING_DOMAIN/STRUCTURAL_FOREST. Внутренние validators не создают observations.
Discard читает точные domain/page/prerequisite/condition/shell dependency refs,
включая registry-only evidence и последние packet revisions; unrelated reads
не удаляются. CONDITIONAL_PROOF и PARTITION_EXCLUSION также участвуют в этом
адресном снятии заменённых предпосылок.

Независимый reviewer выявил недостающий latest-task lookup в view key, различия
list/tuple в expected payload, set canonicalization, обработку ошибок дочерних
generators и неполный сбор вложенных refs для discard. Исправления проверены.
Дополнительно восстановлены публичные subscriptions, которые раньше возникали
неявно через вызов prerequisite.errors. Финальный readonly review — без найденных
конкретных блокеров в проверенном контуре.

После: тот же BFS3 78,614 с; source signatures 4601, вложенность наблюдаемых
validation calls 2. Размер shell 310173 bytes и registry 85681 bytes не изменился.
Pure shell: 0,095 с, повтор 0,0631 с; 56 явных obligations. Это один сценарий,
не универсальная оценка скорости. Измерение сделано до добавления aggregate
public subscriptions; последующие проверки покрывают их корректность.

Test-only harness строит длинную цепочку настоящими producers вне production
планировщика. Окно runtime остаётся 1–3. На глубинах 3/8/16 получены соответственно
31/91/187 obligations и 7/12/20 pending work items. Для глубины 16 Python frames
на входе в каждый obligation постоянны: 7..7; два private views, 90 reuse.
Проверка готовой глубины 16: 0,3933 с, повтор 0,4034 с; отзыв основания в середине
цепочки отвергает результат за 0,0427 с. Производство: 579,8837 с, shell 352523 bytes.
Глубины 3/8 измерялись на промежуточном варианте memo: нельзя выдавать их production
время за чистое асимптотическое сравнение. Глубина 32 не запускалась из-за стоимости.
Подробные цифры сохранены в F05_VALIDATION_PROFILE.json.

На отдельном синтетическом графе планировщика 2000 зависимостей не увеличивают
Python stack; общий DAG и цикл различаются. Это проверка scheduler, не 2000
уровней естественного языка. Реальные контрасты: nested-evidence retirement,
changed fingerprint без retirement event, permission/expected payload mismatch,
малформированный shell, membership→partition→condition cycle, независимость sibling,
negative evidence, resource resume, public cache True→False→True и exact discard.

Проверки: исходный пакет 70 — 63 passed и 7 ошибок fixture без dispatcher после
введения публичных observations. Fixtures подключены к настоящему Dispatcher;
пакет graph/G2/openforest — 30 passed in 38.21s (включая все семь исправленных).
Новый native-cycle — 1 passed in 2.31s. Три resource/context frontier сценария
прошли; local-then-root injection повторно выполнялся на уже STALE очереди из-за
закономерного replay по новой negative observation. Трасса показала успешные
первые assertions и второй вызов hook; инъекция сделана одноразовой, исходные
проверки сохранены. Повтор — 1 passed in 19.18s. Всего 76 различных целевых тестов
проверены группами, это не единый 76-test run. Native NOT4/18 и shared-alternative
четыре сценария также прошли. Все ответы исполнителя scripted, не live LLM.

Устранена взаимная рекурсия проверки; дороговизна производства длинной цепочки
остаётся отдельной установленной границей. G4-B не подключён. Все шесть блоков
F05 открыты; ни разрешения следующего окна, ни publication gate здесь нет.

Координатор принял ограниченный G4-P после измерений и ревью; сводные проверки
завершены. Следующий пакет G4-B: snapshot проверки актуальных exclusions/оснований,
адресное разрешение одного справедливо выбранного продолжения (до трёх уровней),
общий бюджет и точный остаток, проверка разрешения перед каждым запуском.
В диагностику добавить отдельную стоимость проверки и производства. Первый native
сценарий — небольшой выход на уровень 4; полный размер окна проверять дешёвым
fixture. Не подключать публикацию и не объявлять полноту генераторов.

### 2026-10-31 — последовательность операндов и повторное использование схем

Архитектурное направление повторного использования параметризованных схем
повторяющихся конструкций отложено: **DEFER**. Это не реализованный механизм
и не условие закрытия текущего этапа. Действующий кеш доказательств этим решением
не отключается.

Приоритет пересмотра: последовательность операндов сама по себе не является
основанием семантической вложенности. Следует различать положение в тексте,
принадлежность группе, области действия и техническую глубину бинарного
представления. Рекурсивное выделение «первый элемент + остаток» может создавать
глубину способа перечисления, а не глубину смысла. Начальное окно трёх уровней
нельзя без проверки трактовать как три последовательных операнда.

Нельзя и автоматически сплющивать цепочку по повторению союза, предиката или
сходству текста: общий оператор, совместимость областей действия и сохранение
ролей/владельцев требуют основания. Если группировка не установлена, сохраняются
альтернативы; адресованная проба разрешает именно различие группировок.
Выбор конкретного n-арного внутреннего представления пока не принят.

Замер 579,8837 с относится к scripted-выбору бинарных разбиений 17 повторений
«Иван читает», соединённых «и», с принудительным продолжением выбранной ветви.
Он показывает стоимость данного маршрута производителя, но не доказывает,
что исходный текст требует 16 уровней семантической вложенности.
Следующая проверка кода должна установить, где смешиваются эти виды глубины,
и проследить последствия для производителей, окна, проб и потребителей.
Настоящая запись меняет план; исправления runtime и доказательства полноты
этим не заявляются. Все шесть направлений F05 остаются открытыми.

### 2026-10-31 — непосредственные части группы без обязательной бинаризации

Исторический промежуточный этап: предварительный выбор count заменён сбором
конкретных частей в следующей записи. Приведённые ниже замеры относятся к нему.

Причина найдена в relation_partitions.binary: для AND/OR/XOR задавались ровно
две роли; structural_shells._live дополнительно требовал двух детей. Сам frontier
обходит произвольный список children, а native_plan и FunctionRegistry уже
поддерживают n-арные AND/OR/XOR (XOR — ровно одна альтернатива, не parity).

На уровне выбранной внешней связи, перед границами частей, добавлена адресованная
structural_operand_count. Требуются исходный target, текущая область и выбранная
связь; результат устанавливает только число непосредственных частей. Границы
по-прежнему выбираются из вхождений источника, с сохранением вложенных отношений.
Count proof передаётся prerequisite во все boundary collectors и CONFIRM;
подтверждение проверяет точное число, relation, slot и условную область доказательства.
Оболочка допускает >=2 детей, сохраняя проверку полного списка operands.
Изменение относится и к обычному пути до native-записи, и к условным AND/OR.
Окно не увеличено: три соседа теперь имеют одинаковую глубину, вложенная
конструкция внутри одного из них по-прежнему получает следующий уровень.
Автоматического сплющивания по союзам/предикатам или повторениям текста нет.

Неоднозначное число, unknown и NONE_FIT не превращаются в бинарный default.
Верхняя граница len(tokens) консервативна для текущего генератора непустых частей
с отдельным вкладом источника; это не доказательство полноты невыраженных частей.
Несколько допустимых counts сохраняются в диагностике как альтернативы, но
пока не исполняются отдельными ветвями. Отдельный пересмотр count после неудачи
границ ещё открыт. Общий материал поддерживается во всех частях одновременно;
материал только для подмножества частей этим изменением не реализован.
XOR подключён в singleton-маршруте; открытые условные оболочки остаются AND/OR.

Проверки (scripted, не live LLM): 7 прежних binary/conditional сценариев;
52 проверки direct parts, exclusions, conditional shells, open forest;
4 frontier resource/context/retirement; дополнительный native OR с общим
предикатом для трёх альтернатив — 1 passed. Итого 63 разных pytest-проверки
(одна conditional проверка повторяется в двух пакетах), плюс четыре сценария
check_f05_shared_alternative.py. В новых проверках подтверждены native-запись
AND/OR/XOR с тремя частями, сохранение AND(A, OR(B,C)), отсутствие утверждения
внутренних альтернатив, одинаковая глубина sibling и отзыв count.
Изначальные четыре ошибки нового oracle были порядком коммутативных operands
и assertion order; native_plan сортирует их. Сверка теперь сортирует эти
тестовые структуры, сохраняя иерархию и кратность; ожидаемый смысл не изменён.
diff --check и compileall прошли. Независимый reviewer и координатор не нашли
блокеров в ограниченном production diff. G4-B и все шесть блоков F05 открыты.

Профиль того же текста из 17 повторений «Иван читает» с выбором одной группы:
179,6222 с, 218 scripted prompt calls, две условные оболочки AND/OR по 17 детей,
35 задач (корень + 34 ребёнка), максимальная глубина 2. Листья LEXICAL остаются
pending capability; публикации нет. Скрипт profile_f05_direct_parts.py и числа
F05_DIRECT_PARTS_PROFILE.json сохранены. Это демонстрация иного структурного
маршрута, не чистый benchmark ускорения относительно 579,8837 с: состав работы
различается, новый прогон выполнялся параллельно с pytest. Стоимость широкого
узла и 218 проб остаётся отдельной проблемой; качества реальной модели не измеряли.

### 2026-10-31 — группировка по вхождениям; количество как результат

Проба structural_operand_count удалена: она требовала числа до установления
того, какие части относятся к общей связи. direct_partitions.collect работает
после выбора внешней связи, когда известны target, scope и branch-local ownership.
Сначала выбираются два непосредственных операнда (минимальная арность этих
операторов), затем structural_group_next предлагает все ещё доступные начала
ещё одной непосредственной части этой же связи. Начало может находиться и раньше
предыдущей части: порядок текста не отсекает гипотезы. Вопрос предъявляет принятые
части и требует сохранять вложенные отношения внутри владельца.

Выбранное начало передаётся source_set как initial, поэтому повторной start-пробы
нет. Новый fixed_initial запрещает прежний скрытый переход к другому началу,
если все концы выбранного начала отвергнуты. Такой случай остаётся pending и не
считается исчерпанием всех начал. Остальные пользователи span сохраняют прежний
режим. У продолжения тип NEXT; 0 отвергает страницу, ? и несколько альтернативных
начал не превращаются в завершение группы. DONE доступен только при покрытии
known required content и получается после исчерпания всех страниц оставшихся
начал. open_parts позволяет промежуточной части не поглощать весь оставшийся
обязательный материал; итоговое покрытие проверяется при закрытии/подтверждении.

Каждый новый сбор получает prerequisites предыдущих SOURCE_SET, включая их
completion proofs. DONE хранит exact raw_groups и всю цепочку оснований.
Grouping witness обязателен для AND/OR/XOR в confirm_partition. Перед итоговым
CONFIRM для каждого индекса проверяется final_i = (raw_i − markers) ∪ shared_all,
а функции markers и shared material отдельно имеют действующие доказательства.
Совпадения объединений недостаточно: перестановка/перенос слов между детьми
отвергается. Completion proof становится prerequisite итогового подтверждения,
включая отрицательный receipt. Отзыв boundary completion отзывает shell.

select_parts сохраняет механизм доказанного ownership repair. У пересмотренной
части отзывается suffix (включая её ведущий NEXT), части/завершение собираются
снова. Feedback устанавливается до NEXT; исходное _ownership_feedback теперь
не стирается до появления собственного repair. Источник числа — длина собранного
списка; числовых гипотез больше нет. Поддержка n-ary native IR и окна сохранена.

Проверки scripted: первоначально 15 passed (9 direct-parts + 6 binary), затем
расширенные direct-parts 13 passed. Регрессионный пакет exclusions/conditional/
open-forest/resource/context: 46 passed, один устаревший fixture отвергнут, поскольку
он переносил слова между детьми со старым grouping witness. Fixture теперь
заново получает границы и completion через реальный producer; ожидание другого
допустимого разбиения и действующего старого отрицательного receipt сохранено.
Повтор этого сценария вместе с ownership repair и projection — 3 passed.
Всего 66 разных pytest-проверок, включая UNKNOWN/MULTIPLE NEXT, fixed-initial
endpoint rejection, отзыв group DONE и operand SOURCE_SET DONE, exact projection,
native AND/OR/XOR, nested OR и общий материал трёх альтернатив.
Четыре сценария check_f05_shared_alternative.py также прошли; compileall и
diff --check чистые. Финальное независимое ревью не нашло новых блокеров;
проверены mandatory grouping gate, feedback перед NEXT и отзыв suffix.

Профиль четырёх повторений: 14,2038 с, 46 scripted calls, две оболочки по четыре
ребёнка, 9 задач, глубина 2; листья LEXICAL pending capability, без публикации.
Это не сопоставимый замер ускорения относительно прежних 17 частей. Исторический
F05_DIRECT_PARTS_PROFILE.json оставлен без переписывания; новый результат в
F05_COLLECTED_PARTS_PROFILE.json. Live модель в этом этапе не проверялась.
Открыты исполнение альтернативных NEXT/границ, адресный пересмотр неудачного
NEXT, subset sharing, полнота генераторов и G4-B. Схемы повторения остаются DEFER;
все шесть блоков F05 открыты. Сценарные ответы не доказывают надёжность языкового
различения плоской группы и вложенности у целевой модели.

### 2026-10-31 — OF2: общие простые оболочки и адресованные окна G4-B

structural_relations содержит единый контракт 12 простых отношений:
AND/OR/XOR (>=2 части), IMPLIES/COUNTERFACTUAL/BEFORE/AFTER/DURING (2),
IF_ELSE (3), NOT/QUERY/GROUP (1). Producer использует существующие разбиения;
scalar compose, shell producer/live и frontier используют один вывод child_request.
Для GROUP сохраняется inside_attitude без generic surrounding append. Проверяются
точная арность, child refs, slots и exact partition payload; при отзыве partition
оболочка теряет основание. owner/shared-function проверки confirm_partition
переведены на scoped license для будущих специальных производителей; это само
по себе не подключает CONTENT или кванторы.

Нельзя просто распространить тот же контракт на остальные 8 отношений:
POSSIBLE/NECESSARY требуют governor и правил agreement inheritance;
CONTENT — owner/role и зависимого от результата родителя controller;
FORALL/EXISTS — quantifier kind, binder head, shared functions и целый body;
LEXICAL/NOMINAL_DESCRIPTION/CONTENT_REFERENCE — отдельные результаты и obligations.
Эти производители остаются pending capability, не объявляются невозможными.

G4-B: после начального окна 1–3 structural_windows.inspect проверяет всю
доступную цепочку предков, current forest/shell evidence и действующие exact
partition exclusions. Пробел parent chain запрещает продолжение. Разрешение
связано с generation, job, immutable ancestor check и локальными уровнями
root..root+2; наличие собственного нового forest не меняет input basis разрешения,
но его живость проверяется. Перед стартом повторяются permit identity, root check,
job check и текущие source/context/feedback/memory context. Изменение generation
останавливает последующие старты и очищает permits. Retired exclusion не блокирует
ветвь, но непроверенное/противоречивое основание не считается допуском.

Готовая очередь выбирается по (depth, job_ref) ДО admission: более глубокий
разрешённый job не обходит более близкого соседа без permit. Локальный неизменившийся
resource stop исключает только соответствующий job из ready; доступные siblings
продолжаются. Общий исчерпанный бюджет останавливает весь проход. Кеш, dispatcher
spent, reader checkpoints и остаток сохраняются. Snapshot содержит permits,
parent job refs и blocked checks. cost.validation_seconds измеряет именно вызовы
constraint inspection, production_seconds — блок исполнения producer; это не
полная разбивка всех liveness/snapshot расходов.

Проверки: 30 passed in 68.28s на адаптерах, direct parts и open forest до завершения
G4-B; native frontier suite 11 passed in 444.60s (на промежуточном scheduler до
последнего исправления fairness/local-resource). На конечном scheduler 7 новых
window tests passed in 16.49s, 3 resource/context regression passed in 62.34s.
Итого 48 различных pytest-проверок; три последних повторяют часть frontier suite.
Новые native tests: NOT до глубины 5, unknown/capability sibling сохранён,
retirement между grant и start, смена feedback во время production, независимый
прогресс siblings при локальном resource stop. Отдельно scheduler fixtures
проверяют окно 4–6 без уровня 7, permit/ancestry corruption, exact exclusion
vs unrelated/retired и действительный run с обратным порядком вставки jobs.
Корректность negative receipt не подменяется verifier stub: это отдельный
проверяемый контракт G4-A. Ни один открытый лес не публикует AH assertions.

Во время работы среда временно отключалась. Первый незавершённый frontier прогон
не засчитан; после восстановления файлы проверены и suite запущена заново.
Независимый reviewer последовательно выявил и проверил исправления permit,
missing-parent, current-generation, BFS и local-resource guards; финальных
блокеров scheduling не нашёл. Все ответы сценарные, не live LLM.

Все шесть F05 остаются открытыми. Следующий шлюз — условный lexical producer
без скрытого рекурсивного обхода и с зависимыми дочерними задачами; затем специальные
отношения, альтернативные boundaries/NEXT, владельцы, binder/reference domains,
источники и publication gate. Схемы повторения и арифметические кванторы — DEFER.
