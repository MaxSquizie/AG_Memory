# Инвентаризация проб: 16 октября 2026

Получено из всех доступных записей выгрузки. «Первый ?» — наблюдаемая остановка, **не доказанная первопричина**. Этот документ не восстанавливает обрезанные части и не оценивает качество новых промптов.

Источник: `progress(20261015-210229).jsonl`. SHA-256: `f3284e338a285328b23915d77e29ff48916af5263282d802d6db77209dfaf044`.

Завершённых случаев: 640; FAIL: 215, PASS: 425.
Полученных ответов: 3708. Обрезанных промптов: 0. Обрезанных результатов шагов: 640.
PASS при наличии ответа ?: 0. Непустая формула, не совпавшая с эталоном: 52. Несовпадение только генерации: 11.

Из непустых несовпадений в 45 различаются только текстовые метки OPEN-предикатов: структура, роли, участники и операторы совпадают. Это отдельная категория аудита, не исправление эталона и не доказательство тождества неизвестных слов.

## Все типы вызванных проб

| Вопрос | Вызовов | ? | 0 | Средняя длина промпта, символов | Обрезано |
|---|---:|---:|---:|---:|---:|
| Внешняя связь (`structural_relation`) | 1055 | 0 | 0 | 2403 | 0 |
| Вложенное содержание: начало (`structural_content_start`) | 113 | 0 | 0 | 1121 | 0 |
| Вложенное содержание: конец (`structural_content_end`) | 113 | 0 | 0 | 1235 | 0 |
| Родительская часть: начало (`structural_parent_start`) | 113 | 0 | 0 | 997 | 0 |
| Родительская часть: конец (`structural_parent_end`) | 113 | 0 | 0 | 1242 | 0 |
| Проверка разбиения (`structural_partition`) | 386 | 0 | 37 | 1592 | 0 |
| Предикат — владелец содержания (`structural_owner`) | 113 | 0 | 0 | 752 | 0 |
| Роль и статус вложенного содержания (`structural_content_role`) | 113 | 0 | 0 | 942 | 0 |
| Именная зависимость (`nominal_dependency`) | 310 | 2 | 2 | 1588 | 0 |
| Пересмотр разбора (`structural_revision`) | 266 | 0 | 0 | 1703 | 0 |
| Однородные участники (`nominal_coordination`) | 1 | 0 | 0 | 850 | 0 |
| Первая часть: начало (`structural_operand_1_start`) | 36 | 0 | 0 | 940 | 0 |
| Первая часть: конец (`structural_operand_1_end`) | 36 | 0 | 0 | 1283 | 0 |
| Вторая часть: начало (`structural_operand_2_start`) | 36 | 0 | 0 | 916 | 0 |
| Вторая часть: конец (`structural_operand_2_end`) | 36 | 0 | 0 | 1011 | 0 |
| Вводящее выражение: начало (`structural_introducer_start`) | 239 | 0 | 0 | 1210 | 0 |
| Вводящее выражение: конец (`structural_introducer_end`) | 239 | 0 | 0 | 1487 | 0 |
| Принадлежность служебного слова (`structural_function_owner`) | 6 | 0 | 0 | 1292 | 0 |
| Область модификатора (`modifier_scope`) | 1 | 0 | 0 | 1050 | 0 |
| Состав и чтение конструкции (`component_attachment`) | 176 | 0 | 1 | 1556 | 0 |
| Управление модальным содержанием (`structural_governor`) | 66 | 0 | 0 | 944 | 0 |
| lexical_recovery (`lexical_recovery`) | 1 | 0 | 0 | 1048 | 0 |
| Присоединение именной группы (`nominal_attachment`) | 4 | 0 | 0 | 959 | 0 |
| Высказывание или название события (`structural_event_head`) | 13 | 0 | 0 | 1025 | 0 |
| implicit_argument (`implicit_argument`) | 1 | 0 | 0 | 2243 | 0 |
| Грамматическое чтение неизвестного слова (`structural_oov_reading`) | 122 | 0 | 0 | 1911 | 0 |

## Первый ответ ? в неуспешных случаях

| Вопрос | Случаев |
|---|---:|
| Без ответа ? | 214 |
| Именная зависимость | 1 |

## Отдельно проверяемые результаты

PASS с неотвеченными вопросами: .

Непустое несовпадение формулы: A35, NONFINITE-00-base, NONFINITE-01-base, NONFINITE-02-base, NONFINITE-04-base, NONFINITE-05-base, NONFINITE-06-base, OPEN-00-0-or, OPEN-00-1-asserted, OPEN-00-1-or, OPEN-00-2-asserted, OPEN-00-2-or, OPEN-00-3-asserted, OPEN-00-3-or, OPEN-01-0-asserted, OPEN-01-0-not, OPEN-01-0-or, OPEN-01-1-asserted, OPEN-01-1-or, OPEN-01-2-or, OPEN-01-3-asserted, OPEN-01-3-or, OPEN-02-0-asserted, OPEN-02-0-or, OPEN-02-1-asserted, OPEN-02-1-or, OPEN-02-2-asserted, OPEN-02-2-or, OPEN-02-3-asserted, OPEN-02-3-or, OPEN-03-0-asserted, OPEN-03-0-or, OPEN-03-1-asserted, OPEN-03-1-not, OPEN-03-1-or, OPEN-03-2-asserted, OPEN-03-2-or, OPEN-03-3-asserted, OPEN-03-3-or, OPEN-04-0-asserted, OPEN-04-0-or, OPEN-04-1-asserted, OPEN-04-1-or, OPEN-04-2-asserted, OPEN-04-2-or, OPEN-04-3-asserted, OPEN-04-3-or, OPEN-05-0-asserted, OPEN-05-1-asserted, OPEN-05-2-asserted, OPEN-05-3-asserted, OPEN-05-3-or.

## Каждый завершённый случай

Номера строк относятся к исходному JSONL. Последовательность содержит **все** записанные ответы случая. Подробные поля морфологии здесь сокращены для чтения; исходные варианты находятся в промпте указанной строки.

### A01 — FAIL

Иван сказал, что Пётр пришёл.

Результат шага обрезан в выгрузке.

- Строки 4 → 5. Внешняя связь: Пропозициональное содержание
- Строки 6 → 7. Вложенное содержание: начало: Начать с «Пётр» @17
- Строки 8 → 9. Вложенное содержание: конец: Закончить после «пришёл» @28; выбранные слова «Пётр пришёл»
- Строки 10 → 11. Родительская часть: начало: Начать с «Иван» @0
- Строки 12 → 13. Родительская часть: конец: Закончить после «.» @29; выбранные слова «Иван сказал , что .»
- Строки 14 → 15. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что .»; content filling that slot: «Пётр пришёл»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 16 → 17. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 18 → 19. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 20 → 21. Внешняя связь: Одна предикация / именное описание
- Строки 22 → 23. Именная зависимость: Ни один показанный вариант не подошёл (0)
- Строки 24 → 25. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 26 → 27. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/supports/root_targets`, `/structural/formulas`.

### A02 — PASS

Иван и Пётр пришли.

Результат шага обрезан в выгрузке.

- Строки 32 → 33. Внешняя связь: Одна предикация / именное описание
- Строки 34 → 35. Однородные участники: Conjoined participants in ONE nominal slot: «Иван» + «Пётр»

Первая записанная диагностика: нет.

### A03 — PASS

Иван пришёл и Мария спит.

Результат шага обрезан в выгрузке.

- Строки 40 → 41. Внешняя связь: Совместное выполнение
- Строки 42 → 43. Первая часть: начало: Начать с «Иван» @0
- Строки 44 → 45. Первая часть: конец: Закончить после «пришёл» @11; выбранные слова «Иван пришёл»
- Строки 46 → 47. Вторая часть: начало: Начать с «Мария» @14
- Строки 48 → 49. Вторая часть: конец: Закончить после «спит» @24; выбранные слова «Мария спит»
- Строки 50 → 51. Проверка разбиения: Proposed split — part 1: «Иван пришёл»; part 2: «Мария спит»; outer relation occurrences: «и» @12; punctuation outside parts: «.»
- Строки 52 → 53. Внешняя связь: Одна предикация / именное описание
- Строки 54 → 55. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### A06 — FAIL

Не каждый студент мог не сдать экзамен.

Результат шага обрезан в выгрузке.

- Строки 60 → 61. Внешняя связь: Отрицание
- Строки 62 → 63. Вводящее выражение: начало: Начать с «Не» @0
- Строки 64 → 65. Вводящее выражение: конец: Закончить после «не» @24; выбранные слова «Не каждый студент мог не»
- Строки 66 → 67. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 68 → 69. Пересмотр разбора: The text supports a different relation or different boundaries; reconsider them
- Строки 70 → 71. Внешняя связь: Отрицание
- Строки 72 → 73. Вводящее выражение: начало: Начать с «Не» @0
- Строки 74 → 75. Вводящее выражение: конец: The text is "Не каждый студент мог не сдать экзамен."
The instruction asks to select the words expressing the outer relation of negation of a proposition.
The outer negation is "Не" (Not) at the beginning.
The inner negation is "не" (not) before "сдать".
The structure is: [Not] [every student] [could] [not pass] [the exam].
The outer negation "Не" negates the proposition "каждый студент мог не сдать экзамен" (every student could not pass the exam).
The instruction says: "Exclude words belonging to a different nested relation... Exclude the content proposition, its subject and predicate."
The content proposition is "каждый студент мог не сдать экзамен".
The outer marker is "Не".
The instruction says: "Include the full linking expression and any conjunction introducing its content."
Here, "Не" is the marker. The content is the rest of the sentence.
The previous attempt selected "Не каждый студент мог не" which included the inner negation "не". The instruction says "Exclude words belonging to a different nested relation". The inner "не" belongs to the nested relation (negation of "сдать"). Therefore, the inner "не" should be excluded from the selection of the *outer* relation's expression if we are strictly selecting the words that *express* the outer relation itself, or if the "linking expression" is just the marker.
However, usually in these tasks, "select only the complete words expressing this outer relation" implies selecting the marker and potentially the scope if it's a specific construction, but the instruction explicitly says "Exclude the content proposition".
Let's re-read carefully: "select only the complete words expressing this outer relation... Exclude the content proposition, its subject and predicate."
The outer relation is the negation of the whole clause. The word expressing this is "Не".
Does "Не" link to the content? Yes.
Is "каждый студент мог не сдать экзамен" the content? Yes.
So we should exclude the content.
This leaves only "Не".
Option 1 is "Закончить после «Не» @2; выбранные слова «Не»".

Let's check if there is a "linking expression" that is longer. In Russian, "Не" is the standard negation particle. It doesn't have a multi-word form like "not only... but also". It is a single word.
The instruction "Include the full linking expression" might refer to cases like "It is not the case that...". Here it is just "Не".
The instruction "do not end early just because the first word already signals the relation" is a warning against stopping too soon if the expression is longer. But here the expression is just "Не".
The previous attempt failed because it included the inner negation "не" and parts of the content.
Therefore, the correct selection is just the outer marker "Не".

Option 1 corresponds to this.

1

Первая записанная диагностика: COMPONENT_PROBE_FAILED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/supports/root_count`.

### A11 — FAIL

Кто-то вошёл, а затем он сел.

Результат шага обрезан в выгрузке.

- Строки 80 → 81. Внешняя связь: Раньше
- Строки 82 → 83. Первая часть: начало: Начать с «Кто-то» @0
- Строки 84 → 85. Первая часть: конец: Закончить после «вошёл» @12; выбранные слова «Кто-то вошёл»
- Строки 86 → 87. Вторая часть: начало: Начать с «а» @14
- Строки 88 → 89. Вторая часть: конец: Закончить после «сел» @28; выбранные слова «а затем он сел»
- Строки 90 → 91. Принадлежность служебного слова: Outer relation owns «а» @14; remove this occurrence from its part
- Строки 92 → 93. Проверка разбиения: Proposed split — part 1: «Кто-то вошёл»; part 2: «затем он сел»; outer relation occurrences: «а» @14; punctuation outside parts: «, .»
- Строки 94 → 95. Внешняя связь: Одна предикация / именное описание
- Строки 96 → 97. Внешняя связь: Одна предикация / именное описание
- Строки 98 → 99. Область модификатора: «затем» applies to «сел он»
- Строки 100 → 101. Состав и чтение конструкции: сесть [VERB]; SUBJECT=он

Первая записанная диагностика: REFERENCE_UNKNOWN.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/bindings/discourse_variable`.

### A12 — PASS

Возможно, Иван пришёл.

Результат шага обрезан в выгрузке.

- Строки 106 → 107. Внешняя связь: Возможность
- Строки 108 → 109. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 110 → 111. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 112 → 113. Проверка разбиения: Proposed split — part 1: «Иван пришёл»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 114 → 115. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 116 → 117. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### A13 — PASS

Если Иван пришёл, то Мария спит.

Результат шага обрезан в выгрузке.

- Строки 122 → 123. lexical_recovery: Keep «то» as written; no licensed correction established
- Строки 124 → 125. Внешняя связь: Условие → следствие
- Строки 126 → 127. Первая часть: начало: Начать с «Если» @0
- Строки 128 → 129. Первая часть: конец: Закончить после «пришёл» @16; выбранные слова «Если Иван пришёл»
- Строки 130 → 131. Вторая часть: начало: Начать с «то» @18
- Строки 132 → 133. Вторая часть: конец: Закончить после «спит» @31; выбранные слова «то Мария спит»
- Строки 134 → 135. Принадлежность служебного слова: Outer relation owns «Если» @0; remove this occurrence from its part
- Строки 136 → 137. Принадлежность служебного слова: Outer relation owns «то» @18; remove this occurrence from its part
- Строки 138 → 139. Проверка разбиения: Proposed split — condition: «Иван пришёл»; consequence: «Мария спит»; outer relation occurrences: «Если» @0, «то» @18; punctuation outside parts: «, .»
- Строки 140 → 141. Внешняя связь: Одна предикация / именное описание
- Строки 142 → 143. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### A14 — PASS

Если бы Иван пришёл, Мария бы уснула.

Результат шага обрезан в выгрузке.

- Строки 148 → 149. Внешняя связь: Контрфактическое условие
- Строки 150 → 151. Первая часть: начало: Начать с «Если» @0
- Строки 152 → 153. Первая часть: конец: Закончить после «пришёл» @19; выбранные слова «Если бы Иван пришёл»
- Строки 154 → 155. Вторая часть: начало: Начать с «Мария» @21
- Строки 156 → 157. Вторая часть: конец: Закончить после «уснула» @36; выбранные слова «Мария бы уснула»
- Строки 158 → 159. Принадлежность служебного слова: Outer relation owns «Если» @0; remove this occurrence from its part
- Строки 160 → 161. Принадлежность служебного слова: Outer relation owns «бы» @27; remove this occurrence from its part
- Строки 162 → 163. Принадлежность служебного слова: Outer relation owns «бы» @5; remove this occurrence from its part
- Строки 164 → 165. Проверка разбиения: Proposed split — condition: «Иван пришёл»; consequence: «Мария уснула»; outer relation occurrences: «Если» @0, «бы» @5, «бы» @27; punctuation outside parts: «, .»
- Строки 166 → 167. Внешняя связь: Одна предикация / именное описание
- Строки 168 → 169. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### A31 — PASS

Мне холодно.

Результат шага обрезан в выгрузке.

- Строки 174 → 175. Внешняя связь: Одна предикация / именное описание
- Строки 176 → 177. Состав и чтение конструкции: холодно [ADVB]; EXPERIENCER=Мне; impersonal state; dative participant experiences it; no separate grammatical subject

Первая записанная диагностика: нет.

### A33 — PASS

Курьер переадресовал письмо.

Результат шага обрезан в выгрузке.

- Строки 182 → 183. Внешняя связь: Одна предикация / именное описание
- Строки 184 → 185. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### A35 — FAIL

Мария перестала курить.

Результат шага обрезан в выгрузке.

- Строки 190 → 191. Внешняя связь: Одна предикация / именное описание
- Строки 192 → 193. Состав и чтение конструкции: Infinitive area «курить.»; remaining parent «Мария перестала»
- Строки 194 → 195. Внешняя связь: Одна предикация / именное описание
- Строки 196 → 197. Состав и чтение конструкции: «курить» fills OBJECT of «перестала» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Мария» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 198 → 199. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### A38-NOT — FAIL

Курьер не переадресовал письмо.

Результат шага обрезан в выгрузке.

- Строки 204 → 205. Внешняя связь: Отрицание
- Строки 206 → 207. Вводящее выражение: начало: Начать с «не» @7
- Строки 208 → 209. Вводящее выражение: конец: Закончить после «переадресовал» @23; выбранные слова «не переадресовал»
- Строки 210 → 211. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 212 → 213. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/structural/formulas`, `/structural/entity_aliases`.

### A38-QUOTED — FAIL

Иван сказал: «Курьер переадресовал письмо».

Результат шага обрезан в выгрузке.

- Строки 218 → 219. Внешняя связь: Пропозициональное содержание
- Строки 220 → 221. Вложенное содержание: начало: Начать с «Курьер» @14
- Строки 222 → 223. Вложенное содержание: конец: Закончить после «письмо» @41; выбранные слова «Курьер переадресовал письмо»
- Строки 224 → 225. Родительская часть: начало: Начать с «Иван» @0
- Строки 226 → 227. Родительская часть: конец: Закончить после «»» @42; выбранные слова «Иван сказал : « »»
- Строки 228 → 229. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал : « »»; content filling that slot: «Курьер переадресовал письмо»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 230 → 231. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 232 → 233. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 234 → 235. Внешняя связь: Одна предикация / именное описание
- Строки 236 → 237. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 238 → 239. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/structural/formulas`, `/structural/entity_aliases`.

### LANG-00-0-bare — PASS

Иван вошёл.

Результат шага обрезан в выгрузке.

- Строки 244 → 245. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-0-not — PASS

Неверно, что иван вошёл.

Результат шага обрезан в выгрузке.

- Строки 250 → 251. Внешняя связь: Отрицание
- Строки 252 → 253. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 254 → 255. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 256 → 257. Проверка разбиения: Proposed split — part 1: «иван вошёл»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 258 → 259. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-0-possible — PASS

Возможно, иван вошёл.

Результат шага обрезан в выгрузке.

- Строки 264 → 265. Внешняя связь: Возможность
- Строки 266 → 267. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 268 → 269. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 270 → 271. Проверка разбиения: Proposed split — part 1: «иван вошёл»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 272 → 273. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 274 → 275. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-0-quoted — FAIL

Мария сказала: «Иван вошёл».

Результат шага обрезан в выгрузке.

- Строки 280 → 281. Внешняя связь: Пропозициональное содержание
- Строки 282 → 283. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 284 → 285. Вложенное содержание: конец: Закончить после «вошёл» @26; выбранные слова «Иван вошёл»
- Строки 286 → 287. Родительская часть: начало: Начать с «Мария» @0
- Строки 288 → 289. Родительская часть: конец: Закончить после «»» @27; выбранные слова «Мария сказала : « »»
- Строки 290 → 291. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван вошёл»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 292 → 293. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 294 → 295. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 296 → 297. Внешняя связь: Одна предикация / именное описание
- Строки 298 → 299. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 300 → 301. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-00-0-before_point — PASS

В 09:00 иван вошёл.

Результат шага обрезан в выгрузке.

- Строки 306 → 307. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-0-yesterday — PASS

Вчера иван вошёл.

Результат шага обрезан в выгрузке.

- Строки 312 → 313. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-0-question — PASS

Верно ли, что иван вошёл?

Результат шага обрезан в выгрузке.

- Строки 318 → 319. Внешняя связь: Вопрос
- Строки 320 → 321. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 322 → 323. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 324 → 325. Проверка разбиения: Proposed split — part 1: «иван вошёл»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 326 → 327. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-00-1-bare — PASS

Пётр вошёл.

Результат шага обрезан в выгрузке.

- Строки 332 → 333. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-1-not — PASS

Неверно, что пётр вошёл.

Результат шага обрезан в выгрузке.

- Строки 338 → 339. Внешняя связь: Отрицание
- Строки 340 → 341. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 342 → 343. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 344 → 345. Проверка разбиения: Proposed split — part 1: «пётр вошёл»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 346 → 347. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-1-possible — PASS

Возможно, пётр вошёл.

Результат шага обрезан в выгрузке.

- Строки 352 → 353. Внешняя связь: Возможность
- Строки 354 → 355. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 356 → 357. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 358 → 359. Проверка разбиения: Proposed split — part 1: «пётр вошёл»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 360 → 361. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 362 → 363. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-1-quoted — FAIL

Мария сказала: «Пётр вошёл».

Результат шага обрезан в выгрузке.

- Строки 368 → 369. Внешняя связь: Пропозициональное содержание
- Строки 370 → 371. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 372 → 373. Вложенное содержание: конец: Закончить после «вошёл» @26; выбранные слова «Пётр вошёл»
- Строки 374 → 375. Родительская часть: начало: Начать с «Мария» @0
- Строки 376 → 377. Родительская часть: конец: Закончить после «.» @28; выбранные слова «Мария сказала : « » .»
- Строки 378 → 379. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Пётр вошёл»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 380 → 381. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 382 → 383. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 384 → 385. Внешняя связь: Одна предикация / именное описание
- Строки 386 → 387. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 388 → 389. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-00-1-before_point — PASS

В 09:00 пётр вошёл.

Результат шага обрезан в выгрузке.

- Строки 394 → 395. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-1-yesterday — PASS

Вчера пётр вошёл.

Результат шага обрезан в выгрузке.

- Строки 400 → 401. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-1-question — PASS

Верно ли, что пётр вошёл?

Результат шага обрезан в выгрузке.

- Строки 406 → 407. Внешняя связь: Вопрос
- Строки 408 → 409. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 410 → 411. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 412 → 413. Проверка разбиения: Proposed split — part 1: «пётр вошёл»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 414 → 415. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-00-2-bare — PASS

Сергей вошёл.

Результат шага обрезан в выгрузке.

- Строки 420 → 421. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-2-not — PASS

Неверно, что сергей вошёл.

Результат шага обрезан в выгрузке.

- Строки 426 → 427. Внешняя связь: Отрицание
- Строки 428 → 429. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 430 → 431. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 432 → 433. Проверка разбиения: Proposed split — part 1: «сергей вошёл»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 434 → 435. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-2-possible — PASS

Возможно, сергей вошёл.

Результат шага обрезан в выгрузке.

- Строки 440 → 441. Внешняя связь: Возможность
- Строки 442 → 443. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 444 → 445. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 446 → 447. Проверка разбиения: Proposed split — part 1: «сергей вошёл»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 448 → 449. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 450 → 451. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-2-quoted — FAIL

Мария сказала: «Сергей вошёл».

Результат шага обрезан в выгрузке.

- Строки 456 → 457. Внешняя связь: Пропозициональное содержание
- Строки 458 → 459. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 460 → 461. Вложенное содержание: конец: Закончить после «вошёл» @28; выбранные слова «Сергей вошёл»
- Строки 462 → 463. Родительская часть: начало: Начать с «Мария» @0
- Строки 464 → 465. Родительская часть: конец: Закончить после «»» @29; выбранные слова «Мария сказала : « »»
- Строки 466 → 467. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей вошёл»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 468 → 469. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 470 → 471. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 472 → 473. Внешняя связь: Одна предикация / именное описание
- Строки 474 → 475. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 476 → 477. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-00-2-before_point — PASS

В 09:00 сергей вошёл.

Результат шага обрезан в выгрузке.

- Строки 482 → 483. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-2-yesterday — PASS

Вчера сергей вошёл.

Результат шага обрезан в выгрузке.

- Строки 488 → 489. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-2-question — PASS

Верно ли, что сергей вошёл?

Результат шага обрезан в выгрузке.

- Строки 494 → 495. Внешняя связь: Вопрос
- Строки 496 → 497. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 498 → 499. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 500 → 501. Проверка разбиения: Proposed split — part 1: «сергей вошёл»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 502 → 503. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-00-3-bare — PASS

Алексей вошёл.

Результат шага обрезан в выгрузке.

- Строки 508 → 509. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-3-not — PASS

Неверно, что алексей вошёл.

Результат шага обрезан в выгрузке.

- Строки 514 → 515. Внешняя связь: Отрицание
- Строки 516 → 517. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 518 → 519. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 520 → 521. Проверка разбиения: Proposed split — part 1: «алексей вошёл»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 522 → 523. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-3-possible — PASS

Возможно, алексей вошёл.

Результат шага обрезан в выгрузке.

- Строки 528 → 529. Внешняя связь: Возможность
- Строки 530 → 531. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 532 → 533. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 534 → 535. Проверка разбиения: Proposed split — part 1: «алексей вошёл»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 536 → 537. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 538 → 539. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-3-quoted — FAIL

Мария сказала: «Алексей вошёл».

Результат шага обрезан в выгрузке.

- Строки 544 → 545. Внешняя связь: Пропозициональное содержание
- Строки 546 → 547. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 548 → 549. Вложенное содержание: конец: Закончить после «вошёл» @29; выбранные слова «Алексей вошёл»
- Строки 550 → 551. Родительская часть: начало: Начать с «Мария» @0
- Строки 552 → 553. Родительская часть: конец: Закончить после «»» @30; выбранные слова «Мария сказала : « »»
- Строки 554 → 555. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей вошёл»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 556 → 557. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 558 → 559. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 560 → 561. Внешняя связь: Одна предикация / именное описание
- Строки 562 → 563. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 564 → 565. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-00-3-before_point — PASS

В 09:00 алексей вошёл.

Результат шага обрезан в выгрузке.

- Строки 570 → 571. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-3-yesterday — PASS

Вчера алексей вошёл.

Результат шага обрезан в выгрузке.

- Строки 576 → 577. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-00-3-question — PASS

Верно ли, что алексей вошёл?

Результат шага обрезан в выгрузке.

- Строки 582 → 583. Внешняя связь: Вопрос
- Строки 584 → 585. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 586 → 587. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 588 → 589. Проверка разбиения: Proposed split — part 1: «алексей вошёл»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 590 → 591. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-01-0-bare — PASS

Вошёл Иван.

Результат шага обрезан в выгрузке.

- Строки 596 → 597. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-0-not — PASS

Неверно, что вошёл Иван.

Результат шага обрезан в выгрузке.

- Строки 602 → 603. Внешняя связь: Отрицание
- Строки 604 → 605. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 606 → 607. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 608 → 609. Проверка разбиения: Proposed split — part 1: «вошёл Иван»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 610 → 611. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-0-possible — PASS

Возможно, вошёл Иван.

Результат шага обрезан в выгрузке.

- Строки 616 → 617. Внешняя связь: Возможность
- Строки 618 → 619. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 620 → 621. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 622 → 623. Проверка разбиения: Proposed split — part 1: «вошёл Иван»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 624 → 625. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 626 → 627. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-0-quoted — FAIL

Мария сказала: «Вошёл Иван».

Результат шага обрезан в выгрузке.

- Строки 632 → 633. Внешняя связь: Пропозициональное содержание
- Строки 634 → 635. Вложенное содержание: начало: Начать с «Вошёл» @16
- Строки 636 → 637. Вложенное содержание: конец: Закончить после «Иван» @26; выбранные слова «Вошёл Иван»
- Строки 638 → 639. Родительская часть: начало: Начать с «Мария» @0
- Строки 640 → 641. Родительская часть: конец: Закончить после «»» @27; выбранные слова «Мария сказала : « »»
- Строки 642 → 643. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Вошёл Иван»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 644 → 645. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 646 → 647. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 648 → 649. Внешняя связь: Одна предикация / именное описание
- Строки 650 → 651. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 652 → 653. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-01-0-before_point — PASS

В 09:00 вошёл Иван.

Результат шага обрезан в выгрузке.

- Строки 658 → 659. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-0-yesterday — PASS

Вчера вошёл Иван.

Результат шага обрезан в выгрузке.

- Строки 664 → 665. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-0-question — PASS

Верно ли, что вошёл Иван?

Результат шага обрезан в выгрузке.

- Строки 670 → 671. Внешняя связь: Вопрос
- Строки 672 → 673. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 674 → 675. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 676 → 677. Проверка разбиения: Proposed split — part 1: «вошёл Иван»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 678 → 679. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-01-1-bare — PASS

Вошёл Пётр.

Результат шага обрезан в выгрузке.

- Строки 684 → 685. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-1-not — PASS

Неверно, что вошёл Пётр.

Результат шага обрезан в выгрузке.

- Строки 690 → 691. Внешняя связь: Отрицание
- Строки 692 → 693. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 694 → 695. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 696 → 697. Проверка разбиения: Proposed split — part 1: «вошёл Пётр»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 698 → 699. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-1-possible — PASS

Возможно, вошёл Пётр.

Результат шага обрезан в выгрузке.

- Строки 704 → 705. Внешняя связь: Возможность
- Строки 706 → 707. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 708 → 709. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 710 → 711. Проверка разбиения: Proposed split — part 1: «вошёл Пётр»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 712 → 713. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 714 → 715. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-1-quoted — FAIL

Мария сказала: «Вошёл Пётр».

Результат шага обрезан в выгрузке.

- Строки 720 → 721. Внешняя связь: Пропозициональное содержание
- Строки 722 → 723. Вложенное содержание: начало: Начать с «Вошёл» @16
- Строки 724 → 725. Вложенное содержание: конец: Закончить после «Пётр» @26; выбранные слова «Вошёл Пётр»
- Строки 726 → 727. Родительская часть: начало: Начать с «Мария» @0
- Строки 728 → 729. Родительская часть: конец: Закончить после «»» @27; выбранные слова «Мария сказала : « »»
- Строки 730 → 731. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Вошёл Пётр»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 732 → 733. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 734 → 735. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 736 → 737. Внешняя связь: Одна предикация / именное описание
- Строки 738 → 739. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 740 → 741. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-01-1-before_point — PASS

В 09:00 вошёл Пётр.

Результат шага обрезан в выгрузке.

- Строки 746 → 747. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-1-yesterday — PASS

Вчера вошёл Пётр.

Результат шага обрезан в выгрузке.

- Строки 752 → 753. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-1-question — PASS

Верно ли, что вошёл Пётр?

Результат шага обрезан в выгрузке.

- Строки 758 → 759. Внешняя связь: Вопрос
- Строки 760 → 761. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 762 → 763. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 764 → 765. Проверка разбиения: Proposed split — part 1: «вошёл Пётр»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 766 → 767. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-01-2-bare — PASS

Вошёл Сергей.

Результат шага обрезан в выгрузке.

- Строки 772 → 773. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-2-not — PASS

Неверно, что вошёл Сергей.

Результат шага обрезан в выгрузке.

- Строки 778 → 779. Внешняя связь: Отрицание
- Строки 780 → 781. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 782 → 783. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 784 → 785. Проверка разбиения: Proposed split — part 1: «вошёл Сергей»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 786 → 787. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-2-possible — PASS

Возможно, вошёл Сергей.

Результат шага обрезан в выгрузке.

- Строки 792 → 793. Внешняя связь: Возможность
- Строки 794 → 795. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 796 → 797. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 798 → 799. Проверка разбиения: Proposed split — part 1: «вошёл Сергей»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 800 → 801. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 802 → 803. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-2-quoted — FAIL

Мария сказала: «Вошёл Сергей».

Результат шага обрезан в выгрузке.

- Строки 808 → 809. Внешняя связь: Пропозициональное содержание
- Строки 810 → 811. Вложенное содержание: начало: Начать с «Вошёл» @16
- Строки 812 → 813. Вложенное содержание: конец: Закончить после «Сергей» @28; выбранные слова «Вошёл Сергей»
- Строки 814 → 815. Родительская часть: начало: Начать с «Мария» @0
- Строки 816 → 817. Родительская часть: конец: Закончить после «»» @29; выбранные слова «Мария сказала : « »»
- Строки 818 → 819. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Вошёл Сергей»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 820 → 821. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 822 → 823. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 824 → 825. Внешняя связь: Одна предикация / именное описание
- Строки 826 → 827. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 828 → 829. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-01-2-before_point — PASS

В 09:00 вошёл Сергей.

Результат шага обрезан в выгрузке.

- Строки 834 → 835. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-2-yesterday — PASS

Вчера вошёл Сергей.

Результат шага обрезан в выгрузке.

- Строки 840 → 841. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-2-question — PASS

Верно ли, что вошёл Сергей?

Результат шага обрезан в выгрузке.

- Строки 846 → 847. Внешняя связь: Вопрос
- Строки 848 → 849. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 850 → 851. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 852 → 853. Проверка разбиения: Proposed split — part 1: «вошёл Сергей»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 854 → 855. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-01-3-bare — PASS

Вошёл Алексей.

Результат шага обрезан в выгрузке.

- Строки 860 → 861. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-3-not — PASS

Неверно, что вошёл Алексей.

Результат шага обрезан в выгрузке.

- Строки 866 → 867. Внешняя связь: Отрицание
- Строки 868 → 869. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 870 → 871. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 872 → 873. Проверка разбиения: Proposed split — part 1: «вошёл Алексей»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 874 → 875. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-3-possible — PASS

Возможно, вошёл Алексей.

Результат шага обрезан в выгрузке.

- Строки 880 → 881. Внешняя связь: Возможность
- Строки 882 → 883. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 884 → 885. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 886 → 887. Проверка разбиения: Proposed split — part 1: «вошёл Алексей»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 888 → 889. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 890 → 891. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-3-quoted — FAIL

Мария сказала: «Вошёл Алексей».

Результат шага обрезан в выгрузке.

- Строки 896 → 897. Внешняя связь: Пропозициональное содержание
- Строки 898 → 899. Вложенное содержание: начало: Начать с «Вошёл» @16
- Строки 900 → 901. Вложенное содержание: конец: Закончить после «Алексей» @29; выбранные слова «Вошёл Алексей»
- Строки 902 → 903. Родительская часть: начало: Начать с «Мария» @0
- Строки 904 → 905. Родительская часть: конец: Закончить после «»» @30; выбранные слова «Мария сказала : « »»
- Строки 906 → 907. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Вошёл Алексей»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 908 → 909. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 910 → 911. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 912 → 913. Внешняя связь: Одна предикация / именное описание
- Строки 914 → 915. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 916 → 917. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-01-3-before_point — PASS

В 09:00 вошёл Алексей.

Результат шага обрезан в выгрузке.

- Строки 922 → 923. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-3-yesterday — PASS

Вчера вошёл Алексей.

Результат шага обрезан в выгрузке.

- Строки 928 → 929. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-01-3-question — PASS

Верно ли, что вошёл Алексей?

Результат шага обрезан в выгрузке.

- Строки 934 → 935. Внешняя связь: Вопрос
- Строки 936 → 937. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 938 → 939. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 940 → 941. Проверка разбиения: Proposed split — part 1: «вошёл Алексей»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 942 → 943. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-02-0-bare — PASS

Иван читает книгу.

Результат шага обрезан в выгрузке.

- Строки 948 → 949. Внешняя связь: Одна предикация / именное описание
- Строки 950 → 951. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-0-not — PASS

Неверно, что иван читает книгу.

Результат шага обрезан в выгрузке.

- Строки 956 → 957. Внешняя связь: Отрицание
- Строки 958 → 959. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 960 → 961. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 962 → 963. Проверка разбиения: Proposed split — part 1: «иван читает книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 964 → 965. Внешняя связь: Одна предикация / именное описание
- Строки 966 → 967. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-0-possible — PASS

Возможно, иван читает книгу.

Результат шага обрезан в выгрузке.

- Строки 972 → 973. Внешняя связь: Возможность
- Строки 974 → 975. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 976 → 977. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 978 → 979. Проверка разбиения: Proposed split — part 1: «иван читает книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 980 → 981. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 982 → 983. Внешняя связь: Одна предикация / именное описание
- Строки 984 → 985. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-0-quoted — FAIL

Мария сказала: «Иван читает книгу».

Результат шага обрезан в выгрузке.

- Строки 990 → 991. Внешняя связь: Пропозициональное содержание
- Строки 992 → 993. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 994 → 995. Вложенное содержание: конец: Закончить после «книгу» @33; выбранные слова «Иван читает книгу»
- Строки 996 → 997. Родительская часть: начало: Начать с «Мария» @0
- Строки 998 → 999. Родительская часть: конец: Закончить после «»» @34; выбранные слова «Мария сказала : « »»
- Строки 1000 → 1001. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван читает книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1002 → 1003. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1004 → 1005. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1006 → 1007. Внешняя связь: Одна предикация / именное описание
- Строки 1008 → 1009. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1010 → 1011. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-02-0-before_point — PASS

В 09:00 иван читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1016 → 1017. Внешняя связь: Одна предикация / именное описание
- Строки 1018 → 1019. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-0-yesterday — PASS

Вчера иван читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1024 → 1025. Внешняя связь: Одна предикация / именное описание
- Строки 1026 → 1027. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-0-question — PASS

Верно ли, что иван читает книгу?

Результат шага обрезан в выгрузке.

- Строки 1032 → 1033. Внешняя связь: Вопрос
- Строки 1034 → 1035. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1036 → 1037. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1038 → 1039. Проверка разбиения: Proposed split — part 1: «иван читает книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1040 → 1041. Внешняя связь: Одна предикация / именное описание
- Строки 1042 → 1043. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-02-1-bare — PASS

Пётр читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1048 → 1049. Внешняя связь: Одна предикация / именное описание
- Строки 1050 → 1051. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-1-not — PASS

Неверно, что пётр читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1056 → 1057. Внешняя связь: Отрицание
- Строки 1058 → 1059. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1060 → 1061. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1062 → 1063. Проверка разбиения: Proposed split — part 1: «пётр читает книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1064 → 1065. Внешняя связь: Одна предикация / именное описание
- Строки 1066 → 1067. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-1-possible — PASS

Возможно, пётр читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1072 → 1073. Внешняя связь: Возможность
- Строки 1074 → 1075. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1076 → 1077. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1078 → 1079. Проверка разбиения: Proposed split — part 1: «пётр читает книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1080 → 1081. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1082 → 1083. Внешняя связь: Одна предикация / именное описание
- Строки 1084 → 1085. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-1-quoted — FAIL

Мария сказала: «Пётр читает книгу».

Результат шага обрезан в выгрузке.

- Строки 1090 → 1091. Внешняя связь: Пропозициональное содержание
- Строки 1092 → 1093. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 1094 → 1095. Вложенное содержание: конец: Закончить после «книгу» @33; выбранные слова «Пётр читает книгу»
- Строки 1096 → 1097. Родительская часть: начало: Начать с «Мария» @0
- Строки 1098 → 1099. Родительская часть: конец: Закончить после «.» @35; выбранные слова «Мария сказала : « » .»
- Строки 1100 → 1101. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Пётр читает книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 1102 → 1103. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1104 → 1105. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1106 → 1107. Внешняя связь: Одна предикация / именное описание
- Строки 1108 → 1109. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1110 → 1111. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-02-1-before_point — PASS

В 09:00 пётр читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1116 → 1117. Внешняя связь: Одна предикация / именное описание
- Строки 1118 → 1119. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-1-yesterday — PASS

Вчера пётр читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1124 → 1125. Внешняя связь: Одна предикация / именное описание
- Строки 1126 → 1127. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-1-question — PASS

Верно ли, что пётр читает книгу?

Результат шага обрезан в выгрузке.

- Строки 1132 → 1133. Внешняя связь: Вопрос
- Строки 1134 → 1135. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1136 → 1137. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1138 → 1139. Проверка разбиения: Proposed split — part 1: «пётр читает книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1140 → 1141. Внешняя связь: Одна предикация / именное описание
- Строки 1142 → 1143. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-02-2-bare — PASS

Сергей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1148 → 1149. Внешняя связь: Одна предикация / именное описание
- Строки 1150 → 1151. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-2-not — PASS

Неверно, что сергей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1156 → 1157. Внешняя связь: Отрицание
- Строки 1158 → 1159. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1160 → 1161. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1162 → 1163. Проверка разбиения: Proposed split — part 1: «сергей читает книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1164 → 1165. Внешняя связь: Одна предикация / именное описание
- Строки 1166 → 1167. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-2-possible — PASS

Возможно, сергей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1172 → 1173. Внешняя связь: Возможность
- Строки 1174 → 1175. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1176 → 1177. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1178 → 1179. Проверка разбиения: Proposed split — part 1: «сергей читает книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1180 → 1181. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1182 → 1183. Внешняя связь: Одна предикация / именное описание
- Строки 1184 → 1185. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-2-quoted — FAIL

Мария сказала: «Сергей читает книгу».

Результат шага обрезан в выгрузке.

- Строки 1190 → 1191. Внешняя связь: Пропозициональное содержание
- Строки 1192 → 1193. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 1194 → 1195. Вложенное содержание: конец: Закончить после «книгу» @35; выбранные слова «Сергей читает книгу»
- Строки 1196 → 1197. Родительская часть: начало: Начать с «Мария» @0
- Строки 1198 → 1199. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 1200 → 1201. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей читает книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1202 → 1203. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1204 → 1205. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1206 → 1207. Внешняя связь: Одна предикация / именное описание
- Строки 1208 → 1209. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1210 → 1211. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-02-2-before_point — PASS

В 09:00 сергей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1216 → 1217. Внешняя связь: Одна предикация / именное описание
- Строки 1218 → 1219. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-2-yesterday — PASS

Вчера сергей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1224 → 1225. Внешняя связь: Одна предикация / именное описание
- Строки 1226 → 1227. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-2-question — PASS

Верно ли, что сергей читает книгу?

Результат шага обрезан в выгрузке.

- Строки 1232 → 1233. Внешняя связь: Вопрос
- Строки 1234 → 1235. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1236 → 1237. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1238 → 1239. Проверка разбиения: Proposed split — part 1: «сергей читает книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1240 → 1241. Внешняя связь: Одна предикация / именное описание
- Строки 1242 → 1243. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-02-3-bare — PASS

Алексей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1248 → 1249. Внешняя связь: Одна предикация / именное описание
- Строки 1250 → 1251. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-3-not — PASS

Неверно, что алексей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1256 → 1257. Внешняя связь: Отрицание
- Строки 1258 → 1259. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1260 → 1261. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1262 → 1263. Проверка разбиения: Proposed split — part 1: «алексей читает книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1264 → 1265. Внешняя связь: Одна предикация / именное описание
- Строки 1266 → 1267. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-3-possible — PASS

Возможно, алексей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1272 → 1273. Внешняя связь: Возможность
- Строки 1274 → 1275. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1276 → 1277. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1278 → 1279. Проверка разбиения: Proposed split — part 1: «алексей читает книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1280 → 1281. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1282 → 1283. Внешняя связь: Одна предикация / именное описание
- Строки 1284 → 1285. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-3-quoted — FAIL

Мария сказала: «Алексей читает книгу».

Результат шага обрезан в выгрузке.

- Строки 1290 → 1291. Внешняя связь: Пропозициональное содержание
- Строки 1292 → 1293. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 1294 → 1295. Вложенное содержание: конец: Закончить после «книгу» @36; выбранные слова «Алексей читает книгу»
- Строки 1296 → 1297. Родительская часть: начало: Начать с «Мария» @0
- Строки 1298 → 1299. Родительская часть: конец: Закончить после «»» @37; выбранные слова «Мария сказала : « »»
- Строки 1300 → 1301. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей читает книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1302 → 1303. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1304 → 1305. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1306 → 1307. Внешняя связь: Одна предикация / именное описание
- Строки 1308 → 1309. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1310 → 1311. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-02-3-before_point — PASS

В 09:00 алексей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1316 → 1317. Внешняя связь: Одна предикация / именное описание
- Строки 1318 → 1319. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-3-yesterday — PASS

Вчера алексей читает книгу.

Результат шага обрезан в выгрузке.

- Строки 1324 → 1325. Внешняя связь: Одна предикация / именное описание
- Строки 1326 → 1327. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-02-3-question — PASS

Верно ли, что алексей читает книгу?

Результат шага обрезан в выгрузке.

- Строки 1332 → 1333. Внешняя связь: Вопрос
- Строки 1334 → 1335. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1336 → 1337. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1338 → 1339. Проверка разбиения: Proposed split — part 1: «алексей читает книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1340 → 1341. Внешняя связь: Одна предикация / именное описание
- Строки 1342 → 1343. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-03-0-bare — PASS

Книгу читает Иван.

Результат шага обрезан в выгрузке.

- Строки 1348 → 1349. Внешняя связь: Одна предикация / именное описание
- Строки 1350 → 1351. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-0-not — PASS

Неверно, что книгу читает Иван.

Результат шага обрезан в выгрузке.

- Строки 1356 → 1357. Внешняя связь: Отрицание
- Строки 1358 → 1359. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1360 → 1361. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1362 → 1363. Проверка разбиения: Proposed split — part 1: «книгу читает Иван»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1364 → 1365. Внешняя связь: Одна предикация / именное описание
- Строки 1366 → 1367. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-0-possible — PASS

Возможно, книгу читает Иван.

Результат шага обрезан в выгрузке.

- Строки 1372 → 1373. Внешняя связь: Возможность
- Строки 1374 → 1375. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1376 → 1377. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1378 → 1379. Проверка разбиения: Proposed split — part 1: «книгу читает Иван»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1380 → 1381. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1382 → 1383. Внешняя связь: Одна предикация / именное описание
- Строки 1384 → 1385. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-0-quoted — FAIL

Мария сказала: «Книгу читает Иван».

Результат шага обрезан в выгрузке.

- Строки 1390 → 1391. Внешняя связь: Одна предикация / именное описание
- Строки 1392 → 1393. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-03-0-before_point — PASS

В 09:00 книгу читает Иван.

Результат шага обрезан в выгрузке.

- Строки 1398 → 1399. Внешняя связь: Одна предикация / именное описание
- Строки 1400 → 1401. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-0-yesterday — PASS

Вчера книгу читает Иван.

Результат шага обрезан в выгрузке.

- Строки 1406 → 1407. Внешняя связь: Одна предикация / именное описание
- Строки 1408 → 1409. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-0-question — FAIL

Верно ли, что книгу читает Иван?

Результат шага обрезан в выгрузке.

- Строки 1414 → 1415. Внешняя связь: Вопрос
- Строки 1416 → 1417. Вводящее выражение: начало: Начать с «что» @10
- Строки 1418 → 1419. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «что»
- Строки 1420 → 1421. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 1422 → 1423. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/generation/gold_patterns`.

### LANG-03-1-bare — PASS

Книгу читает Пётр.

Результат шага обрезан в выгрузке.

- Строки 1428 → 1429. Внешняя связь: Одна предикация / именное описание
- Строки 1430 → 1431. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-1-not — PASS

Неверно, что книгу читает Пётр.

Результат шага обрезан в выгрузке.

- Строки 1436 → 1437. Внешняя связь: Отрицание
- Строки 1438 → 1439. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1440 → 1441. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1442 → 1443. Проверка разбиения: Proposed split — part 1: «книгу читает Пётр»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1444 → 1445. Внешняя связь: Одна предикация / именное описание
- Строки 1446 → 1447. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-1-possible — PASS

Возможно, книгу читает Пётр.

Результат шага обрезан в выгрузке.

- Строки 1452 → 1453. Внешняя связь: Возможность
- Строки 1454 → 1455. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1456 → 1457. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1458 → 1459. Проверка разбиения: Proposed split — part 1: «книгу читает Пётр»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1460 → 1461. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1462 → 1463. Внешняя связь: Одна предикация / именное описание
- Строки 1464 → 1465. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-1-quoted — FAIL

Мария сказала: «Книгу читает Пётр».

Результат шага обрезан в выгрузке.

- Строки 1470 → 1471. Внешняя связь: Пропозициональное содержание
- Строки 1472 → 1473. Вложенное содержание: начало: Начать с «Книгу» @16
- Строки 1474 → 1475. Вложенное содержание: конец: Закончить после «Пётр» @33; выбранные слова «Книгу читает Пётр»
- Строки 1476 → 1477. Родительская часть: начало: Начать с «Мария» @0
- Строки 1478 → 1479. Родительская часть: конец: Закончить после «»» @34; выбранные слова «Мария сказала : « »»
- Строки 1480 → 1481. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Книгу читает Пётр»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1482 → 1483. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1484 → 1485. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1486 → 1487. Внешняя связь: Одна предикация / именное описание
- Строки 1488 → 1489. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1490 → 1491. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-03-1-before_point — PASS

В 09:00 книгу читает Пётр.

Результат шага обрезан в выгрузке.

- Строки 1496 → 1497. Внешняя связь: Одна предикация / именное описание
- Строки 1498 → 1499. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-1-yesterday — PASS

Вчера книгу читает Пётр.

Результат шага обрезан в выгрузке.

- Строки 1504 → 1505. Внешняя связь: Одна предикация / именное описание
- Строки 1506 → 1507. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-1-question — PASS

Верно ли, что книгу читает Пётр?

Результат шага обрезан в выгрузке.

- Строки 1512 → 1513. Внешняя связь: Вопрос
- Строки 1514 → 1515. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1516 → 1517. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1518 → 1519. Проверка разбиения: Proposed split — part 1: «книгу читает Пётр»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1520 → 1521. Внешняя связь: Одна предикация / именное описание
- Строки 1522 → 1523. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-03-2-bare — PASS

Книгу читает Сергей.

Результат шага обрезан в выгрузке.

- Строки 1528 → 1529. Внешняя связь: Одна предикация / именное описание
- Строки 1530 → 1531. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-2-not — PASS

Неверно, что книгу читает Сергей.

Результат шага обрезан в выгрузке.

- Строки 1536 → 1537. Внешняя связь: Отрицание
- Строки 1538 → 1539. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1540 → 1541. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1542 → 1543. Проверка разбиения: Proposed split — part 1: «книгу читает Сергей»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1544 → 1545. Внешняя связь: Одна предикация / именное описание
- Строки 1546 → 1547. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-2-possible — PASS

Возможно, книгу читает Сергей.

Результат шага обрезан в выгрузке.

- Строки 1552 → 1553. Внешняя связь: Возможность
- Строки 1554 → 1555. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1556 → 1557. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1558 → 1559. Проверка разбиения: Proposed split — part 1: «книгу читает Сергей»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1560 → 1561. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1562 → 1563. Внешняя связь: Одна предикация / именное описание
- Строки 1564 → 1565. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-2-quoted — FAIL

Мария сказала: «Книгу читает Сергей».

Результат шага обрезан в выгрузке.

- Строки 1570 → 1571. Внешняя связь: Пропозициональное содержание
- Строки 1572 → 1573. Вложенное содержание: начало: Начать с «Книгу» @16
- Строки 1574 → 1575. Вложенное содержание: конец: Закончить после «Сергей» @35; выбранные слова «Книгу читает Сергей»
- Строки 1576 → 1577. Родительская часть: начало: Начать с «Мария» @0
- Строки 1578 → 1579. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 1580 → 1581. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Книгу читает Сергей»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1582 → 1583. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1584 → 1585. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1586 → 1587. Внешняя связь: Одна предикация / именное описание
- Строки 1588 → 1589. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1590 → 1591. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-03-2-before_point — PASS

В 09:00 книгу читает Сергей.

Результат шага обрезан в выгрузке.

- Строки 1596 → 1597. Внешняя связь: Одна предикация / именное описание
- Строки 1598 → 1599. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-2-yesterday — PASS

Вчера книгу читает Сергей.

Результат шага обрезан в выгрузке.

- Строки 1604 → 1605. Внешняя связь: Одна предикация / именное описание
- Строки 1606 → 1607. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-2-question — PASS

Верно ли, что книгу читает Сергей?

Результат шага обрезан в выгрузке.

- Строки 1612 → 1613. Внешняя связь: Вопрос
- Строки 1614 → 1615. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1616 → 1617. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1618 → 1619. Проверка разбиения: Proposed split — part 1: «книгу читает Сергей»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1620 → 1621. Внешняя связь: Одна предикация / именное описание
- Строки 1622 → 1623. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-03-3-bare — PASS

Книгу читает Алексей.

Результат шага обрезан в выгрузке.

- Строки 1628 → 1629. Внешняя связь: Одна предикация / именное описание
- Строки 1630 → 1631. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-3-not — PASS

Неверно, что книгу читает Алексей.

Результат шага обрезан в выгрузке.

- Строки 1636 → 1637. Внешняя связь: Отрицание
- Строки 1638 → 1639. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1640 → 1641. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1642 → 1643. Проверка разбиения: Proposed split — part 1: «книгу читает Алексей»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1644 → 1645. Внешняя связь: Одна предикация / именное описание
- Строки 1646 → 1647. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-3-possible — PASS

Возможно, книгу читает Алексей.

Результат шага обрезан в выгрузке.

- Строки 1652 → 1653. Внешняя связь: Возможность
- Строки 1654 → 1655. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1656 → 1657. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1658 → 1659. Проверка разбиения: Proposed split — part 1: «книгу читает Алексей»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1660 → 1661. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1662 → 1663. Внешняя связь: Одна предикация / именное описание
- Строки 1664 → 1665. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-3-quoted — FAIL

Мария сказала: «Книгу читает Алексей».

Результат шага обрезан в выгрузке.

- Строки 1670 → 1671. Внешняя связь: Пропозициональное содержание
- Строки 1672 → 1673. Вложенное содержание: начало: Начать с «Книгу» @16
- Строки 1674 → 1675. Вложенное содержание: конец: Закончить после «Алексей» @36; выбранные слова «Книгу читает Алексей»
- Строки 1676 → 1677. Родительская часть: начало: Начать с «Мария» @0
- Строки 1678 → 1679. Родительская часть: конец: Закончить после «»» @37; выбранные слова «Мария сказала : « »»
- Строки 1680 → 1681. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Книгу читает Алексей»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1682 → 1683. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1684 → 1685. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1686 → 1687. Внешняя связь: Одна предикация / именное описание
- Строки 1688 → 1689. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1690 → 1691. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-03-3-before_point — PASS

В 09:00 книгу читает Алексей.

Результат шага обрезан в выгрузке.

- Строки 1696 → 1697. Внешняя связь: Одна предикация / именное описание
- Строки 1698 → 1699. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-3-yesterday — PASS

Вчера книгу читает Алексей.

Результат шага обрезан в выгрузке.

- Строки 1704 → 1705. Внешняя связь: Одна предикация / именное описание
- Строки 1706 → 1707. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### LANG-03-3-question — PASS

Верно ли, что книгу читает Алексей?

Результат шага обрезан в выгрузке.

- Строки 1712 → 1713. Внешняя связь: Вопрос
- Строки 1714 → 1715. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1716 → 1717. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1718 → 1719. Проверка разбиения: Proposed split — part 1: «книгу читает Алексей»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1720 → 1721. Внешняя связь: Одна предикация / именное описание
- Строки 1722 → 1723. Именная зависимость: Direct role OBJECT of predicate «читает» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-04-0-bare — PASS

Иван передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1728 → 1729. Внешняя связь: Одна предикация / именное описание
- Строки 1730 → 1731. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1732 → 1733. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-0-not — PASS

Неверно, что иван передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1738 → 1739. Внешняя связь: Отрицание
- Строки 1740 → 1741. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1742 → 1743. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1744 → 1745. Проверка разбиения: Proposed split — part 1: «иван передал книгу Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1746 → 1747. Внешняя связь: Одна предикация / именное описание
- Строки 1748 → 1749. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1750 → 1751. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-0-possible — PASS

Возможно, иван передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1756 → 1757. Внешняя связь: Возможность
- Строки 1758 → 1759. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1760 → 1761. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1762 → 1763. Проверка разбиения: Proposed split — part 1: «иван передал книгу Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1764 → 1765. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1766 → 1767. Внешняя связь: Одна предикация / именное описание
- Строки 1768 → 1769. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1770 → 1771. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-0-quoted — FAIL

Мария сказала: «Иван передал книгу Марии».

Результат шага обрезан в выгрузке.

- Строки 1776 → 1777. Внешняя связь: Пропозициональное содержание
- Строки 1778 → 1779. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 1780 → 1781. Вложенное содержание: конец: Закончить после «Марии» @40; выбранные слова «Иван передал книгу Марии»
- Строки 1782 → 1783. Родительская часть: начало: Начать с «Мария» @0
- Строки 1784 → 1785. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 1786 → 1787. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван передал книгу Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1788 → 1789. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1790 → 1791. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1792 → 1793. Внешняя связь: Одна предикация / именное описание
- Строки 1794 → 1795. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1796 → 1797. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-04-0-before_point — PASS

В 09:00 иван передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1802 → 1803. Внешняя связь: Одна предикация / именное описание
- Строки 1804 → 1805. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1806 → 1807. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-0-yesterday — PASS

Вчера иван передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1812 → 1813. Внешняя связь: Одна предикация / именное описание
- Строки 1814 → 1815. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1816 → 1817. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-0-question — PASS

Верно ли, что иван передал книгу Марии?

Результат шага обрезан в выгрузке.

- Строки 1822 → 1823. Внешняя связь: Вопрос
- Строки 1824 → 1825. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1826 → 1827. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1828 → 1829. Проверка разбиения: Proposed split — part 1: «иван передал книгу Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1830 → 1831. Внешняя связь: Одна предикация / именное описание
- Строки 1832 → 1833. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1834 → 1835. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-04-1-bare — PASS

Пётр передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1840 → 1841. Внешняя связь: Одна предикация / именное описание
- Строки 1842 → 1843. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1844 → 1845. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-1-not — PASS

Неверно, что пётр передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1850 → 1851. Внешняя связь: Отрицание
- Строки 1852 → 1853. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1854 → 1855. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1856 → 1857. Проверка разбиения: Proposed split — part 1: «пётр передал книгу Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1858 → 1859. Внешняя связь: Одна предикация / именное описание
- Строки 1860 → 1861. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1862 → 1863. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-1-possible — PASS

Возможно, пётр передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1868 → 1869. Внешняя связь: Возможность
- Строки 1870 → 1871. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1872 → 1873. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1874 → 1875. Проверка разбиения: Proposed split — part 1: «пётр передал книгу Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1876 → 1877. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1878 → 1879. Внешняя связь: Одна предикация / именное описание
- Строки 1880 → 1881. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1882 → 1883. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-1-quoted — FAIL

Мария сказала: «Пётр передал книгу Марии».

Результат шага обрезан в выгрузке.

- Строки 1888 → 1889. Внешняя связь: Пропозициональное содержание
- Строки 1890 → 1891. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 1892 → 1893. Вложенное содержание: конец: Закончить после «Марии» @40; выбранные слова «Пётр передал книгу Марии»
- Строки 1894 → 1895. Родительская часть: начало: Начать с «Мария» @0
- Строки 1896 → 1897. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 1898 → 1899. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр передал книгу Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 1900 → 1901. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 1902 → 1903. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 1904 → 1905. Внешняя связь: Одна предикация / именное описание
- Строки 1906 → 1907. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 1908 → 1909. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-04-1-before_point — PASS

В 09:00 пётр передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1914 → 1915. Внешняя связь: Одна предикация / именное описание
- Строки 1916 → 1917. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1918 → 1919. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-1-yesterday — PASS

Вчера пётр передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1924 → 1925. Внешняя связь: Одна предикация / именное описание
- Строки 1926 → 1927. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1928 → 1929. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-1-question — PASS

Верно ли, что пётр передал книгу Марии?

Результат шага обрезан в выгрузке.

- Строки 1934 → 1935. Внешняя связь: Вопрос
- Строки 1936 → 1937. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 1938 → 1939. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 1940 → 1941. Проверка разбиения: Proposed split — part 1: «пётр передал книгу Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 1942 → 1943. Внешняя связь: Одна предикация / именное описание
- Строки 1944 → 1945. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1946 → 1947. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-04-2-bare — PASS

Сергей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1952 → 1953. Внешняя связь: Одна предикация / именное описание
- Строки 1954 → 1955. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1956 → 1957. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-2-not — PASS

Неверно, что сергей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1962 → 1963. Внешняя связь: Отрицание
- Строки 1964 → 1965. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 1966 → 1967. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 1968 → 1969. Проверка разбиения: Proposed split — part 1: «сергей передал книгу Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 1970 → 1971. Внешняя связь: Одна предикация / именное описание
- Строки 1972 → 1973. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1974 → 1975. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-2-possible — PASS

Возможно, сергей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 1980 → 1981. Внешняя связь: Возможность
- Строки 1982 → 1983. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 1984 → 1985. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 1986 → 1987. Проверка разбиения: Proposed split — part 1: «сергей передал книгу Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 1988 → 1989. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 1990 → 1991. Внешняя связь: Одна предикация / именное описание
- Строки 1992 → 1993. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 1994 → 1995. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-2-quoted — FAIL

Мария сказала: «Сергей передал книгу Марии».

Результат шага обрезан в выгрузке.

- Строки 2000 → 2001. Внешняя связь: Пропозициональное содержание
- Строки 2002 → 2003. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 2004 → 2005. Вложенное содержание: конец: Закончить после «Марии» @42; выбранные слова «Сергей передал книгу Марии»
- Строки 2006 → 2007. Родительская часть: начало: Начать с «Мария» @0
- Строки 2008 → 2009. Родительская часть: конец: Закончить после «»» @43; выбранные слова «Мария сказала : « »»
- Строки 2010 → 2011. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей передал книгу Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2012 → 2013. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2014 → 2015. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2016 → 2017. Внешняя связь: Одна предикация / именное описание
- Строки 2018 → 2019. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2020 → 2021. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-04-2-before_point — PASS

В 09:00 сергей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2026 → 2027. Внешняя связь: Одна предикация / именное описание
- Строки 2028 → 2029. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2030 → 2031. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-2-yesterday — PASS

Вчера сергей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2036 → 2037. Внешняя связь: Одна предикация / именное описание
- Строки 2038 → 2039. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2040 → 2041. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-2-question — PASS

Верно ли, что сергей передал книгу Марии?

Результат шага обрезан в выгрузке.

- Строки 2046 → 2047. Внешняя связь: Вопрос
- Строки 2048 → 2049. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2050 → 2051. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2052 → 2053. Проверка разбиения: Proposed split — part 1: «сергей передал книгу Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2054 → 2055. Внешняя связь: Одна предикация / именное описание
- Строки 2056 → 2057. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2058 → 2059. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-04-3-bare — PASS

Алексей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2064 → 2065. Внешняя связь: Одна предикация / именное описание
- Строки 2066 → 2067. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2068 → 2069. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-3-not — PASS

Неверно, что алексей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2074 → 2075. Внешняя связь: Отрицание
- Строки 2076 → 2077. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2078 → 2079. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2080 → 2081. Проверка разбиения: Proposed split — part 1: «алексей передал книгу Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2082 → 2083. Внешняя связь: Одна предикация / именное описание
- Строки 2084 → 2085. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2086 → 2087. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-3-possible — PASS

Возможно, алексей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2092 → 2093. Внешняя связь: Возможность
- Строки 2094 → 2095. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2096 → 2097. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2098 → 2099. Проверка разбиения: Proposed split — part 1: «алексей передал книгу Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2100 → 2101. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2102 → 2103. Внешняя связь: Одна предикация / именное описание
- Строки 2104 → 2105. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2106 → 2107. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-3-quoted — FAIL

Мария сказала: «Алексей передал книгу Марии».

Результат шага обрезан в выгрузке.

- Строки 2112 → 2113. Внешняя связь: Пропозициональное содержание
- Строки 2114 → 2115. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 2116 → 2117. Вложенное содержание: конец: Закончить после «Марии» @43; выбранные слова «Алексей передал книгу Марии»
- Строки 2118 → 2119. Родительская часть: начало: Начать с «Мария» @0
- Строки 2120 → 2121. Родительская часть: конец: Закончить после «»» @44; выбранные слова «Мария сказала : « »»
- Строки 2122 → 2123. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей передал книгу Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2124 → 2125. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2126 → 2127. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2128 → 2129. Внешняя связь: Одна предикация / именное описание
- Строки 2130 → 2131. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2132 → 2133. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-04-3-before_point — PASS

В 09:00 алексей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2138 → 2139. Внешняя связь: Одна предикация / именное описание
- Строки 2140 → 2141. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2142 → 2143. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-3-yesterday — PASS

Вчера алексей передал книгу Марии.

Результат шага обрезан в выгрузке.

- Строки 2148 → 2149. Внешняя связь: Одна предикация / именное описание
- Строки 2150 → 2151. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2152 → 2153. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-04-3-question — PASS

Верно ли, что алексей передал книгу Марии?

Результат шага обрезан в выгрузке.

- Строки 2158 → 2159. Внешняя связь: Вопрос
- Строки 2160 → 2161. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2162 → 2163. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2164 → 2165. Проверка разбиения: Proposed split — part 1: «алексей передал книгу Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2166 → 2167. Внешняя связь: Одна предикация / именное описание
- Строки 2168 → 2169. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2170 → 2171. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-05-0-bare — PASS

Марии Иван передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2176 → 2177. Внешняя связь: Одна предикация / именное описание
- Строки 2178 → 2179. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2180 → 2181. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-0-not — PASS

Неверно, что марии Иван передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2186 → 2187. Внешняя связь: Отрицание
- Строки 2188 → 2189. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2190 → 2191. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2192 → 2193. Проверка разбиения: Proposed split — part 1: «марии Иван передал книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2194 → 2195. Внешняя связь: Одна предикация / именное описание
- Строки 2196 → 2197. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2198 → 2199. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-0-possible — PASS

Возможно, марии Иван передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2204 → 2205. Внешняя связь: Возможность
- Строки 2206 → 2207. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2208 → 2209. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2210 → 2211. Проверка разбиения: Proposed split — part 1: «марии Иван передал книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2212 → 2213. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2214 → 2215. Внешняя связь: Одна предикация / именное описание
- Строки 2216 → 2217. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2218 → 2219. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-0-quoted — FAIL

Мария сказала: «Марии Иван передал книгу».

Результат шага обрезан в выгрузке.

- Строки 2224 → 2225. Внешняя связь: Пропозициональное содержание
- Строки 2226 → 2227. Вложенное содержание: начало: Начать с «Марии» @16
- Строки 2228 → 2229. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Марии Иван передал книгу»
- Строки 2230 → 2231. Родительская часть: начало: Начать с «Мария» @0
- Строки 2232 → 2233. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 2234 → 2235. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Марии Иван передал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2236 → 2237. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2238 → 2239. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2240 → 2241. Внешняя связь: Одна предикация / именное описание
- Строки 2242 → 2243. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2244 → 2245. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-05-0-before_point — PASS

В 09:00 марии Иван передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2250 → 2251. Внешняя связь: Одна предикация / именное описание
- Строки 2252 → 2253. Присоединение именной группы: None is a quantity of this noun; retain its original morphology
- Строки 2254 → 2255. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2256 → 2257. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-0-yesterday — PASS

Вчера марии Иван передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2262 → 2263. Внешняя связь: Одна предикация / именное описание
- Строки 2264 → 2265. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2266 → 2267. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-0-question — PASS

Верно ли, что марии Иван передал книгу?

Результат шага обрезан в выгрузке.

- Строки 2272 → 2273. Внешняя связь: Вопрос
- Строки 2274 → 2275. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2276 → 2277. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2278 → 2279. Проверка разбиения: Proposed split — part 1: «марии Иван передал книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2280 → 2281. Внешняя связь: Одна предикация / именное описание
- Строки 2282 → 2283. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2284 → 2285. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-05-1-bare — PASS

Марии Пётр передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2290 → 2291. Внешняя связь: Одна предикация / именное описание
- Строки 2292 → 2293. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2294 → 2295. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-1-not — PASS

Неверно, что марии Пётр передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2300 → 2301. Внешняя связь: Отрицание
- Строки 2302 → 2303. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2304 → 2305. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2306 → 2307. Проверка разбиения: Proposed split — part 1: «марии Пётр передал книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2308 → 2309. Внешняя связь: Одна предикация / именное описание
- Строки 2310 → 2311. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2312 → 2313. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-1-possible — PASS

Возможно, марии Пётр передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2318 → 2319. Внешняя связь: Возможность
- Строки 2320 → 2321. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2322 → 2323. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2324 → 2325. Проверка разбиения: Proposed split — part 1: «марии Пётр передал книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2326 → 2327. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2328 → 2329. Внешняя связь: Одна предикация / именное описание
- Строки 2330 → 2331. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2332 → 2333. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-1-quoted — FAIL

Мария сказала: «Марии Пётр передал книгу».

Результат шага обрезан в выгрузке.

- Строки 2338 → 2339. Внешняя связь: Пропозициональное содержание
- Строки 2340 → 2341. Вложенное содержание: начало: Начать с «Марии» @16
- Строки 2342 → 2343. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Марии Пётр передал книгу»
- Строки 2344 → 2345. Родительская часть: начало: Начать с «Мария» @0
- Строки 2346 → 2347. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 2348 → 2349. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Марии Пётр передал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2350 → 2351. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2352 → 2353. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2354 → 2355. Внешняя связь: Одна предикация / именное описание
- Строки 2356 → 2357. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2358 → 2359. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-05-1-before_point — PASS

В 09:00 марии Пётр передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2364 → 2365. Внешняя связь: Одна предикация / именное описание
- Строки 2366 → 2367. Присоединение именной группы: None is a quantity of this noun; retain its original morphology
- Строки 2368 → 2369. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2370 → 2371. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-1-yesterday — PASS

Вчера марии Пётр передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2376 → 2377. Внешняя связь: Одна предикация / именное описание
- Строки 2378 → 2379. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2380 → 2381. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-1-question — PASS

Верно ли, что марии Пётр передал книгу?

Результат шага обрезан в выгрузке.

- Строки 2386 → 2387. Внешняя связь: Вопрос
- Строки 2388 → 2389. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2390 → 2391. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2392 → 2393. Проверка разбиения: Proposed split — part 1: «марии Пётр передал книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2394 → 2395. Внешняя связь: Одна предикация / именное описание
- Строки 2396 → 2397. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2398 → 2399. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-05-2-bare — PASS

Марии Сергей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2404 → 2405. Внешняя связь: Одна предикация / именное описание
- Строки 2406 → 2407. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2408 → 2409. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-2-not — PASS

Неверно, что марии Сергей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2414 → 2415. Внешняя связь: Отрицание
- Строки 2416 → 2417. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2418 → 2419. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2420 → 2421. Проверка разбиения: Proposed split — part 1: «марии Сергей передал книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2422 → 2423. Внешняя связь: Одна предикация / именное описание
- Строки 2424 → 2425. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2426 → 2427. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-2-possible — PASS

Возможно, марии Сергей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2432 → 2433. Внешняя связь: Возможность
- Строки 2434 → 2435. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2436 → 2437. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2438 → 2439. Проверка разбиения: Proposed split — part 1: «марии Сергей передал книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2440 → 2441. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2442 → 2443. Внешняя связь: Одна предикация / именное описание
- Строки 2444 → 2445. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2446 → 2447. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-2-quoted — FAIL

Мария сказала: «Марии Сергей передал книгу».

Результат шага обрезан в выгрузке.

- Строки 2452 → 2453. Внешняя связь: Пропозициональное содержание
- Строки 2454 → 2455. Вложенное содержание: начало: Начать с «Марии» @16
- Строки 2456 → 2457. Вложенное содержание: конец: Закончить после «книгу» @42; выбранные слова «Марии Сергей передал книгу»
- Строки 2458 → 2459. Родительская часть: начало: Начать с «Мария» @0
- Строки 2460 → 2461. Родительская часть: конец: Закончить после «»» @43; выбранные слова «Мария сказала : « »»
- Строки 2462 → 2463. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Марии Сергей передал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2464 → 2465. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2466 → 2467. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2468 → 2469. Внешняя связь: Одна предикация / именное описание
- Строки 2470 → 2471. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2472 → 2473. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-05-2-before_point — PASS

В 09:00 марии Сергей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2478 → 2479. Внешняя связь: Одна предикация / именное описание
- Строки 2480 → 2481. Присоединение именной группы: None is a quantity of this noun; retain its original morphology
- Строки 2482 → 2483. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2484 → 2485. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-2-yesterday — PASS

Вчера марии Сергей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2490 → 2491. Внешняя связь: Одна предикация / именное описание
- Строки 2492 → 2493. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2494 → 2495. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-2-question — PASS

Верно ли, что марии Сергей передал книгу?

Результат шага обрезан в выгрузке.

- Строки 2500 → 2501. Внешняя связь: Вопрос
- Строки 2502 → 2503. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2504 → 2505. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2506 → 2507. Проверка разбиения: Proposed split — part 1: «марии Сергей передал книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2508 → 2509. Внешняя связь: Одна предикация / именное описание
- Строки 2510 → 2511. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2512 → 2513. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-05-3-bare — PASS

Марии Алексей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2518 → 2519. Внешняя связь: Одна предикация / именное описание
- Строки 2520 → 2521. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2522 → 2523. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-3-not — FAIL

Неверно, что марии Алексей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2528 → 2529. Внешняя связь: Отрицание
- Строки 2530 → 2531. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2532 → 2533. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2534 → 2535. Проверка разбиения: Proposed split — part 1: «марии Алексей передал книгу»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2536 → 2537. Внешняя связь: Одна предикация / именное описание
- Строки 2538 → 2539. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2540 → 2541. Именная зависимость: Недостаточно контекста (?)
- Строки 2542 → 2543. Внешняя связь: Одна предикация / именное описание
- Строки 2544 → 2545. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2546 → 2547. Именная зависимость: Недостаточно контекста (?)

Первая записанная диагностика: COMPONENT_DEPENDENCY_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`.

### LANG-05-3-possible — PASS

Возможно, марии Алексей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2552 → 2553. Внешняя связь: Возможность
- Строки 2554 → 2555. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2556 → 2557. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2558 → 2559. Проверка разбиения: Proposed split — part 1: «марии Алексей передал книгу»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2560 → 2561. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2562 → 2563. Внешняя связь: Одна предикация / именное описание
- Строки 2564 → 2565. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2566 → 2567. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-3-quoted — FAIL

Мария сказала: «Марии Алексей передал книгу».

Результат шага обрезан в выгрузке.

- Строки 2572 → 2573. Внешняя связь: Пропозициональное содержание
- Строки 2574 → 2575. Вложенное содержание: начало: Начать с «Марии» @16
- Строки 2576 → 2577. Вложенное содержание: конец: Закончить после «книгу» @43; выбранные слова «Марии Алексей передал книгу»
- Строки 2578 → 2579. Родительская часть: начало: Начать с «Мария» @0
- Строки 2580 → 2581. Родительская часть: конец: Закончить после «»» @44; выбранные слова «Мария сказала : « »»
- Строки 2582 → 2583. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Марии Алексей передал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2584 → 2585. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2586 → 2587. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2588 → 2589. Внешняя связь: Одна предикация / именное описание
- Строки 2590 → 2591. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2592 → 2593. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-05-3-before_point — PASS

В 09:00 марии Алексей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2598 → 2599. Внешняя связь: Одна предикация / именное описание
- Строки 2600 → 2601. Присоединение именной группы: None is a quantity of this noun; retain its original morphology
- Строки 2602 → 2603. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2604 → 2605. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-3-yesterday — PASS

Вчера марии Алексей передал книгу.

Результат шага обрезан в выгрузке.

- Строки 2610 → 2611. Внешняя связь: Одна предикация / именное описание
- Строки 2612 → 2613. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2614 → 2615. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-05-3-question — PASS

Верно ли, что марии Алексей передал книгу?

Результат шага обрезан в выгрузке.

- Строки 2620 → 2621. Внешняя связь: Вопрос
- Строки 2622 → 2623. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2624 → 2625. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2626 → 2627. Проверка разбиения: Proposed split — part 1: «марии Алексей передал книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2628 → 2629. Внешняя связь: Одна предикация / именное описание
- Строки 2630 → 2631. Именная зависимость: Direct role OBJECT of predicate «передал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 2632 → 2633. Именная зависимость: Direct role RECIPIENT of predicate «передал» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-06-0-bare — PASS

Иван — врач.

Результат шага обрезан в выгрузке.

- Строки 2638 → 2639. Внешняя связь: Одна предикация / именное описание
- Строки 2640 → 2641. Состав и чтение конструкции: врач [NOUN]; SUBJECT=Иван; noun predicate: «врач» describes what «Иван» is

Первая записанная диагностика: нет.

### LANG-06-0-not — PASS

Неверно, что иван — врач.

Результат шага обрезан в выгрузке.

- Строки 2646 → 2647. Внешняя связь: Отрицание
- Строки 2648 → 2649. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2650 → 2651. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2652 → 2653. Проверка разбиения: Proposed split — part 1: «иван — врач»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2654 → 2655. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2656 → 2657. Внешняя связь: Одна предикация / именное описание
- Строки 2658 → 2659. Состав и чтение конструкции: врач [NOUN]; SUBJECT=иван; noun predicate: «врач» describes what «иван» is

Первая записанная диагностика: нет.

### LANG-06-0-possible — PASS

Возможно, иван — врач.

Результат шага обрезан в выгрузке.

- Строки 2664 → 2665. Внешняя связь: Возможность
- Строки 2666 → 2667. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2668 → 2669. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2670 → 2671. Проверка разбиения: Proposed split — part 1: «иван — врач»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2672 → 2673. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2674 → 2675. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2676 → 2677. Внешняя связь: Одна предикация / именное описание
- Строки 2678 → 2679. Состав и чтение конструкции: врач [NOUN]; SUBJECT=иван; noun predicate: «врач» describes what «иван» is

Первая записанная диагностика: нет.

### LANG-06-0-quoted — FAIL

Мария сказала: «Иван — врач».

Результат шага обрезан в выгрузке.

- Строки 2684 → 2685. Внешняя связь: Пропозициональное содержание
- Строки 2686 → 2687. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 2688 → 2689. Вложенное содержание: конец: Закончить после «врач» @27; выбранные слова «Иван — врач»
- Строки 2690 → 2691. Родительская часть: начало: Начать с «Мария» @0
- Строки 2692 → 2693. Родительская часть: конец: Закончить после «»» @28; выбранные слова «Мария сказала : « »»
- Строки 2694 → 2695. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван — врач»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2696 → 2697. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2698 → 2699. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2700 → 2701. Внешняя связь: Одна предикация / именное описание
- Строки 2702 → 2703. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2704 → 2705. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-06-0-before_point — PASS

В 09:00 иван — врач.

Результат шага обрезан в выгрузке.

- Строки 2710 → 2711. Внешняя связь: Одна предикация / именное описание
- Строки 2712 → 2713. Состав и чтение конструкции: врач [NOUN]; SUBJECT=иван; noun predicate: «врач» describes what «иван» is

Первая записанная диагностика: нет.

### LANG-06-0-yesterday — PASS

Вчера иван — врач.

Результат шага обрезан в выгрузке.

- Строки 2718 → 2719. Внешняя связь: Одна предикация / именное описание
- Строки 2720 → 2721. Состав и чтение конструкции: врач [NOUN]; SUBJECT=иван; noun predicate: «врач» describes what «иван» is

Первая записанная диагностика: нет.

### LANG-06-0-continuous — PASS

Весь вчерашний день иван — врач.

Результат шага обрезан в выгрузке.

- Строки 2726 → 2727. Внешняя связь: Одна предикация / именное описание
- Строки 2728 → 2729. Состав и чтение конструкции: врач [NOUN]; SUBJECT=иван; noun predicate: «врач» describes what «иван» is

Первая записанная диагностика: нет.

### LANG-06-0-question — PASS

Верно ли, что иван — врач?

Результат шага обрезан в выгрузке.

- Строки 2734 → 2735. Внешняя связь: Вопрос
- Строки 2736 → 2737. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2738 → 2739. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2740 → 2741. Проверка разбиения: Proposed split — part 1: «иван — врач»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2742 → 2743. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2744 → 2745. Внешняя связь: Одна предикация / именное описание
- Строки 2746 → 2747. Состав и чтение конструкции: врач [NOUN]; SUBJECT=иван; noun predicate: «врач» describes what «иван» is

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-06-1-bare — PASS

Пётр — врач.

Результат шага обрезан в выгрузке.

- Строки 2752 → 2753. Внешняя связь: Одна предикация / именное описание
- Строки 2754 → 2755. Состав и чтение конструкции: врач [NOUN]; SUBJECT=Пётр; noun predicate: «врач» describes what «Пётр» is

Первая записанная диагностика: нет.

### LANG-06-1-not — PASS

Неверно, что пётр — врач.

Результат шага обрезан в выгрузке.

- Строки 2760 → 2761. Внешняя связь: Отрицание
- Строки 2762 → 2763. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2764 → 2765. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2766 → 2767. Проверка разбиения: Proposed split — part 1: «пётр — врач»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2768 → 2769. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2770 → 2771. Внешняя связь: Одна предикация / именное описание
- Строки 2772 → 2773. Состав и чтение конструкции: врач [NOUN]; SUBJECT=пётр; noun predicate: «врач» describes what «пётр» is

Первая записанная диагностика: нет.

### LANG-06-1-possible — PASS

Возможно, пётр — врач.

Результат шага обрезан в выгрузке.

- Строки 2778 → 2779. Внешняя связь: Возможность
- Строки 2780 → 2781. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2782 → 2783. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2784 → 2785. Проверка разбиения: Proposed split — part 1: «пётр — врач»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2786 → 2787. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2788 → 2789. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2790 → 2791. Внешняя связь: Одна предикация / именное описание
- Строки 2792 → 2793. Состав и чтение конструкции: врач [NOUN]; SUBJECT=пётр; noun predicate: «врач» describes what «пётр» is

Первая записанная диагностика: нет.

### LANG-06-1-quoted — FAIL

Мария сказала: «Пётр — врач».

Результат шага обрезан в выгрузке.

- Строки 2798 → 2799. Внешняя связь: Пропозициональное содержание
- Строки 2800 → 2801. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 2802 → 2803. Вложенное содержание: конец: Закончить после «врач» @27; выбранные слова «Пётр — врач»
- Строки 2804 → 2805. Родительская часть: начало: Начать с «Мария» @0
- Строки 2806 → 2807. Родительская часть: конец: Закончить после «»» @28; выбранные слова «Мария сказала : « »»
- Строки 2808 → 2809. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр — врач»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2810 → 2811. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2812 → 2813. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2814 → 2815. Внешняя связь: Одна предикация / именное описание
- Строки 2816 → 2817. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2818 → 2819. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-06-1-before_point — PASS

В 09:00 пётр — врач.

Результат шага обрезан в выгрузке.

- Строки 2824 → 2825. Внешняя связь: Одна предикация / именное описание
- Строки 2826 → 2827. Состав и чтение конструкции: врач [NOUN]; SUBJECT=пётр; noun predicate: «врач» describes what «пётр» is

Первая записанная диагностика: нет.

### LANG-06-1-yesterday — PASS

Вчера пётр — врач.

Результат шага обрезан в выгрузке.

- Строки 2832 → 2833. Внешняя связь: Одна предикация / именное описание
- Строки 2834 → 2835. Состав и чтение конструкции: врач [NOUN]; SUBJECT=пётр; noun predicate: «врач» describes what «пётр» is

Первая записанная диагностика: нет.

### LANG-06-1-continuous — PASS

Весь вчерашний день пётр — врач.

Результат шага обрезан в выгрузке.

- Строки 2840 → 2841. Внешняя связь: Одна предикация / именное описание
- Строки 2842 → 2843. Состав и чтение конструкции: врач [NOUN]; SUBJECT=пётр; noun predicate: «врач» describes what «пётр» is

Первая записанная диагностика: нет.

### LANG-06-1-question — PASS

Верно ли, что пётр — врач?

Результат шага обрезан в выгрузке.

- Строки 2848 → 2849. Внешняя связь: Вопрос
- Строки 2850 → 2851. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2852 → 2853. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2854 → 2855. Проверка разбиения: Proposed split — part 1: «пётр — врач»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2856 → 2857. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2858 → 2859. Внешняя связь: Одна предикация / именное описание
- Строки 2860 → 2861. Состав и чтение конструкции: врач [NOUN]; SUBJECT=пётр; noun predicate: «врач» describes what «пётр» is

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-06-2-bare — PASS

Сергей — врач.

Результат шага обрезан в выгрузке.

- Строки 2866 → 2867. Внешняя связь: Одна предикация / именное описание
- Строки 2868 → 2869. Состав и чтение конструкции: врач [NOUN]; SUBJECT=Сергей; noun predicate: «врач» describes what «Сергей» is

Первая записанная диагностика: нет.

### LANG-06-2-not — PASS

Неверно, что сергей — врач.

Результат шага обрезан в выгрузке.

- Строки 2874 → 2875. Внешняя связь: Отрицание
- Строки 2876 → 2877. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2878 → 2879. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2880 → 2881. Проверка разбиения: Proposed split — part 1: «сергей — врач»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2882 → 2883. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2884 → 2885. Внешняя связь: Одна предикация / именное описание
- Строки 2886 → 2887. Состав и чтение конструкции: врач [NOUN]; SUBJECT=сергей; noun predicate: «врач» describes what «сергей» is

Первая записанная диагностика: нет.

### LANG-06-2-possible — PASS

Возможно, сергей — врач.

Результат шага обрезан в выгрузке.

- Строки 2892 → 2893. Внешняя связь: Возможность
- Строки 2894 → 2895. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 2896 → 2897. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 2898 → 2899. Проверка разбиения: Proposed split — part 1: «сергей — врач»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 2900 → 2901. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 2902 → 2903. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2904 → 2905. Внешняя связь: Одна предикация / именное описание
- Строки 2906 → 2907. Состав и чтение конструкции: врач [NOUN]; SUBJECT=сергей; noun predicate: «врач» describes what «сергей» is

Первая записанная диагностика: нет.

### LANG-06-2-quoted — FAIL

Мария сказала: «Сергей — врач».

Результат шага обрезан в выгрузке.

- Строки 2912 → 2913. Внешняя связь: Пропозициональное содержание
- Строки 2914 → 2915. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 2916 → 2917. Вложенное содержание: конец: Закончить после «врач» @29; выбранные слова «Сергей — врач»
- Строки 2918 → 2919. Родительская часть: начало: Начать с «Мария» @0
- Строки 2920 → 2921. Родительская часть: конец: Закончить после «»» @30; выбранные слова «Мария сказала : « »»
- Строки 2922 → 2923. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей — врач»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 2924 → 2925. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 2926 → 2927. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 2928 → 2929. Внешняя связь: Одна предикация / именное описание
- Строки 2930 → 2931. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 2932 → 2933. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-06-2-before_point — PASS

В 09:00 сергей — врач.

Результат шага обрезан в выгрузке.

- Строки 2938 → 2939. Внешняя связь: Одна предикация / именное описание
- Строки 2940 → 2941. Состав и чтение конструкции: врач [NOUN]; SUBJECT=сергей; noun predicate: «врач» describes what «сергей» is

Первая записанная диагностика: нет.

### LANG-06-2-yesterday — PASS

Вчера сергей — врач.

Результат шага обрезан в выгрузке.

- Строки 2946 → 2947. Внешняя связь: Одна предикация / именное описание
- Строки 2948 → 2949. Состав и чтение конструкции: врач [NOUN]; SUBJECT=сергей; noun predicate: «врач» describes what «сергей» is

Первая записанная диагностика: нет.

### LANG-06-2-continuous — PASS

Весь вчерашний день сергей — врач.

Результат шага обрезан в выгрузке.

- Строки 2954 → 2955. Внешняя связь: Одна предикация / именное описание
- Строки 2956 → 2957. Состав и чтение конструкции: врач [NOUN]; SUBJECT=сергей; noun predicate: «врач» describes what «сергей» is

Первая записанная диагностика: нет.

### LANG-06-2-question — PASS

Верно ли, что сергей — врач?

Результат шага обрезан в выгрузке.

- Строки 2962 → 2963. Внешняя связь: Вопрос
- Строки 2964 → 2965. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 2966 → 2967. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 2968 → 2969. Проверка разбиения: Proposed split — part 1: «сергей — врач»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 2970 → 2971. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2972 → 2973. Внешняя связь: Одна предикация / именное описание
- Строки 2974 → 2975. Состав и чтение конструкции: врач [NOUN]; SUBJECT=сергей; noun predicate: «врач» describes what «сергей» is

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-06-3-bare — PASS

Алексей — врач.

Результат шага обрезан в выгрузке.

- Строки 2980 → 2981. Внешняя связь: Одна предикация / именное описание
- Строки 2982 → 2983. Состав и чтение конструкции: врач [NOUN]; SUBJECT=Алексей; noun predicate: «врач» describes what «Алексей» is

Первая записанная диагностика: нет.

### LANG-06-3-not — PASS

Неверно, что алексей — врач.

Результат шага обрезан в выгрузке.

- Строки 2988 → 2989. Внешняя связь: Отрицание
- Строки 2990 → 2991. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 2992 → 2993. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 2994 → 2995. Проверка разбиения: Proposed split — part 1: «алексей — врач»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 2996 → 2997. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 2998 → 2999. Внешняя связь: Одна предикация / именное описание
- Строки 3000 → 3001. Состав и чтение конструкции: врач [NOUN]; SUBJECT=алексей; noun predicate: «врач» describes what «алексей» is

Первая записанная диагностика: нет.

### LANG-06-3-possible — PASS

Возможно, алексей — врач.

Результат шага обрезан в выгрузке.

- Строки 3006 → 3007. Внешняя связь: Возможность
- Строки 3008 → 3009. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3010 → 3011. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3012 → 3013. Проверка разбиения: Proposed split — part 1: «алексей — врач»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3014 → 3015. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3016 → 3017. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 3018 → 3019. Внешняя связь: Одна предикация / именное описание
- Строки 3020 → 3021. Состав и чтение конструкции: врач [NOUN]; SUBJECT=алексей; noun predicate: «врач» describes what «алексей» is

Первая записанная диагностика: нет.

### LANG-06-3-quoted — FAIL

Мария сказала: «Алексей — врач».

Результат шага обрезан в выгрузке.

- Строки 3026 → 3027. Внешняя связь: Одна предикация / именное описание
- Строки 3028 → 3029. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-06-3-before_point — PASS

В 09:00 алексей — врач.

Результат шага обрезан в выгрузке.

- Строки 3034 → 3035. Внешняя связь: Одна предикация / именное описание
- Строки 3036 → 3037. Состав и чтение конструкции: врач [NOUN]; SUBJECT=алексей; noun predicate: «врач» describes what «алексей» is

Первая записанная диагностика: нет.

### LANG-06-3-yesterday — PASS

Вчера алексей — врач.

Результат шага обрезан в выгрузке.

- Строки 3042 → 3043. Внешняя связь: Одна предикация / именное описание
- Строки 3044 → 3045. Состав и чтение конструкции: врач [NOUN]; SUBJECT=алексей; noun predicate: «врач» describes what «алексей» is

Первая записанная диагностика: нет.

### LANG-06-3-continuous — PASS

Весь вчерашний день алексей — врач.

Результат шага обрезан в выгрузке.

- Строки 3050 → 3051. Внешняя связь: Одна предикация / именное описание
- Строки 3052 → 3053. Состав и чтение конструкции: врач [NOUN]; SUBJECT=алексей; noun predicate: «врач» describes what «алексей» is

Первая записанная диагностика: нет.

### LANG-06-3-question — PASS

Верно ли, что алексей — врач?

Результат шага обрезан в выгрузке.

- Строки 3058 → 3059. Внешняя связь: Вопрос
- Строки 3060 → 3061. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3062 → 3063. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3064 → 3065. Проверка разбиения: Proposed split — part 1: «алексей — врач»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3066 → 3067. Высказывание или название события: A complete clause: a predicate describes a participant, possibly without an explicit verb
- Строки 3068 → 3069. Внешняя связь: Одна предикация / именное описание
- Строки 3070 → 3071. Состав и чтение конструкции: врач [NOUN]; SUBJECT=алексей; noun predicate: «врач» describes what «алексей» is

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-07-0-bare — PASS

Иван устал.

Результат шага обрезан в выгрузке.

- Строки 3076 → 3077. Внешняя связь: Одна предикация / именное описание
- Строки 3078 → 3079. Состав и чтение конструкции: устать [VERB]; SUBJECT=Иван

Первая записанная диагностика: нет.

### LANG-07-0-not — PASS

Неверно, что иван устал.

Результат шага обрезан в выгрузке.

- Строки 3084 → 3085. Внешняя связь: Отрицание
- Строки 3086 → 3087. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3088 → 3089. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3090 → 3091. Проверка разбиения: Proposed split — part 1: «иван устал»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3092 → 3093. Внешняя связь: Одна предикация / именное описание
- Строки 3094 → 3095. Состав и чтение конструкции: устать [VERB]; SUBJECT=иван

Первая записанная диагностика: нет.

### LANG-07-0-possible — PASS

Возможно, иван устал.

Результат шага обрезан в выгрузке.

- Строки 3100 → 3101. Внешняя связь: Возможность
- Строки 3102 → 3103. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3104 → 3105. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3106 → 3107. Проверка разбиения: Proposed split — part 1: «иван устал»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3108 → 3109. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3110 → 3111. Внешняя связь: Одна предикация / именное описание
- Строки 3112 → 3113. Состав и чтение конструкции: устать [VERB]; SUBJECT=иван

Первая записанная диагностика: нет.

### LANG-07-0-quoted — FAIL

Мария сказала: «Иван устал».

Результат шага обрезан в выгрузке.

- Строки 3118 → 3119. Внешняя связь: Пропозициональное содержание
- Строки 3120 → 3121. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 3122 → 3123. Вложенное содержание: конец: Закончить после «устал» @26; выбранные слова «Иван устал»
- Строки 3124 → 3125. Родительская часть: начало: Начать с «Мария» @0
- Строки 3126 → 3127. Родительская часть: конец: Закончить после «»» @27; выбранные слова «Мария сказала : « »»
- Строки 3128 → 3129. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван устал»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3130 → 3131. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3132 → 3133. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3134 → 3135. Внешняя связь: Одна предикация / именное описание
- Строки 3136 → 3137. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3138 → 3139. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-07-0-before_point — PASS

В 09:00 иван устал.

Результат шага обрезан в выгрузке.

- Строки 3144 → 3145. Внешняя связь: Одна предикация / именное описание
- Строки 3146 → 3147. Состав и чтение конструкции: устать [VERB]; SUBJECT=иван

Первая записанная диагностика: нет.

### LANG-07-0-yesterday — PASS

Вчера иван устал.

Результат шага обрезан в выгрузке.

- Строки 3152 → 3153. Внешняя связь: Одна предикация / именное описание
- Строки 3154 → 3155. Состав и чтение конструкции: устать [VERB]; SUBJECT=иван

Первая записанная диагностика: нет.

### LANG-07-0-continuous — PASS

Весь вчерашний день иван устал.

Результат шага обрезан в выгрузке.

- Строки 3160 → 3161. Внешняя связь: Одна предикация / именное описание
- Строки 3162 → 3163. Состав и чтение конструкции: устать [VERB]; SUBJECT=иван

Первая записанная диагностика: нет.

### LANG-07-0-question — PASS

Верно ли, что иван устал?

Результат шага обрезан в выгрузке.

- Строки 3168 → 3169. Внешняя связь: Вопрос
- Строки 3170 → 3171. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3172 → 3173. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3174 → 3175. Проверка разбиения: Proposed split — part 1: «иван устал»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3176 → 3177. Внешняя связь: Одна предикация / именное описание
- Строки 3178 → 3179. Состав и чтение конструкции: устать [VERB]; SUBJECT=иван

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-07-1-bare — PASS

Пётр устал.

Результат шага обрезан в выгрузке.

- Строки 3184 → 3185. Внешняя связь: Одна предикация / именное описание
- Строки 3186 → 3187. Состав и чтение конструкции: устать [VERB]; SUBJECT=Пётр

Первая записанная диагностика: нет.

### LANG-07-1-not — PASS

Неверно, что пётр устал.

Результат шага обрезан в выгрузке.

- Строки 3192 → 3193. Внешняя связь: Отрицание
- Строки 3194 → 3195. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3196 → 3197. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3198 → 3199. Проверка разбиения: Proposed split — part 1: «пётр устал»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3200 → 3201. Внешняя связь: Одна предикация / именное описание
- Строки 3202 → 3203. Состав и чтение конструкции: устать [VERB]; SUBJECT=пётр

Первая записанная диагностика: нет.

### LANG-07-1-possible — PASS

Возможно, пётр устал.

Результат шага обрезан в выгрузке.

- Строки 3208 → 3209. Внешняя связь: Возможность
- Строки 3210 → 3211. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3212 → 3213. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3214 → 3215. Проверка разбиения: Proposed split — part 1: «пётр устал»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3216 → 3217. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3218 → 3219. Внешняя связь: Одна предикация / именное описание
- Строки 3220 → 3221. Состав и чтение конструкции: устать [VERB]; SUBJECT=пётр

Первая записанная диагностика: нет.

### LANG-07-1-quoted — FAIL

Мария сказала: «Пётр устал».

Результат шага обрезан в выгрузке.

- Строки 3226 → 3227. Внешняя связь: Пропозициональное содержание
- Строки 3228 → 3229. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 3230 → 3231. Вложенное содержание: конец: Закончить после «устал» @26; выбранные слова «Пётр устал»
- Строки 3232 → 3233. Родительская часть: начало: Начать с «Мария» @0
- Строки 3234 → 3235. Родительская часть: конец: Закончить после «»» @27; выбранные слова «Мария сказала : « »»
- Строки 3236 → 3237. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр устал»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3238 → 3239. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3240 → 3241. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3242 → 3243. Внешняя связь: Одна предикация / именное описание
- Строки 3244 → 3245. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3246 → 3247. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-07-1-before_point — PASS

В 09:00 пётр устал.

Результат шага обрезан в выгрузке.

- Строки 3252 → 3253. Внешняя связь: Одна предикация / именное описание
- Строки 3254 → 3255. Состав и чтение конструкции: устать [VERB]; SUBJECT=пётр

Первая записанная диагностика: нет.

### LANG-07-1-yesterday — PASS

Вчера пётр устал.

Результат шага обрезан в выгрузке.

- Строки 3260 → 3261. Внешняя связь: Одна предикация / именное описание
- Строки 3262 → 3263. Состав и чтение конструкции: устать [VERB]; SUBJECT=пётр

Первая записанная диагностика: нет.

### LANG-07-1-continuous — PASS

Весь вчерашний день пётр устал.

Результат шага обрезан в выгрузке.

- Строки 3268 → 3269. Внешняя связь: Одна предикация / именное описание
- Строки 3270 → 3271. Состав и чтение конструкции: устать [VERB]; SUBJECT=пётр

Первая записанная диагностика: нет.

### LANG-07-1-question — PASS

Верно ли, что пётр устал?

Результат шага обрезан в выгрузке.

- Строки 3276 → 3277. Внешняя связь: Вопрос
- Строки 3278 → 3279. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3280 → 3281. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3282 → 3283. Проверка разбиения: Proposed split — part 1: «пётр устал»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3284 → 3285. Внешняя связь: Одна предикация / именное описание
- Строки 3286 → 3287. Состав и чтение конструкции: устать [VERB]; SUBJECT=пётр

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-07-2-bare — PASS

Сергей устал.

Результат шага обрезан в выгрузке.

- Строки 3292 → 3293. Внешняя связь: Одна предикация / именное описание
- Строки 3294 → 3295. Состав и чтение конструкции: устать [VERB]; SUBJECT=Сергей

Первая записанная диагностика: нет.

### LANG-07-2-not — PASS

Неверно, что сергей устал.

Результат шага обрезан в выгрузке.

- Строки 3300 → 3301. Внешняя связь: Отрицание
- Строки 3302 → 3303. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3304 → 3305. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3306 → 3307. Проверка разбиения: Proposed split — part 1: «сергей устал»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3308 → 3309. Внешняя связь: Одна предикация / именное описание
- Строки 3310 → 3311. Состав и чтение конструкции: устать [VERB]; SUBJECT=сергей

Первая записанная диагностика: нет.

### LANG-07-2-possible — PASS

Возможно, сергей устал.

Результат шага обрезан в выгрузке.

- Строки 3316 → 3317. Внешняя связь: Возможность
- Строки 3318 → 3319. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3320 → 3321. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3322 → 3323. Проверка разбиения: Proposed split — part 1: «сергей устал»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3324 → 3325. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3326 → 3327. Внешняя связь: Одна предикация / именное описание
- Строки 3328 → 3329. Состав и чтение конструкции: устать [VERB]; SUBJECT=сергей

Первая записанная диагностика: нет.

### LANG-07-2-quoted — FAIL

Мария сказала: «Сергей устал».

Результат шага обрезан в выгрузке.

- Строки 3334 → 3335. Внешняя связь: Пропозициональное содержание
- Строки 3336 → 3337. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 3338 → 3339. Вложенное содержание: конец: Закончить после «устал» @28; выбранные слова «Сергей устал»
- Строки 3340 → 3341. Родительская часть: начало: Начать с «Мария» @0
- Строки 3342 → 3343. Родительская часть: конец: Закончить после «»» @29; выбранные слова «Мария сказала : « »»
- Строки 3344 → 3345. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей устал»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3346 → 3347. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3348 → 3349. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3350 → 3351. Внешняя связь: Одна предикация / именное описание
- Строки 3352 → 3353. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3354 → 3355. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-07-2-before_point — PASS

В 09:00 сергей устал.

Результат шага обрезан в выгрузке.

- Строки 3360 → 3361. Внешняя связь: Одна предикация / именное описание
- Строки 3362 → 3363. Состав и чтение конструкции: устать [VERB]; SUBJECT=сергей

Первая записанная диагностика: нет.

### LANG-07-2-yesterday — PASS

Вчера сергей устал.

Результат шага обрезан в выгрузке.

- Строки 3368 → 3369. Внешняя связь: Одна предикация / именное описание
- Строки 3370 → 3371. Состав и чтение конструкции: устать [VERB]; SUBJECT=сергей

Первая записанная диагностика: нет.

### LANG-07-2-continuous — PASS

Весь вчерашний день сергей устал.

Результат шага обрезан в выгрузке.

- Строки 3376 → 3377. Внешняя связь: Одна предикация / именное описание
- Строки 3378 → 3379. Состав и чтение конструкции: устать [VERB]; SUBJECT=сергей

Первая записанная диагностика: нет.

### LANG-07-2-question — PASS

Верно ли, что сергей устал?

Результат шага обрезан в выгрузке.

- Строки 3384 → 3385. Внешняя связь: Вопрос
- Строки 3386 → 3387. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3388 → 3389. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3390 → 3391. Проверка разбиения: Proposed split — part 1: «сергей устал»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3392 → 3393. Внешняя связь: Одна предикация / именное описание
- Строки 3394 → 3395. Состав и чтение конструкции: устать [VERB]; SUBJECT=сергей

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-07-3-bare — PASS

Алексей устал.

Результат шага обрезан в выгрузке.

- Строки 3400 → 3401. Внешняя связь: Одна предикация / именное описание
- Строки 3402 → 3403. Состав и чтение конструкции: устать [VERB]; SUBJECT=Алексей

Первая записанная диагностика: нет.

### LANG-07-3-not — PASS

Неверно, что алексей устал.

Результат шага обрезан в выгрузке.

- Строки 3408 → 3409. Внешняя связь: Отрицание
- Строки 3410 → 3411. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3412 → 3413. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3414 → 3415. Проверка разбиения: Proposed split — part 1: «алексей устал»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3416 → 3417. Внешняя связь: Одна предикация / именное описание
- Строки 3418 → 3419. Состав и чтение конструкции: устать [VERB]; SUBJECT=алексей

Первая записанная диагностика: нет.

### LANG-07-3-possible — PASS

Возможно, алексей устал.

Результат шага обрезан в выгрузке.

- Строки 3424 → 3425. Внешняя связь: Возможность
- Строки 3426 → 3427. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3428 → 3429. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3430 → 3431. Проверка разбиения: Proposed split — part 1: «алексей устал»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3432 → 3433. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3434 → 3435. Внешняя связь: Одна предикация / именное описание
- Строки 3436 → 3437. Состав и чтение конструкции: устать [VERB]; SUBJECT=алексей

Первая записанная диагностика: нет.

### LANG-07-3-quoted — FAIL

Мария сказала: «Алексей устал».

Результат шага обрезан в выгрузке.

- Строки 3442 → 3443. Внешняя связь: Пропозициональное содержание
- Строки 3444 → 3445. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 3446 → 3447. Вложенное содержание: конец: Закончить после «устал» @29; выбранные слова «Алексей устал»
- Строки 3448 → 3449. Родительская часть: начало: Начать с «Мария» @0
- Строки 3450 → 3451. Родительская часть: конец: Закончить после «»» @30; выбранные слова «Мария сказала : « »»
- Строки 3452 → 3453. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей устал»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3454 → 3455. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3456 → 3457. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3458 → 3459. Внешняя связь: Одна предикация / именное описание
- Строки 3460 → 3461. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3462 → 3463. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-07-3-before_point — PASS

В 09:00 алексей устал.

Результат шага обрезан в выгрузке.

- Строки 3468 → 3469. Внешняя связь: Одна предикация / именное описание
- Строки 3470 → 3471. Состав и чтение конструкции: устать [VERB]; SUBJECT=алексей

Первая записанная диагностика: нет.

### LANG-07-3-yesterday — PASS

Вчера алексей устал.

Результат шага обрезан в выгрузке.

- Строки 3476 → 3477. Внешняя связь: Одна предикация / именное описание
- Строки 3478 → 3479. Состав и чтение конструкции: устать [VERB]; SUBJECT=алексей

Первая записанная диагностика: нет.

### LANG-07-3-continuous — PASS

Весь вчерашний день алексей устал.

Результат шага обрезан в выгрузке.

- Строки 3484 → 3485. Внешняя связь: Одна предикация / именное описание
- Строки 3486 → 3487. Состав и чтение конструкции: устать [VERB]; SUBJECT=алексей

Первая записанная диагностика: нет.

### LANG-07-3-question — PASS

Верно ли, что алексей устал?

Результат шага обрезан в выгрузке.

- Строки 3492 → 3493. Внешняя связь: Вопрос
- Строки 3494 → 3495. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3496 → 3497. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3498 → 3499. Проверка разбиения: Proposed split — part 1: «алексей устал»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3500 → 3501. Внешняя связь: Одна предикация / именное описание
- Строки 3502 → 3503. Состав и чтение конструкции: устать [VERB]; SUBJECT=алексей

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-08-0-bare — PASS

Иван сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3508 → 3509. Внешняя связь: Одна предикация / именное описание
- Строки 3510 → 3511. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=Иван, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-0-not — PASS

Неверно, что иван сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3516 → 3517. Внешняя связь: Отрицание
- Строки 3518 → 3519. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3520 → 3521. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3522 → 3523. Проверка разбиения: Proposed split — part 1: «иван сидит на стуле»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3524 → 3525. Внешняя связь: Одна предикация / именное описание
- Строки 3526 → 3527. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=иван, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-0-possible — PASS

Возможно, иван сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3532 → 3533. Внешняя связь: Возможность
- Строки 3534 → 3535. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3536 → 3537. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3538 → 3539. Проверка разбиения: Proposed split — part 1: «иван сидит на стуле»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3540 → 3541. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3542 → 3543. Внешняя связь: Одна предикация / именное описание
- Строки 3544 → 3545. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=иван, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-0-quoted — FAIL

Мария сказала: «Иван сидит на стуле».

Результат шага обрезан в выгрузке.

- Строки 3550 → 3551. Внешняя связь: Пропозициональное содержание
- Строки 3552 → 3553. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 3554 → 3555. Вложенное содержание: конец: Закончить после «стуле» @35; выбранные слова «Иван сидит на стуле»
- Строки 3556 → 3557. Родительская часть: начало: Начать с «Мария» @0
- Строки 3558 → 3559. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 3560 → 3561. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван сидит на стуле»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3562 → 3563. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3564 → 3565. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3566 → 3567. Внешняя связь: Одна предикация / именное описание
- Строки 3568 → 3569. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3570 → 3571. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-08-0-before_point — PASS

В 09:00 иван сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3576 → 3577. Внешняя связь: Одна предикация / именное описание
- Строки 3578 → 3579. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=иван, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-0-yesterday — PASS

Вчера иван сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3584 → 3585. Внешняя связь: Одна предикация / именное описание
- Строки 3586 → 3587. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=иван, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-0-continuous — PASS

Весь вчерашний день иван сидел на стуле.

Результат шага обрезан в выгрузке.

- Строки 3592 → 3593. Внешняя связь: Одна предикация / именное описание
- Строки 3594 → 3595. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=иван, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-0-question — PASS

Верно ли, что иван сидит на стуле?

Результат шага обрезан в выгрузке.

- Строки 3600 → 3601. Внешняя связь: Вопрос
- Строки 3602 → 3603. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3604 → 3605. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3606 → 3607. Проверка разбиения: Proposed split — part 1: «иван сидит на стуле»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3608 → 3609. Внешняя связь: Одна предикация / именное описание
- Строки 3610 → 3611. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=иван, LOCATION=стуле

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-08-1-bare — PASS

Пётр сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3616 → 3617. Внешняя связь: Одна предикация / именное описание
- Строки 3618 → 3619. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=Пётр, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-1-not — PASS

Неверно, что пётр сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3624 → 3625. Внешняя связь: Отрицание
- Строки 3626 → 3627. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3628 → 3629. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3630 → 3631. Проверка разбиения: Proposed split — part 1: «пётр сидит на стуле»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3632 → 3633. Внешняя связь: Одна предикация / именное описание
- Строки 3634 → 3635. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=пётр, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-1-possible — PASS

Возможно, пётр сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3640 → 3641. Внешняя связь: Возможность
- Строки 3642 → 3643. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3644 → 3645. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3646 → 3647. Проверка разбиения: Proposed split — part 1: «пётр сидит на стуле»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3648 → 3649. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3650 → 3651. Внешняя связь: Одна предикация / именное описание
- Строки 3652 → 3653. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=пётр, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-1-quoted — FAIL

Мария сказала: «Пётр сидит на стуле».

Результат шага обрезан в выгрузке.

- Строки 3658 → 3659. Внешняя связь: Пропозициональное содержание
- Строки 3660 → 3661. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 3662 → 3663. Вложенное содержание: конец: Закончить после «стуле» @35; выбранные слова «Пётр сидит на стуле»
- Строки 3664 → 3665. Родительская часть: начало: Начать с «Мария» @0
- Строки 3666 → 3667. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 3668 → 3669. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр сидит на стуле»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3670 → 3671. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3672 → 3673. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3674 → 3675. Внешняя связь: Одна предикация / именное описание
- Строки 3676 → 3677. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3678 → 3679. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-08-1-before_point — PASS

В 09:00 пётр сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3684 → 3685. Внешняя связь: Одна предикация / именное описание
- Строки 3686 → 3687. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=пётр, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-1-yesterday — PASS

Вчера пётр сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3692 → 3693. Внешняя связь: Одна предикация / именное описание
- Строки 3694 → 3695. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=пётр, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-1-continuous — PASS

Весь вчерашний день пётр сидел на стуле.

Результат шага обрезан в выгрузке.

- Строки 3700 → 3701. Внешняя связь: Одна предикация / именное описание
- Строки 3702 → 3703. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=пётр, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-1-question — PASS

Верно ли, что пётр сидит на стуле?

Результат шага обрезан в выгрузке.

- Строки 3708 → 3709. Внешняя связь: Вопрос
- Строки 3710 → 3711. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3712 → 3713. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3714 → 3715. Проверка разбиения: Proposed split — part 1: «пётр сидит на стуле»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3716 → 3717. Внешняя связь: Одна предикация / именное описание
- Строки 3718 → 3719. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=пётр, LOCATION=стуле

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-08-2-bare — PASS

Сергей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3724 → 3725. Внешняя связь: Одна предикация / именное описание
- Строки 3726 → 3727. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=Сергей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-2-not — PASS

Неверно, что сергей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3732 → 3733. Внешняя связь: Отрицание
- Строки 3734 → 3735. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3736 → 3737. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3738 → 3739. Проверка разбиения: Proposed split — part 1: «сергей сидит на стуле»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3740 → 3741. Внешняя связь: Одна предикация / именное описание
- Строки 3742 → 3743. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=сергей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-2-possible — PASS

Возможно, сергей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3748 → 3749. Внешняя связь: Возможность
- Строки 3750 → 3751. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3752 → 3753. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3754 → 3755. Проверка разбиения: Proposed split — part 1: «сергей сидит на стуле»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3756 → 3757. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3758 → 3759. Внешняя связь: Одна предикация / именное описание
- Строки 3760 → 3761. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=сергей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-2-quoted — FAIL

Мария сказала: «Сергей сидит на стуле».

Результат шага обрезан в выгрузке.

- Строки 3766 → 3767. Внешняя связь: Пропозициональное содержание
- Строки 3768 → 3769. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 3770 → 3771. Вложенное содержание: конец: Закончить после «стуле» @37; выбранные слова «Сергей сидит на стуле»
- Строки 3772 → 3773. Родительская часть: начало: Начать с «Мария» @0
- Строки 3774 → 3775. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 3776 → 3777. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей сидит на стуле»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3778 → 3779. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3780 → 3781. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3782 → 3783. Внешняя связь: Одна предикация / именное описание
- Строки 3784 → 3785. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3786 → 3787. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-08-2-before_point — PASS

В 09:00 сергей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3792 → 3793. Внешняя связь: Одна предикация / именное описание
- Строки 3794 → 3795. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=сергей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-2-yesterday — PASS

Вчера сергей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3800 → 3801. Внешняя связь: Одна предикация / именное описание
- Строки 3802 → 3803. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=сергей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-2-continuous — PASS

Весь вчерашний день сергей сидел на стуле.

Результат шага обрезан в выгрузке.

- Строки 3808 → 3809. Внешняя связь: Одна предикация / именное описание
- Строки 3810 → 3811. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=сергей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-2-question — PASS

Верно ли, что сергей сидит на стуле?

Результат шага обрезан в выгрузке.

- Строки 3816 → 3817. Внешняя связь: Вопрос
- Строки 3818 → 3819. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3820 → 3821. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 3822 → 3823. Проверка разбиения: Proposed split — part 1: «сергей сидит на стуле»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 3824 → 3825. Внешняя связь: Одна предикация / именное описание
- Строки 3826 → 3827. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=сергей, LOCATION=стуле

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-08-3-bare — PASS

Алексей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3832 → 3833. Внешняя связь: Одна предикация / именное описание
- Строки 3834 → 3835. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=Алексей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-3-not — PASS

Неверно, что алексей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3840 → 3841. Внешняя связь: Отрицание
- Строки 3842 → 3843. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3844 → 3845. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3846 → 3847. Проверка разбиения: Proposed split — part 1: «алексей сидит на стуле»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3848 → 3849. Внешняя связь: Одна предикация / именное описание
- Строки 3850 → 3851. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=алексей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-3-possible — PASS

Возможно, алексей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3856 → 3857. Внешняя связь: Возможность
- Строки 3858 → 3859. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3860 → 3861. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3862 → 3863. Проверка разбиения: Proposed split — part 1: «алексей сидит на стуле»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3864 → 3865. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3866 → 3867. Внешняя связь: Одна предикация / именное описание
- Строки 3868 → 3869. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=алексей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-3-quoted — FAIL

Мария сказала: «Алексей сидит на стуле».

Результат шага обрезан в выгрузке.

- Строки 3874 → 3875. Внешняя связь: Пропозициональное содержание
- Строки 3876 → 3877. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 3878 → 3879. Вложенное содержание: конец: Закончить после «стуле» @38; выбранные слова «Алексей сидит на стуле»
- Строки 3880 → 3881. Родительская часть: начало: Начать с «Мария» @0
- Строки 3882 → 3883. Родительская часть: конец: Закончить после «.» @40; выбранные слова «Мария сказала : « » .»
- Строки 3884 → 3885. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Алексей сидит на стуле»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 3886 → 3887. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3888 → 3889. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3890 → 3891. Внешняя связь: Одна предикация / именное описание
- Строки 3892 → 3893. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3894 → 3895. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-08-3-before_point — PASS

В 09:00 алексей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3900 → 3901. Внешняя связь: Одна предикация / именное описание
- Строки 3902 → 3903. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=алексей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-3-yesterday — PASS

Вчера алексей сидит на стуле.

Результат шага обрезан в выгрузке.

- Строки 3908 → 3909. Внешняя связь: Одна предикация / именное описание
- Строки 3910 → 3911. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=алексей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-3-continuous — PASS

Весь вчерашний день алексей сидел на стуле.

Результат шага обрезан в выгрузке.

- Строки 3916 → 3917. Внешняя связь: Одна предикация / именное описание
- Строки 3918 → 3919. Состав и чтение конструкции: сидеть [VERB]; SUBJECT=алексей, LOCATION=стуле

Первая записанная диагностика: нет.

### LANG-08-3-question — FAIL

Верно ли, что алексей сидит на стуле?

Результат шага обрезан в выгрузке.

- Строки 3924 → 3925. Внешняя связь: Вопрос
- Строки 3926 → 3927. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 3928 → 3929. Вводящее выражение: конец: The text is "Верно ли, что алексей сидит на стуле?".
The query asks to select the complete words expressing the outer relation, including the full linking expression and any conjunction introducing its content.
The outer relation is introduced by "Верно ли" (Is it true) and the conjunction "что" (that) introduces the content proposition.
The instruction says: "Include the full linking expression and any conjunction introducing its content."
It also says: "Exclude the content proposition, its subject and predicate."
So we need to include "Верно", "ли", and "что".
We should exclude "алексей", "сидит", "на", "стуле".
The separating comma may be included.
The start is «Верно» @0.
The last token of the selected expression should be the conjunction "что".
Let's check the options:
Option 4: Закончить после «что» @13; выбранные слова «Верно ли , что». This matches the requirement to include the linking expression ("Верно ли") and the conjunction ("что") introducing the content, while excluding the content itself.

Therefore, Option 4 is the correct choice.

4

Первая записанная диагностика: COMPONENT_PROBE_FAILED.
Несовпавшие проверки: `/generation/gold_patterns`.

### LANG-09-0-bare — PASS

Иван работает.

Результат шага обрезан в выгрузке.

- Строки 3934 → 3935. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-0-not — PASS

Неверно, что иван работает.

Результат шага обрезан в выгрузке.

- Строки 3940 → 3941. Внешняя связь: Отрицание
- Строки 3942 → 3943. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 3944 → 3945. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 3946 → 3947. Проверка разбиения: Proposed split — part 1: «иван работает»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 3948 → 3949. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-0-possible — PASS

Возможно, иван работает.

Результат шага обрезан в выгрузке.

- Строки 3954 → 3955. Внешняя связь: Возможность
- Строки 3956 → 3957. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 3958 → 3959. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 3960 → 3961. Проверка разбиения: Proposed split — part 1: «иван работает»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 3962 → 3963. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 3964 → 3965. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-0-quoted — FAIL

Мария сказала: «Иван работает».

Результат шага обрезан в выгрузке.

- Строки 3970 → 3971. Внешняя связь: Пропозициональное содержание
- Строки 3972 → 3973. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 3974 → 3975. Вложенное содержание: конец: Закончить после «работает» @29; выбранные слова «Иван работает»
- Строки 3976 → 3977. Родительская часть: начало: Начать с «Мария» @0
- Строки 3978 → 3979. Родительская часть: конец: Закончить после «»» @30; выбранные слова «Мария сказала : « »»
- Строки 3980 → 3981. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван работает»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 3982 → 3983. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 3984 → 3985. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 3986 → 3987. Внешняя связь: Одна предикация / именное описание
- Строки 3988 → 3989. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 3990 → 3991. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-09-0-before_point — PASS

В 09:00 иван работает.

Результат шага обрезан в выгрузке.

- Строки 3996 → 3997. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-0-yesterday — PASS

Вчера иван работает.

Результат шага обрезан в выгрузке.

- Строки 4002 → 4003. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-0-continuous — PASS

Весь вчерашний день иван работал.

Результат шага обрезан в выгрузке.

- Строки 4008 → 4009. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-0-question — PASS

Верно ли, что иван работает?

Результат шага обрезан в выгрузке.

- Строки 4014 → 4015. Внешняя связь: Вопрос
- Строки 4016 → 4017. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4018 → 4019. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4020 → 4021. Проверка разбиения: Proposed split — part 1: «иван работает»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4022 → 4023. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-09-1-bare — PASS

Пётр работает.

Результат шага обрезан в выгрузке.

- Строки 4028 → 4029. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-1-not — PASS

Неверно, что пётр работает.

Результат шага обрезан в выгрузке.

- Строки 4034 → 4035. Внешняя связь: Отрицание
- Строки 4036 → 4037. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4038 → 4039. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4040 → 4041. Проверка разбиения: Proposed split — part 1: «пётр работает»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4042 → 4043. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-1-possible — PASS

Возможно, пётр работает.

Результат шага обрезан в выгрузке.

- Строки 4048 → 4049. Внешняя связь: Возможность
- Строки 4050 → 4051. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4052 → 4053. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4054 → 4055. Проверка разбиения: Proposed split — part 1: «пётр работает»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4056 → 4057. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4058 → 4059. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-1-quoted — FAIL

Мария сказала: «Пётр работает».

Результат шага обрезан в выгрузке.

- Строки 4064 → 4065. Внешняя связь: Пропозициональное содержание
- Строки 4066 → 4067. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 4068 → 4069. Вложенное содержание: конец: Закончить после «работает» @29; выбранные слова «Пётр работает»
- Строки 4070 → 4071. Родительская часть: начало: Начать с «Мария» @0
- Строки 4072 → 4073. Родительская часть: конец: Закончить после «»» @30; выбранные слова «Мария сказала : « »»
- Строки 4074 → 4075. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр работает»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4076 → 4077. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4078 → 4079. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4080 → 4081. Внешняя связь: Одна предикация / именное описание
- Строки 4082 → 4083. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4084 → 4085. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-09-1-before_point — PASS

В 09:00 пётр работает.

Результат шага обрезан в выгрузке.

- Строки 4090 → 4091. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-1-yesterday — PASS

Вчера пётр работает.

Результат шага обрезан в выгрузке.

- Строки 4096 → 4097. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-1-continuous — PASS

Весь вчерашний день пётр работал.

Результат шага обрезан в выгрузке.

- Строки 4102 → 4103. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-1-question — PASS

Верно ли, что пётр работает?

Результат шага обрезан в выгрузке.

- Строки 4108 → 4109. Внешняя связь: Вопрос
- Строки 4110 → 4111. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4112 → 4113. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4114 → 4115. Проверка разбиения: Proposed split — part 1: «пётр работает»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4116 → 4117. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-09-2-bare — PASS

Сергей работает.

Результат шага обрезан в выгрузке.

- Строки 4122 → 4123. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-2-not — PASS

Неверно, что сергей работает.

Результат шага обрезан в выгрузке.

- Строки 4128 → 4129. Внешняя связь: Отрицание
- Строки 4130 → 4131. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4132 → 4133. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4134 → 4135. Проверка разбиения: Proposed split — part 1: «сергей работает»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4136 → 4137. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-2-possible — PASS

Возможно, сергей работает.

Результат шага обрезан в выгрузке.

- Строки 4142 → 4143. Внешняя связь: Возможность
- Строки 4144 → 4145. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4146 → 4147. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4148 → 4149. Проверка разбиения: Proposed split — part 1: «сергей работает»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4150 → 4151. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4152 → 4153. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-2-quoted — FAIL

Мария сказала: «Сергей работает».

Результат шага обрезан в выгрузке.

- Строки 4158 → 4159. Внешняя связь: Пропозициональное содержание
- Строки 4160 → 4161. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 4162 → 4163. Вложенное содержание: конец: Закончить после «работает» @31; выбранные слова «Сергей работает»
- Строки 4164 → 4165. Родительская часть: начало: Начать с «Мария» @0
- Строки 4166 → 4167. Родительская часть: конец: Закончить после «»» @32; выбранные слова «Мария сказала : « »»
- Строки 4168 → 4169. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей работает»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4170 → 4171. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4172 → 4173. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4174 → 4175. Внешняя связь: Одна предикация / именное описание
- Строки 4176 → 4177. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4178 → 4179. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-09-2-before_point — PASS

В 09:00 сергей работает.

Результат шага обрезан в выгрузке.

- Строки 4184 → 4185. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-2-yesterday — PASS

Вчера сергей работает.

Результат шага обрезан в выгрузке.

- Строки 4190 → 4191. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-2-continuous — PASS

Весь вчерашний день сергей работал.

Результат шага обрезан в выгрузке.

- Строки 4196 → 4197. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-2-question — PASS

Верно ли, что сергей работает?

Результат шага обрезан в выгрузке.

- Строки 4202 → 4203. Внешняя связь: Вопрос
- Строки 4204 → 4205. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4206 → 4207. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4208 → 4209. Проверка разбиения: Proposed split — part 1: «сергей работает»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4210 → 4211. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-09-3-bare — PASS

Алексей работает.

Результат шага обрезан в выгрузке.

- Строки 4216 → 4217. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-3-not — PASS

Неверно, что алексей работает.

Результат шага обрезан в выгрузке.

- Строки 4222 → 4223. Внешняя связь: Отрицание
- Строки 4224 → 4225. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4226 → 4227. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4228 → 4229. Проверка разбиения: Proposed split — part 1: «алексей работает»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4230 → 4231. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-3-possible — PASS

Возможно, алексей работает.

Результат шага обрезан в выгрузке.

- Строки 4236 → 4237. Внешняя связь: Возможность
- Строки 4238 → 4239. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4240 → 4241. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4242 → 4243. Проверка разбиения: Proposed split — part 1: «алексей работает»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4244 → 4245. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4246 → 4247. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-3-quoted — FAIL

Мария сказала: «Алексей работает».

Результат шага обрезан в выгрузке.

- Строки 4252 → 4253. Внешняя связь: Пропозициональное содержание
- Строки 4254 → 4255. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 4256 → 4257. Вложенное содержание: конец: Закончить после «работает» @32; выбранные слова «Алексей работает»
- Строки 4258 → 4259. Родительская часть: начало: Начать с «Мария» @0
- Строки 4260 → 4261. Родительская часть: конец: Закончить после «»» @33; выбранные слова «Мария сказала : « »»
- Строки 4262 → 4263. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей работает»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4264 → 4265. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4266 → 4267. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4268 → 4269. Внешняя связь: Одна предикация / именное описание
- Строки 4270 → 4271. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4272 → 4273. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-09-3-before_point — PASS

В 09:00 алексей работает.

Результат шага обрезан в выгрузке.

- Строки 4278 → 4279. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-3-yesterday — PASS

Вчера алексей работает.

Результат шага обрезан в выгрузке.

- Строки 4284 → 4285. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-3-continuous — PASS

Весь вчерашний день алексей работал.

Результат шага обрезан в выгрузке.

- Строки 4290 → 4291. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LANG-09-3-question — PASS

Верно ли, что алексей работает?

Результат шага обрезан в выгрузке.

- Строки 4296 → 4297. Внешняя связь: Вопрос
- Строки 4298 → 4299. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4300 → 4301. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4302 → 4303. Проверка разбиения: Proposed split — part 1: «алексей работает»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4304 → 4305. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-10-0-bare — PASS

Иван открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4310 → 4311. Внешняя связь: Одна предикация / именное описание
- Строки 4312 → 4313. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-0-not — PASS

Неверно, что иван открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4318 → 4319. Внешняя связь: Отрицание
- Строки 4320 → 4321. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4322 → 4323. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4324 → 4325. Проверка разбиения: Proposed split — part 1: «иван открыл окно»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4326 → 4327. Внешняя связь: Одна предикация / именное описание
- Строки 4328 → 4329. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-0-possible — PASS

Возможно, иван открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4334 → 4335. Внешняя связь: Возможность
- Строки 4336 → 4337. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4338 → 4339. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4340 → 4341. Проверка разбиения: Proposed split — part 1: «иван открыл окно»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4342 → 4343. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4344 → 4345. Внешняя связь: Одна предикация / именное описание
- Строки 4346 → 4347. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-0-quoted — FAIL

Мария сказала: «Иван открыл окно».

Результат шага обрезан в выгрузке.

- Строки 4352 → 4353. Внешняя связь: Пропозициональное содержание
- Строки 4354 → 4355. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 4356 → 4357. Вложенное содержание: конец: Закончить после «окно» @32; выбранные слова «Иван открыл окно»
- Строки 4358 → 4359. Родительская часть: начало: Начать с «Мария» @0
- Строки 4360 → 4361. Родительская часть: конец: Закончить после «»» @33; выбранные слова «Мария сказала : « »»
- Строки 4362 → 4363. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван открыл окно»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4364 → 4365. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4366 → 4367. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4368 → 4369. Внешняя связь: Одна предикация / именное описание
- Строки 4370 → 4371. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4372 → 4373. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-10-0-before_point — PASS

В 09:00 иван открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4378 → 4379. Внешняя связь: Одна предикация / именное описание
- Строки 4380 → 4381. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-0-yesterday — PASS

Вчера иван открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4386 → 4387. Внешняя связь: Одна предикация / именное описание
- Строки 4388 → 4389. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-0-question — PASS

Верно ли, что иван открыл окно?

Результат шага обрезан в выгрузке.

- Строки 4394 → 4395. Внешняя связь: Вопрос
- Строки 4396 → 4397. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4398 → 4399. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4400 → 4401. Проверка разбиения: Proposed split — part 1: «иван открыл окно»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4402 → 4403. Внешняя связь: Одна предикация / именное описание
- Строки 4404 → 4405. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-10-1-bare — PASS

Пётр открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4410 → 4411. Внешняя связь: Одна предикация / именное описание
- Строки 4412 → 4413. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-1-not — PASS

Неверно, что пётр открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4418 → 4419. Внешняя связь: Отрицание
- Строки 4420 → 4421. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4422 → 4423. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4424 → 4425. Проверка разбиения: Proposed split — part 1: «пётр открыл окно»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4426 → 4427. Внешняя связь: Одна предикация / именное описание
- Строки 4428 → 4429. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-1-possible — PASS

Возможно, пётр открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4434 → 4435. Внешняя связь: Возможность
- Строки 4436 → 4437. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4438 → 4439. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4440 → 4441. Проверка разбиения: Proposed split — part 1: «пётр открыл окно»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4442 → 4443. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4444 → 4445. Внешняя связь: Одна предикация / именное описание
- Строки 4446 → 4447. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-1-quoted — FAIL

Мария сказала: «Пётр открыл окно».

Результат шага обрезан в выгрузке.

- Строки 4452 → 4453. Внешняя связь: Пропозициональное содержание
- Строки 4454 → 4455. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 4456 → 4457. Вложенное содержание: конец: Закончить после «окно» @32; выбранные слова «Пётр открыл окно»
- Строки 4458 → 4459. Родительская часть: начало: Начать с «Мария» @0
- Строки 4460 → 4461. Родительская часть: конец: Закончить после «»» @33; выбранные слова «Мария сказала : « »»
- Строки 4462 → 4463. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр открыл окно»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4464 → 4465. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4466 → 4467. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4468 → 4469. Внешняя связь: Одна предикация / именное описание
- Строки 4470 → 4471. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4472 → 4473. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-10-1-before_point — PASS

В 09:00 пётр открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4478 → 4479. Внешняя связь: Одна предикация / именное описание
- Строки 4480 → 4481. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-1-yesterday — PASS

Вчера пётр открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4486 → 4487. Внешняя связь: Одна предикация / именное описание
- Строки 4488 → 4489. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-1-question — PASS

Верно ли, что пётр открыл окно?

Результат шага обрезан в выгрузке.

- Строки 4494 → 4495. Внешняя связь: Вопрос
- Строки 4496 → 4497. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4498 → 4499. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4500 → 4501. Проверка разбиения: Proposed split — part 1: «пётр открыл окно»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4502 → 4503. Внешняя связь: Одна предикация / именное описание
- Строки 4504 → 4505. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-10-2-bare — PASS

Сергей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4510 → 4511. Внешняя связь: Одна предикация / именное описание
- Строки 4512 → 4513. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-2-not — PASS

Неверно, что сергей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4518 → 4519. Внешняя связь: Отрицание
- Строки 4520 → 4521. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4522 → 4523. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4524 → 4525. Проверка разбиения: Proposed split — part 1: «сергей открыл окно»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4526 → 4527. Внешняя связь: Одна предикация / именное описание
- Строки 4528 → 4529. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-2-possible — PASS

Возможно, сергей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4534 → 4535. Внешняя связь: Возможность
- Строки 4536 → 4537. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4538 → 4539. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4540 → 4541. Проверка разбиения: Proposed split — part 1: «сергей открыл окно»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4542 → 4543. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4544 → 4545. Внешняя связь: Одна предикация / именное описание
- Строки 4546 → 4547. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-2-quoted — FAIL

Мария сказала: «Сергей открыл окно».

Результат шага обрезан в выгрузке.

- Строки 4552 → 4553. Внешняя связь: Пропозициональное содержание
- Строки 4554 → 4555. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 4556 → 4557. Вложенное содержание: конец: Закончить после «окно» @34; выбранные слова «Сергей открыл окно»
- Строки 4558 → 4559. Родительская часть: начало: Начать с «Мария» @0
- Строки 4560 → 4561. Родительская часть: конец: Закончить после «»» @35; выбранные слова «Мария сказала : « »»
- Строки 4562 → 4563. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей открыл окно»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4564 → 4565. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4566 → 4567. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4568 → 4569. Внешняя связь: Одна предикация / именное описание
- Строки 4570 → 4571. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4572 → 4573. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-10-2-before_point — PASS

В 09:00 сергей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4578 → 4579. Внешняя связь: Одна предикация / именное описание
- Строки 4580 → 4581. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-2-yesterday — PASS

Вчера сергей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4586 → 4587. Внешняя связь: Одна предикация / именное описание
- Строки 4588 → 4589. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-2-question — PASS

Верно ли, что сергей открыл окно?

Результат шага обрезан в выгрузке.

- Строки 4594 → 4595. Внешняя связь: Вопрос
- Строки 4596 → 4597. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4598 → 4599. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4600 → 4601. Проверка разбиения: Proposed split — part 1: «сергей открыл окно»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4602 → 4603. Внешняя связь: Одна предикация / именное описание
- Строки 4604 → 4605. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-10-3-bare — PASS

Алексей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4610 → 4611. Внешняя связь: Одна предикация / именное описание
- Строки 4612 → 4613. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-3-not — PASS

Неверно, что алексей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4618 → 4619. Внешняя связь: Отрицание
- Строки 4620 → 4621. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4622 → 4623. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4624 → 4625. Проверка разбиения: Proposed split — part 1: «алексей открыл окно»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4626 → 4627. Внешняя связь: Одна предикация / именное описание
- Строки 4628 → 4629. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-3-possible — PASS

Возможно, алексей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4634 → 4635. Внешняя связь: Возможность
- Строки 4636 → 4637. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4638 → 4639. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4640 → 4641. Проверка разбиения: Proposed split — part 1: «алексей открыл окно»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4642 → 4643. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4644 → 4645. Внешняя связь: Одна предикация / именное описание
- Строки 4646 → 4647. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-3-quoted — FAIL

Мария сказала: «Алексей открыл окно».

Результат шага обрезан в выгрузке.

- Строки 4652 → 4653. Внешняя связь: Пропозициональное содержание
- Строки 4654 → 4655. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 4656 → 4657. Вложенное содержание: конец: Закончить после «окно» @35; выбранные слова «Алексей открыл окно»
- Строки 4658 → 4659. Родительская часть: начало: Начать с «Мария» @0
- Строки 4660 → 4661. Родительская часть: конец: Закончить после «.» @37; выбранные слова «Мария сказала : « » .»
- Строки 4662 → 4663. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Алексей открыл окно»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 4664 → 4665. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4666 → 4667. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4668 → 4669. Внешняя связь: Одна предикация / именное описание
- Строки 4670 → 4671. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4672 → 4673. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-10-3-before_point — PASS

В 09:00 алексей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4678 → 4679. Внешняя связь: Одна предикация / именное описание
- Строки 4680 → 4681. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-3-yesterday — PASS

Вчера алексей открыл окно.

Результат шага обрезан в выгрузке.

- Строки 4686 → 4687. Внешняя связь: Одна предикация / именное описание
- Строки 4688 → 4689. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-10-3-question — PASS

Верно ли, что алексей открыл окно?

Результат шага обрезан в выгрузке.

- Строки 4694 → 4695. Внешняя связь: Вопрос
- Строки 4696 → 4697. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4698 → 4699. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4700 → 4701. Проверка разбиения: Proposed split — part 1: «алексей открыл окно»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4702 → 4703. Внешняя связь: Одна предикация / именное описание
- Строки 4704 → 4705. Именная зависимость: Direct role OBJECT of predicate «открыл» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-11-0-bare — PASS

Иван позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4710 → 4711. Внешняя связь: Одна предикация / именное описание
- Строки 4712 → 4713. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-0-not — PASS

Неверно, что иван позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4718 → 4719. Внешняя связь: Отрицание
- Строки 4720 → 4721. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4722 → 4723. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4724 → 4725. Проверка разбиения: Proposed split — part 1: «иван позвонил Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4726 → 4727. Внешняя связь: Одна предикация / именное описание
- Строки 4728 → 4729. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-0-possible — PASS

Возможно, иван позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4734 → 4735. Внешняя связь: Возможность
- Строки 4736 → 4737. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4738 → 4739. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4740 → 4741. Проверка разбиения: Proposed split — part 1: «иван позвонил Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4742 → 4743. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4744 → 4745. Внешняя связь: Одна предикация / именное описание
- Строки 4746 → 4747. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-0-quoted — FAIL

Мария сказала: «Иван позвонил Марии».

Результат шага обрезан в выгрузке.

- Строки 4752 → 4753. Внешняя связь: Пропозициональное содержание
- Строки 4754 → 4755. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 4756 → 4757. Вложенное содержание: конец: Закончить после «Марии» @35; выбранные слова «Иван позвонил Марии»
- Строки 4758 → 4759. Родительская часть: начало: Начать с «Мария» @0
- Строки 4760 → 4761. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 4762 → 4763. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван позвонил Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4764 → 4765. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4766 → 4767. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4768 → 4769. Внешняя связь: Одна предикация / именное описание
- Строки 4770 → 4771. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4772 → 4773. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-11-0-before_point — PASS

В 09:00 иван позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4778 → 4779. Внешняя связь: Одна предикация / именное описание
- Строки 4780 → 4781. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-0-yesterday — PASS

Вчера иван позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4786 → 4787. Внешняя связь: Одна предикация / именное описание
- Строки 4788 → 4789. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-0-question — PASS

Верно ли, что иван позвонил Марии?

Результат шага обрезан в выгрузке.

- Строки 4794 → 4795. Внешняя связь: Вопрос
- Строки 4796 → 4797. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4798 → 4799. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4800 → 4801. Проверка разбиения: Proposed split — part 1: «иван позвонил Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4802 → 4803. Внешняя связь: Одна предикация / именное описание
- Строки 4804 → 4805. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-11-1-bare — PASS

Пётр позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4810 → 4811. Внешняя связь: Одна предикация / именное описание
- Строки 4812 → 4813. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-1-not — PASS

Неверно, что пётр позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4818 → 4819. Внешняя связь: Отрицание
- Строки 4820 → 4821. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4822 → 4823. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4824 → 4825. Проверка разбиения: Proposed split — part 1: «пётр позвонил Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4826 → 4827. Внешняя связь: Одна предикация / именное описание
- Строки 4828 → 4829. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-1-possible — PASS

Возможно, пётр позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4834 → 4835. Внешняя связь: Возможность
- Строки 4836 → 4837. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4838 → 4839. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4840 → 4841. Проверка разбиения: Proposed split — part 1: «пётр позвонил Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4842 → 4843. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4844 → 4845. Внешняя связь: Одна предикация / именное описание
- Строки 4846 → 4847. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-1-quoted — FAIL

Мария сказала: «Пётр позвонил Марии».

Результат шага обрезан в выгрузке.

- Строки 4852 → 4853. Внешняя связь: Пропозициональное содержание
- Строки 4854 → 4855. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 4856 → 4857. Вложенное содержание: конец: Закончить после «Марии» @35; выбранные слова «Пётр позвонил Марии»
- Строки 4858 → 4859. Родительская часть: начало: Начать с «Мария» @0
- Строки 4860 → 4861. Родительская часть: конец: Закончить после «.» @37; выбранные слова «Мария сказала : « » .»
- Строки 4862 → 4863. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Пётр позвонил Марии»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 4864 → 4865. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4866 → 4867. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4868 → 4869. Внешняя связь: Одна предикация / именное описание
- Строки 4870 → 4871. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4872 → 4873. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-11-1-before_point — PASS

В 09:00 пётр позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4878 → 4879. Внешняя связь: Одна предикация / именное описание
- Строки 4880 → 4881. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-1-yesterday — PASS

Вчера пётр позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4886 → 4887. Внешняя связь: Одна предикация / именное описание
- Строки 4888 → 4889. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-1-question — PASS

Верно ли, что пётр позвонил Марии?

Результат шага обрезан в выгрузке.

- Строки 4894 → 4895. Внешняя связь: Вопрос
- Строки 4896 → 4897. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4898 → 4899. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 4900 → 4901. Проверка разбиения: Proposed split — part 1: «пётр позвонил Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 4902 → 4903. Внешняя связь: Одна предикация / именное описание
- Строки 4904 → 4905. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-11-2-bare — PASS

Сергей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4910 → 4911. Внешняя связь: Одна предикация / именное описание
- Строки 4912 → 4913. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-2-not — PASS

Неверно, что сергей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4918 → 4919. Внешняя связь: Отрицание
- Строки 4920 → 4921. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 4922 → 4923. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 4924 → 4925. Проверка разбиения: Proposed split — part 1: «сергей позвонил Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 4926 → 4927. Внешняя связь: Одна предикация / именное описание
- Строки 4928 → 4929. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-2-possible — PASS

Возможно, сергей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4934 → 4935. Внешняя связь: Возможность
- Строки 4936 → 4937. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 4938 → 4939. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 4940 → 4941. Проверка разбиения: Proposed split — part 1: «сергей позвонил Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 4942 → 4943. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 4944 → 4945. Внешняя связь: Одна предикация / именное описание
- Строки 4946 → 4947. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-2-quoted — FAIL

Мария сказала: «Сергей позвонил Марии».

Результат шага обрезан в выгрузке.

- Строки 4952 → 4953. Внешняя связь: Пропозициональное содержание
- Строки 4954 → 4955. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 4956 → 4957. Вложенное содержание: конец: Закончить после «Марии» @37; выбранные слова «Сергей позвонил Марии»
- Строки 4958 → 4959. Родительская часть: начало: Начать с «Мария» @0
- Строки 4960 → 4961. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 4962 → 4963. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей позвонил Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 4964 → 4965. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 4966 → 4967. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 4968 → 4969. Внешняя связь: Одна предикация / именное описание
- Строки 4970 → 4971. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 4972 → 4973. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-11-2-before_point — PASS

В 09:00 сергей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4978 → 4979. Внешняя связь: Одна предикация / именное описание
- Строки 4980 → 4981. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-2-yesterday — PASS

Вчера сергей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 4986 → 4987. Внешняя связь: Одна предикация / именное описание
- Строки 4988 → 4989. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-2-question — PASS

Верно ли, что сергей позвонил Марии?

Результат шага обрезан в выгрузке.

- Строки 4994 → 4995. Внешняя связь: Вопрос
- Строки 4996 → 4997. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 4998 → 4999. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5000 → 5001. Проверка разбиения: Proposed split — part 1: «сергей позвонил Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5002 → 5003. Внешняя связь: Одна предикация / именное описание
- Строки 5004 → 5005. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-11-3-bare — PASS

Алексей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 5010 → 5011. Внешняя связь: Одна предикация / именное описание
- Строки 5012 → 5013. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-3-not — PASS

Неверно, что алексей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 5018 → 5019. Внешняя связь: Отрицание
- Строки 5020 → 5021. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5022 → 5023. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5024 → 5025. Проверка разбиения: Proposed split — part 1: «алексей позвонил Марии»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5026 → 5027. Внешняя связь: Одна предикация / именное описание
- Строки 5028 → 5029. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-3-possible — PASS

Возможно, алексей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 5034 → 5035. Внешняя связь: Возможность
- Строки 5036 → 5037. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5038 → 5039. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5040 → 5041. Проверка разбиения: Proposed split — part 1: «алексей позвонил Марии»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5042 → 5043. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5044 → 5045. Внешняя связь: Одна предикация / именное описание
- Строки 5046 → 5047. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-3-quoted — FAIL

Мария сказала: «Алексей позвонил Марии».

Результат шага обрезан в выгрузке.

- Строки 5052 → 5053. Внешняя связь: Пропозициональное содержание
- Строки 5054 → 5055. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 5056 → 5057. Вложенное содержание: конец: Закончить после «Марии» @38; выбранные слова «Алексей позвонил Марии»
- Строки 5058 → 5059. Родительская часть: начало: Начать с «Мария» @0
- Строки 5060 → 5061. Родительская часть: конец: Закончить после «»» @39; выбранные слова «Мария сказала : « »»
- Строки 5062 → 5063. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей позвонил Марии»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5064 → 5065. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5066 → 5067. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5068 → 5069. Внешняя связь: Одна предикация / именное описание
- Строки 5070 → 5071. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5072 → 5073. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-11-3-before_point — PASS

В 09:00 алексей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 5078 → 5079. Внешняя связь: Одна предикация / именное описание
- Строки 5080 → 5081. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-3-yesterday — PASS

Вчера алексей позвонил Марии.

Результат шага обрезан в выгрузке.

- Строки 5086 → 5087. Внешняя связь: Одна предикация / именное описание
- Строки 5088 → 5089. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: нет.

### LANG-11-3-question — PASS

Верно ли, что алексей позвонил Марии?

Результат шага обрезан в выгрузке.

- Строки 5094 → 5095. Внешняя связь: Вопрос
- Строки 5096 → 5097. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5098 → 5099. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5100 → 5101. Проверка разбиения: Proposed split — part 1: «алексей позвонил Марии»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5102 → 5103. Внешняя связь: Одна предикация / именное описание
- Строки 5104 → 5105. Именная зависимость: Direct role RECIPIENT of predicate «позвонил» (recipient or addressee of the action); lemma: мария; pos: noun; cases: dative; number: singular; gender: feminine; features: personal name, animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-12-0-bare — PASS

Иван написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5110 → 5111. Внешняя связь: Одна предикация / именное описание
- Строки 5112 → 5113. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-0-not — PASS

Неверно, что иван написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5118 → 5119. Внешняя связь: Отрицание
- Строки 5120 → 5121. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5122 → 5123. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5124 → 5125. Проверка разбиения: Proposed split — part 1: «иван написал письмо»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5126 → 5127. Внешняя связь: Одна предикация / именное описание
- Строки 5128 → 5129. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-0-possible — PASS

Возможно, иван написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5134 → 5135. Внешняя связь: Возможность
- Строки 5136 → 5137. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5138 → 5139. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5140 → 5141. Проверка разбиения: Proposed split — part 1: «иван написал письмо»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5142 → 5143. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5144 → 5145. Внешняя связь: Одна предикация / именное описание
- Строки 5146 → 5147. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-0-quoted — FAIL

Мария сказала: «Иван написал письмо».

Результат шага обрезан в выгрузке.

- Строки 5152 → 5153. Внешняя связь: Пропозициональное содержание
- Строки 5154 → 5155. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 5156 → 5157. Вложенное содержание: конец: Закончить после «письмо» @35; выбранные слова «Иван написал письмо»
- Строки 5158 → 5159. Родительская часть: начало: Начать с «Мария» @0
- Строки 5160 → 5161. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 5162 → 5163. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван написал письмо»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5164 → 5165. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5166 → 5167. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5168 → 5169. Внешняя связь: Одна предикация / именное описание
- Строки 5170 → 5171. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5172 → 5173. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-12-0-before_point — PASS

В 09:00 иван написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5178 → 5179. Внешняя связь: Одна предикация / именное описание
- Строки 5180 → 5181. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-0-yesterday — PASS

Вчера иван написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5186 → 5187. Внешняя связь: Одна предикация / именное описание
- Строки 5188 → 5189. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-0-question — FAIL

Верно ли, что иван написал письмо?

Результат шага обрезан в выгрузке.

- Строки 5194 → 5195. Внешняя связь: Вопрос
- Строки 5196 → 5197. Вводящее выражение: начало: Начать с «что» @10
- Строки 5198 → 5199. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «что»
- Строки 5200 → 5201. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 5202 → 5203. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/generation/gold_patterns`.

### LANG-12-1-bare — PASS

Пётр написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5208 → 5209. Внешняя связь: Одна предикация / именное описание
- Строки 5210 → 5211. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-1-not — PASS

Неверно, что пётр написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5216 → 5217. Внешняя связь: Отрицание
- Строки 5218 → 5219. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5220 → 5221. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5222 → 5223. Проверка разбиения: Proposed split — part 1: «пётр написал письмо»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5224 → 5225. Внешняя связь: Одна предикация / именное описание
- Строки 5226 → 5227. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-1-possible — PASS

Возможно, пётр написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5232 → 5233. Внешняя связь: Возможность
- Строки 5234 → 5235. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5236 → 5237. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5238 → 5239. Проверка разбиения: Proposed split — part 1: «пётр написал письмо»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5240 → 5241. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5242 → 5243. Внешняя связь: Одна предикация / именное описание
- Строки 5244 → 5245. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-1-quoted — FAIL

Мария сказала: «Пётр написал письмо».

Результат шага обрезан в выгрузке.

- Строки 5250 → 5251. Внешняя связь: Пропозициональное содержание
- Строки 5252 → 5253. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 5254 → 5255. Вложенное содержание: конец: Закончить после «письмо» @35; выбранные слова «Пётр написал письмо»
- Строки 5256 → 5257. Родительская часть: начало: Начать с «Мария» @0
- Строки 5258 → 5259. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 5260 → 5261. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр написал письмо»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5262 → 5263. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5264 → 5265. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5266 → 5267. Внешняя связь: Одна предикация / именное описание
- Строки 5268 → 5269. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5270 → 5271. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-12-1-before_point — PASS

В 09:00 пётр написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5276 → 5277. Внешняя связь: Одна предикация / именное описание
- Строки 5278 → 5279. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-1-yesterday — PASS

Вчера пётр написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5284 → 5285. Внешняя связь: Одна предикация / именное описание
- Строки 5286 → 5287. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-1-question — PASS

Верно ли, что пётр написал письмо?

Результат шага обрезан в выгрузке.

- Строки 5292 → 5293. Внешняя связь: Вопрос
- Строки 5294 → 5295. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5296 → 5297. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5298 → 5299. Проверка разбиения: Proposed split — part 1: «пётр написал письмо»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5300 → 5301. Внешняя связь: Одна предикация / именное описание
- Строки 5302 → 5303. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-12-2-bare — PASS

Сергей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5308 → 5309. Внешняя связь: Одна предикация / именное описание
- Строки 5310 → 5311. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-2-not — PASS

Неверно, что сергей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5316 → 5317. Внешняя связь: Отрицание
- Строки 5318 → 5319. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5320 → 5321. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5322 → 5323. Проверка разбиения: Proposed split — part 1: «сергей написал письмо»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5324 → 5325. Внешняя связь: Одна предикация / именное описание
- Строки 5326 → 5327. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-2-possible — PASS

Возможно, сергей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5332 → 5333. Внешняя связь: Возможность
- Строки 5334 → 5335. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5336 → 5337. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5338 → 5339. Проверка разбиения: Proposed split — part 1: «сергей написал письмо»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5340 → 5341. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5342 → 5343. Внешняя связь: Одна предикация / именное описание
- Строки 5344 → 5345. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-2-quoted — FAIL

Мария сказала: «Сергей написал письмо».

Результат шага обрезан в выгрузке.

- Строки 5350 → 5351. Внешняя связь: Пропозициональное содержание
- Строки 5352 → 5353. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 5354 → 5355. Вложенное содержание: конец: Закончить после «письмо» @37; выбранные слова «Сергей написал письмо»
- Строки 5356 → 5357. Родительская часть: начало: Начать с «Мария» @0
- Строки 5358 → 5359. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 5360 → 5361. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей написал письмо»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5362 → 5363. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5364 → 5365. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5366 → 5367. Внешняя связь: Одна предикация / именное описание
- Строки 5368 → 5369. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5370 → 5371. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-12-2-before_point — PASS

В 09:00 сергей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5376 → 5377. Внешняя связь: Одна предикация / именное описание
- Строки 5378 → 5379. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-2-yesterday — PASS

Вчера сергей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5384 → 5385. Внешняя связь: Одна предикация / именное описание
- Строки 5386 → 5387. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-2-question — PASS

Верно ли, что сергей написал письмо?

Результат шага обрезан в выгрузке.

- Строки 5392 → 5393. Внешняя связь: Вопрос
- Строки 5394 → 5395. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5396 → 5397. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5398 → 5399. Проверка разбиения: Proposed split — part 1: «сергей написал письмо»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5400 → 5401. Внешняя связь: Одна предикация / именное описание
- Строки 5402 → 5403. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-12-3-bare — PASS

Алексей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5408 → 5409. Внешняя связь: Одна предикация / именное описание
- Строки 5410 → 5411. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-3-not — PASS

Неверно, что алексей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5416 → 5417. Внешняя связь: Отрицание
- Строки 5418 → 5419. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5420 → 5421. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5422 → 5423. Проверка разбиения: Proposed split — part 1: «алексей написал письмо»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5424 → 5425. Внешняя связь: Одна предикация / именное описание
- Строки 5426 → 5427. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-3-possible — PASS

Возможно, алексей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5432 → 5433. Внешняя связь: Возможность
- Строки 5434 → 5435. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5436 → 5437. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5438 → 5439. Проверка разбиения: Proposed split — part 1: «алексей написал письмо»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5440 → 5441. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5442 → 5443. Внешняя связь: Одна предикация / именное описание
- Строки 5444 → 5445. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-3-quoted — FAIL

Мария сказала: «Алексей написал письмо».

Результат шага обрезан в выгрузке.

- Строки 5450 → 5451. Внешняя связь: Пропозициональное содержание
- Строки 5452 → 5453. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 5454 → 5455. Вложенное содержание: конец: Закончить после «письмо» @38; выбранные слова «Алексей написал письмо»
- Строки 5456 → 5457. Родительская часть: начало: Начать с «Мария» @0
- Строки 5458 → 5459. Родительская часть: конец: Закончить после «»» @39; выбранные слова «Мария сказала : « »»
- Строки 5460 → 5461. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей написал письмо»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5462 → 5463. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5464 → 5465. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5466 → 5467. Внешняя связь: Одна предикация / именное описание
- Строки 5468 → 5469. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5470 → 5471. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-12-3-before_point — PASS

В 09:00 алексей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5476 → 5477. Внешняя связь: Одна предикация / именное описание
- Строки 5478 → 5479. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-3-yesterday — PASS

Вчера алексей написал письмо.

Результат шага обрезан в выгрузке.

- Строки 5484 → 5485. Внешняя связь: Одна предикация / именное описание
- Строки 5486 → 5487. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: нет.

### LANG-12-3-question — PASS

Верно ли, что алексей написал письмо?

Результат шага обрезан в выгрузке.

- Строки 5492 → 5493. Внешняя связь: Вопрос
- Строки 5494 → 5495. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5496 → 5497. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5498 → 5499. Проверка разбиения: Proposed split — part 1: «алексей написал письмо»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5500 → 5501. Внешняя связь: Одна предикация / именное описание
- Строки 5502 → 5503. Именная зависимость: Direct role OBJECT of predicate «написал» (direct object or content of the predicate); lemma: письмо; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-13-0-bare — PASS

Иван встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5508 → 5509. Внешняя связь: Одна предикация / именное описание
- Строки 5510 → 5511. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-0-not — PASS

Неверно, что иван встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5516 → 5517. Внешняя связь: Отрицание
- Строки 5518 → 5519. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5520 → 5521. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5522 → 5523. Проверка разбиения: Proposed split — part 1: «иван встретил курьера»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5524 → 5525. Внешняя связь: Одна предикация / именное описание
- Строки 5526 → 5527. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-0-possible — PASS

Возможно, иван встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5532 → 5533. Внешняя связь: Возможность
- Строки 5534 → 5535. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5536 → 5537. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5538 → 5539. Проверка разбиения: Proposed split — part 1: «иван встретил курьера»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5540 → 5541. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5542 → 5543. Внешняя связь: Одна предикация / именное описание
- Строки 5544 → 5545. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-0-quoted — FAIL

Мария сказала: «Иван встретил курьера».

Результат шага обрезан в выгрузке.

- Строки 5550 → 5551. Внешняя связь: Пропозициональное содержание
- Строки 5552 → 5553. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 5554 → 5555. Вложенное содержание: конец: Закончить после «курьера» @37; выбранные слова «Иван встретил курьера»
- Строки 5556 → 5557. Родительская часть: начало: Начать с «Мария» @0
- Строки 5558 → 5559. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 5560 → 5561. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван встретил курьера»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5562 → 5563. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5564 → 5565. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5566 → 5567. Внешняя связь: Одна предикация / именное описание
- Строки 5568 → 5569. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5570 → 5571. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-13-0-before_point — PASS

В 09:00 иван встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5576 → 5577. Внешняя связь: Одна предикация / именное описание
- Строки 5578 → 5579. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-0-yesterday — PASS

Вчера иван встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5584 → 5585. Внешняя связь: Одна предикация / именное описание
- Строки 5586 → 5587. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-0-question — PASS

Верно ли, что иван встретил курьера?

Результат шага обрезан в выгрузке.

- Строки 5592 → 5593. Внешняя связь: Вопрос
- Строки 5594 → 5595. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5596 → 5597. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5598 → 5599. Проверка разбиения: Proposed split — part 1: «иван встретил курьера»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5600 → 5601. Внешняя связь: Одна предикация / именное описание
- Строки 5602 → 5603. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-13-1-bare — PASS

Пётр встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5608 → 5609. Внешняя связь: Одна предикация / именное описание
- Строки 5610 → 5611. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-1-not — PASS

Неверно, что пётр встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5616 → 5617. Внешняя связь: Отрицание
- Строки 5618 → 5619. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5620 → 5621. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5622 → 5623. Проверка разбиения: Proposed split — part 1: «пётр встретил курьера»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5624 → 5625. Внешняя связь: Одна предикация / именное описание
- Строки 5626 → 5627. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-1-possible — PASS

Возможно, пётр встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5632 → 5633. Внешняя связь: Возможность
- Строки 5634 → 5635. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5636 → 5637. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5638 → 5639. Проверка разбиения: Proposed split — part 1: «пётр встретил курьера»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5640 → 5641. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5642 → 5643. Внешняя связь: Одна предикация / именное описание
- Строки 5644 → 5645. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-1-quoted — FAIL

Мария сказала: «Пётр встретил курьера».

Результат шага обрезан в выгрузке.

- Строки 5650 → 5651. Внешняя связь: Пропозициональное содержание
- Строки 5652 → 5653. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 5654 → 5655. Вложенное содержание: конец: Закончить после «курьера» @37; выбранные слова «Пётр встретил курьера»
- Строки 5656 → 5657. Родительская часть: начало: Начать с «Мария» @0
- Строки 5658 → 5659. Родительская часть: конец: Закончить после «.» @39; выбранные слова «Мария сказала : « » .»
- Строки 5660 → 5661. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Пётр встретил курьера»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 5662 → 5663. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5664 → 5665. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5666 → 5667. Внешняя связь: Одна предикация / именное описание
- Строки 5668 → 5669. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5670 → 5671. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-13-1-before_point — PASS

В 09:00 пётр встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5676 → 5677. Внешняя связь: Одна предикация / именное описание
- Строки 5678 → 5679. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-1-yesterday — PASS

Вчера пётр встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5684 → 5685. Внешняя связь: Одна предикация / именное описание
- Строки 5686 → 5687. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-1-question — PASS

Верно ли, что пётр встретил курьера?

Результат шага обрезан в выгрузке.

- Строки 5692 → 5693. Внешняя связь: Вопрос
- Строки 5694 → 5695. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5696 → 5697. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5698 → 5699. Проверка разбиения: Proposed split — part 1: «пётр встретил курьера»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5700 → 5701. Внешняя связь: Одна предикация / именное описание
- Строки 5702 → 5703. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-13-2-bare — PASS

Сергей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5708 → 5709. Внешняя связь: Одна предикация / именное описание
- Строки 5710 → 5711. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-2-not — PASS

Неверно, что сергей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5716 → 5717. Внешняя связь: Отрицание
- Строки 5718 → 5719. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5720 → 5721. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5722 → 5723. Проверка разбиения: Proposed split — part 1: «сергей встретил курьера»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5724 → 5725. Внешняя связь: Одна предикация / именное описание
- Строки 5726 → 5727. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-2-possible — PASS

Возможно, сергей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5732 → 5733. Внешняя связь: Возможность
- Строки 5734 → 5735. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5736 → 5737. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5738 → 5739. Проверка разбиения: Proposed split — part 1: «сергей встретил курьера»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5740 → 5741. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5742 → 5743. Внешняя связь: Одна предикация / именное описание
- Строки 5744 → 5745. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-2-quoted — FAIL

Мария сказала: «Сергей встретил курьера».

Результат шага обрезан в выгрузке.

- Строки 5750 → 5751. Внешняя связь: Пропозициональное содержание
- Строки 5752 → 5753. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 5754 → 5755. Вложенное содержание: конец: Закончить после «курьера» @39; выбранные слова «Сергей встретил курьера»
- Строки 5756 → 5757. Родительская часть: начало: Начать с «Мария» @0
- Строки 5758 → 5759. Родительская часть: конец: Закончить после «»» @40; выбранные слова «Мария сказала : « »»
- Строки 5760 → 5761. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей встретил курьера»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5762 → 5763. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5764 → 5765. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5766 → 5767. Внешняя связь: Одна предикация / именное описание
- Строки 5768 → 5769. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5770 → 5771. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-13-2-before_point — PASS

В 09:00 сергей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5776 → 5777. Внешняя связь: Одна предикация / именное описание
- Строки 5778 → 5779. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-2-yesterday — PASS

Вчера сергей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5784 → 5785. Внешняя связь: Одна предикация / именное описание
- Строки 5786 → 5787. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-2-question — PASS

Верно ли, что сергей встретил курьера?

Результат шага обрезан в выгрузке.

- Строки 5792 → 5793. Внешняя связь: Вопрос
- Строки 5794 → 5795. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5796 → 5797. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5798 → 5799. Проверка разбиения: Proposed split — part 1: «сергей встретил курьера»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5800 → 5801. Внешняя связь: Одна предикация / именное описание
- Строки 5802 → 5803. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-13-3-bare — PASS

Алексей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5808 → 5809. Внешняя связь: Одна предикация / именное описание
- Строки 5810 → 5811. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-3-not — PASS

Неверно, что алексей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5816 → 5817. Внешняя связь: Отрицание
- Строки 5818 → 5819. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5820 → 5821. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5822 → 5823. Проверка разбиения: Proposed split — part 1: «алексей встретил курьера»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5824 → 5825. Внешняя связь: Одна предикация / именное описание
- Строки 5826 → 5827. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-3-possible — PASS

Возможно, алексей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5832 → 5833. Внешняя связь: Возможность
- Строки 5834 → 5835. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5836 → 5837. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5838 → 5839. Проверка разбиения: Proposed split — part 1: «алексей встретил курьера»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5840 → 5841. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5842 → 5843. Внешняя связь: Одна предикация / именное описание
- Строки 5844 → 5845. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-3-quoted — FAIL

Мария сказала: «Алексей встретил курьера».

Результат шага обрезан в выгрузке.

- Строки 5850 → 5851. Внешняя связь: Пропозициональное содержание
- Строки 5852 → 5853. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 5854 → 5855. Вложенное содержание: конец: Закончить после «курьера» @40; выбранные слова «Алексей встретил курьера»
- Строки 5856 → 5857. Родительская часть: начало: Начать с «Мария» @0
- Строки 5858 → 5859. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 5860 → 5861. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей встретил курьера»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5862 → 5863. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5864 → 5865. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5866 → 5867. Внешняя связь: Одна предикация / именное описание
- Строки 5868 → 5869. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5870 → 5871. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-13-3-before_point — PASS

В 09:00 алексей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5876 → 5877. Внешняя связь: Одна предикация / именное описание
- Строки 5878 → 5879. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-3-yesterday — PASS

Вчера алексей встретил курьера.

Результат шага обрезан в выгрузке.

- Строки 5884 → 5885. Внешняя связь: Одна предикация / именное описание
- Строки 5886 → 5887. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: нет.

### LANG-13-3-question — PASS

Верно ли, что алексей встретил курьера?

Результат шага обрезан в выгрузке.

- Строки 5892 → 5893. Внешняя связь: Вопрос
- Строки 5894 → 5895. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 5896 → 5897. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 5898 → 5899. Проверка разбиения: Proposed split — part 1: «алексей встретил курьера»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 5900 → 5901. Внешняя связь: Одна предикация / именное описание
- Строки 5902 → 5903. Именная зависимость: Direct role OBJECT of predicate «встретил» (direct object or content of the predicate); lemma: курьер; pos: noun; cases: accusative; number: singular; gender: masculine; features: animate

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-14-0-bare — PASS

Иван приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 5908 → 5909. Внешняя связь: Одна предикация / именное описание
- Строки 5910 → 5911. Состав и чтение конструкции: приехать [VERB]; SUBJECT=Иван, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-0-not — PASS

Неверно, что иван приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 5916 → 5917. Внешняя связь: Отрицание
- Строки 5918 → 5919. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 5920 → 5921. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 5922 → 5923. Проверка разбиения: Proposed split — part 1: «иван приехал в Москву»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 5924 → 5925. Внешняя связь: Одна предикация / именное описание
- Строки 5926 → 5927. Состав и чтение конструкции: приехать [VERB]; SUBJECT=иван, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-0-possible — PASS

Возможно, иван приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 5932 → 5933. Внешняя связь: Возможность
- Строки 5934 → 5935. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 5936 → 5937. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 5938 → 5939. Проверка разбиения: Proposed split — part 1: «иван приехал в Москву»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 5940 → 5941. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 5942 → 5943. Внешняя связь: Одна предикация / именное описание
- Строки 5944 → 5945. Состав и чтение конструкции: приехать [VERB]; SUBJECT=иван, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-0-quoted — FAIL

Мария сказала: «Иван приехал в Москву».

Результат шага обрезан в выгрузке.

- Строки 5950 → 5951. Внешняя связь: Пропозициональное содержание
- Строки 5952 → 5953. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 5954 → 5955. Вложенное содержание: конец: Закончить после «Москву» @37; выбранные слова «Иван приехал в Москву»
- Строки 5956 → 5957. Родительская часть: начало: Начать с «Мария» @0
- Строки 5958 → 5959. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 5960 → 5961. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван приехал в Москву»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 5962 → 5963. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5964 → 5965. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5966 → 5967. Внешняя связь: Пропозициональное содержание
- Строки 5968 → 5969. Вложенное содержание: начало: Начать с ««» @15
- Строки 5970 → 5971. Вложенное содержание: конец: Закончить после «»» @38; выбранные слова «« »»
- Строки 5972 → 5973. Родительская часть: начало: Начать с «Мария» @0
- Строки 5974 → 5975. Родительская часть: конец: Закончить после «сказала» @13; выбранные слова «Мария сказала»
- Строки 5976 → 5977. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала»; content filling that slot: «« »»; outer relation occurrences: none; punctuation outside parts: «:»
- Строки 5978 → 5979. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 5980 → 5981. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 5982 → 5983. Внешняя связь: Одна предикация / именное описание
- Строки 5984 → 5985. Внешняя связь: Одна предикация / именное описание
- Строки 5986 → 5987. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5988 → 5989. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 5990 → 5991. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-14-0-before_point — PASS

В 09:00 иван приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 5996 → 5997. Внешняя связь: Одна предикация / именное описание
- Строки 5998 → 5999. Состав и чтение конструкции: приехать [VERB]; SUBJECT=иван, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-0-yesterday — PASS

Вчера иван приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6004 → 6005. Внешняя связь: Одна предикация / именное описание
- Строки 6006 → 6007. Состав и чтение конструкции: приехать [VERB]; SUBJECT=иван, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-0-question — PASS

Верно ли, что иван приехал в Москву?

Результат шага обрезан в выгрузке.

- Строки 6012 → 6013. Внешняя связь: Вопрос
- Строки 6014 → 6015. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6016 → 6017. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6018 → 6019. Проверка разбиения: Proposed split — part 1: «иван приехал в Москву»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6020 → 6021. Внешняя связь: Одна предикация / именное описание
- Строки 6022 → 6023. Состав и чтение конструкции: приехать [VERB]; SUBJECT=иван, LOCATION=Москву

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-14-1-bare — PASS

Пётр приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6028 → 6029. Внешняя связь: Одна предикация / именное описание
- Строки 6030 → 6031. Состав и чтение конструкции: приехать [VERB]; SUBJECT=Пётр, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-1-not — PASS

Неверно, что пётр приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6036 → 6037. Внешняя связь: Отрицание
- Строки 6038 → 6039. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6040 → 6041. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6042 → 6043. Проверка разбиения: Proposed split — part 1: «пётр приехал в Москву»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6044 → 6045. Внешняя связь: Одна предикация / именное описание
- Строки 6046 → 6047. Состав и чтение конструкции: приехать [VERB]; SUBJECT=пётр, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-1-possible — PASS

Возможно, пётр приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6052 → 6053. Внешняя связь: Возможность
- Строки 6054 → 6055. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6056 → 6057. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6058 → 6059. Проверка разбиения: Proposed split — part 1: «пётр приехал в Москву»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6060 → 6061. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6062 → 6063. Внешняя связь: Одна предикация / именное описание
- Строки 6064 → 6065. Состав и чтение конструкции: приехать [VERB]; SUBJECT=пётр, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-1-quoted — FAIL

Мария сказала: «Пётр приехал в Москву».

Результат шага обрезан в выгрузке.

- Строки 6070 → 6071. Внешняя связь: Пропозициональное содержание
- Строки 6072 → 6073. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 6074 → 6075. Вложенное содержание: конец: Закончить после «Москву» @37; выбранные слова «Пётр приехал в Москву»
- Строки 6076 → 6077. Родительская часть: начало: Начать с «Мария» @0
- Строки 6078 → 6079. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 6080 → 6081. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр приехал в Москву»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6082 → 6083. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6084 → 6085. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6086 → 6087. Внешняя связь: Одна предикация / именное описание
- Строки 6088 → 6089. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6090 → 6091. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-14-1-before_point — PASS

В 09:00 пётр приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6096 → 6097. Внешняя связь: Одна предикация / именное описание
- Строки 6098 → 6099. Состав и чтение конструкции: приехать [VERB]; SUBJECT=пётр, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-1-yesterday — PASS

Вчера пётр приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6104 → 6105. Внешняя связь: Одна предикация / именное описание
- Строки 6106 → 6107. Состав и чтение конструкции: приехать [VERB]; SUBJECT=пётр, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-1-question — PASS

Верно ли, что пётр приехал в Москву?

Результат шага обрезан в выгрузке.

- Строки 6112 → 6113. Внешняя связь: Вопрос
- Строки 6114 → 6115. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6116 → 6117. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6118 → 6119. Проверка разбиения: Proposed split — part 1: «пётр приехал в Москву»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6120 → 6121. Внешняя связь: Одна предикация / именное описание
- Строки 6122 → 6123. Состав и чтение конструкции: приехать [VERB]; SUBJECT=пётр, LOCATION=Москву

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-14-2-bare — PASS

Сергей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6128 → 6129. Внешняя связь: Одна предикация / именное описание
- Строки 6130 → 6131. Состав и чтение конструкции: приехать [VERB]; SUBJECT=Сергей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-2-not — PASS

Неверно, что сергей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6136 → 6137. Внешняя связь: Отрицание
- Строки 6138 → 6139. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6140 → 6141. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6142 → 6143. Проверка разбиения: Proposed split — part 1: «сергей приехал в Москву»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6144 → 6145. Внешняя связь: Одна предикация / именное описание
- Строки 6146 → 6147. Состав и чтение конструкции: приехать [VERB]; SUBJECT=сергей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-2-possible — PASS

Возможно, сергей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6152 → 6153. Внешняя связь: Возможность
- Строки 6154 → 6155. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6156 → 6157. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6158 → 6159. Проверка разбиения: Proposed split — part 1: «сергей приехал в Москву»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6160 → 6161. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6162 → 6163. Внешняя связь: Одна предикация / именное описание
- Строки 6164 → 6165. Состав и чтение конструкции: приехать [VERB]; SUBJECT=сергей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-2-quoted — FAIL

Мария сказала: «Сергей приехал в Москву».

Результат шага обрезан в выгрузке.

- Строки 6170 → 6171. Внешняя связь: Пропозициональное содержание
- Строки 6172 → 6173. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 6174 → 6175. Вложенное содержание: конец: Закончить после «Москву» @39; выбранные слова «Сергей приехал в Москву»
- Строки 6176 → 6177. Родительская часть: начало: Начать с «Мария» @0
- Строки 6178 → 6179. Родительская часть: конец: Закончить после «»» @40; выбранные слова «Мария сказала : « »»
- Строки 6180 → 6181. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей приехал в Москву»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6182 → 6183. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6184 → 6185. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6186 → 6187. Внешняя связь: Одна предикация / именное описание
- Строки 6188 → 6189. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6190 → 6191. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-14-2-before_point — PASS

В 09:00 сергей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6196 → 6197. Внешняя связь: Одна предикация / именное описание
- Строки 6198 → 6199. Состав и чтение конструкции: приехать [VERB]; SUBJECT=сергей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-2-yesterday — PASS

Вчера сергей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6204 → 6205. Внешняя связь: Одна предикация / именное описание
- Строки 6206 → 6207. Состав и чтение конструкции: приехать [VERB]; SUBJECT=сергей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-2-question — PASS

Верно ли, что сергей приехал в Москву?

Результат шага обрезан в выгрузке.

- Строки 6212 → 6213. Внешняя связь: Вопрос
- Строки 6214 → 6215. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6216 → 6217. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6218 → 6219. Проверка разбиения: Proposed split — part 1: «сергей приехал в Москву»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6220 → 6221. Внешняя связь: Одна предикация / именное описание
- Строки 6222 → 6223. Состав и чтение конструкции: приехать [VERB]; SUBJECT=сергей, LOCATION=Москву

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-14-3-bare — PASS

Алексей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6228 → 6229. Внешняя связь: Одна предикация / именное описание
- Строки 6230 → 6231. Состав и чтение конструкции: приехать [VERB]; SUBJECT=Алексей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-3-not — PASS

Неверно, что алексей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6236 → 6237. Внешняя связь: Отрицание
- Строки 6238 → 6239. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6240 → 6241. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6242 → 6243. Проверка разбиения: Proposed split — part 1: «алексей приехал в Москву»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6244 → 6245. Внешняя связь: Одна предикация / именное описание
- Строки 6246 → 6247. Состав и чтение конструкции: приехать [VERB]; SUBJECT=алексей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-3-possible — PASS

Возможно, алексей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6252 → 6253. Внешняя связь: Возможность
- Строки 6254 → 6255. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6256 → 6257. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6258 → 6259. Проверка разбиения: Proposed split — part 1: «алексей приехал в Москву»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6260 → 6261. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6262 → 6263. Внешняя связь: Одна предикация / именное описание
- Строки 6264 → 6265. Состав и чтение конструкции: приехать [VERB]; SUBJECT=алексей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-3-quoted — FAIL

Мария сказала: «Алексей приехал в Москву».

Результат шага обрезан в выгрузке.

- Строки 6270 → 6271. Внешняя связь: Пропозициональное содержание
- Строки 6272 → 6273. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 6274 → 6275. Вложенное содержание: конец: Закончить после «Москву» @40; выбранные слова «Алексей приехал в Москву»
- Строки 6276 → 6277. Родительская часть: начало: Начать с «Мария» @0
- Строки 6278 → 6279. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 6280 → 6281. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей приехал в Москву»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6282 → 6283. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6284 → 6285. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6286 → 6287. Внешняя связь: Одна предикация / именное описание
- Строки 6288 → 6289. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6290 → 6291. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-14-3-before_point — PASS

В 09:00 алексей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6296 → 6297. Внешняя связь: Одна предикация / именное описание
- Строки 6298 → 6299. Состав и чтение конструкции: приехать [VERB]; SUBJECT=алексей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-3-yesterday — PASS

Вчера алексей приехал в Москву.

Результат шага обрезан в выгрузке.

- Строки 6304 → 6305. Внешняя связь: Одна предикация / именное описание
- Строки 6306 → 6307. Состав и чтение конструкции: приехать [VERB]; SUBJECT=алексей, LOCATION=Москву

Первая записанная диагностика: нет.

### LANG-14-3-question — PASS

Верно ли, что алексей приехал в Москву?

Результат шага обрезан в выгрузке.

- Строки 6312 → 6313. Внешняя связь: Вопрос
- Строки 6314 → 6315. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6316 → 6317. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6318 → 6319. Проверка разбиения: Proposed split — part 1: «алексей приехал в Москву»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6320 → 6321. Внешняя связь: Одна предикация / именное описание
- Строки 6322 → 6323. Состав и чтение конструкции: приехать [VERB]; SUBJECT=алексей, LOCATION=Москву

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-15-0-bare — PASS

Иван уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6328 → 6329. Внешняя связь: Одна предикация / именное описание
- Строки 6330 → 6331. Состав и чтение конструкции: уехать [VERB]; SUBJECT=Иван, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-0-not — PASS

Неверно, что иван уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6336 → 6337. Внешняя связь: Отрицание
- Строки 6338 → 6339. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6340 → 6341. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6342 → 6343. Проверка разбиения: Proposed split — part 1: «иван уехал из Москвы»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6344 → 6345. Внешняя связь: Одна предикация / именное описание
- Строки 6346 → 6347. Состав и чтение конструкции: уехать [VERB]; SUBJECT=иван, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-0-possible — PASS

Возможно, иван уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6352 → 6353. Внешняя связь: Возможность
- Строки 6354 → 6355. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6356 → 6357. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6358 → 6359. Проверка разбиения: Proposed split — part 1: «иван уехал из Москвы»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6360 → 6361. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6362 → 6363. Внешняя связь: Одна предикация / именное описание
- Строки 6364 → 6365. Состав и чтение конструкции: уехать [VERB]; SUBJECT=иван, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-0-quoted — FAIL

Мария сказала: «Иван уехал из Москвы».

Результат шага обрезан в выгрузке.

- Строки 6370 → 6371. Внешняя связь: Пропозициональное содержание
- Строки 6372 → 6373. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 6374 → 6375. Вложенное содержание: конец: Закончить после «Москвы» @36; выбранные слова «Иван уехал из Москвы»
- Строки 6376 → 6377. Родительская часть: начало: Начать с «Мария» @0
- Строки 6378 → 6379. Родительская часть: конец: Закончить после «»» @37; выбранные слова «Мария сказала : « »»
- Строки 6380 → 6381. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван уехал из Москвы»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6382 → 6383. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6384 → 6385. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6386 → 6387. Внешняя связь: Одна предикация / именное описание
- Строки 6388 → 6389. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6390 → 6391. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-15-0-before_point — PASS

В 09:00 иван уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6396 → 6397. Внешняя связь: Одна предикация / именное описание
- Строки 6398 → 6399. Состав и чтение конструкции: уехать [VERB]; SUBJECT=иван, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-0-yesterday — PASS

Вчера иван уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6404 → 6405. Внешняя связь: Одна предикация / именное описание
- Строки 6406 → 6407. Состав и чтение конструкции: уехать [VERB]; SUBJECT=иван, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-0-question — PASS

Верно ли, что иван уехал из Москвы?

Результат шага обрезан в выгрузке.

- Строки 6412 → 6413. Внешняя связь: Вопрос
- Строки 6414 → 6415. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6416 → 6417. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6418 → 6419. Проверка разбиения: Proposed split — part 1: «иван уехал из Москвы»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6420 → 6421. Внешняя связь: Одна предикация / именное описание
- Строки 6422 → 6423. Состав и чтение конструкции: уехать [VERB]; SUBJECT=иван, SOURCE=Москвы

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-15-1-bare — PASS

Пётр уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6428 → 6429. Внешняя связь: Одна предикация / именное описание
- Строки 6430 → 6431. Состав и чтение конструкции: уехать [VERB]; SUBJECT=Пётр, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-1-not — PASS

Неверно, что пётр уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6436 → 6437. Внешняя связь: Отрицание
- Строки 6438 → 6439. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6440 → 6441. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6442 → 6443. Проверка разбиения: Proposed split — part 1: «пётр уехал из Москвы»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6444 → 6445. Внешняя связь: Одна предикация / именное описание
- Строки 6446 → 6447. Состав и чтение конструкции: уехать [VERB]; SUBJECT=пётр, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-1-possible — PASS

Возможно, пётр уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6452 → 6453. Внешняя связь: Возможность
- Строки 6454 → 6455. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6456 → 6457. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6458 → 6459. Проверка разбиения: Proposed split — part 1: «пётр уехал из Москвы»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6460 → 6461. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6462 → 6463. Внешняя связь: Одна предикация / именное описание
- Строки 6464 → 6465. Состав и чтение конструкции: уехать [VERB]; SUBJECT=пётр, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-1-quoted — FAIL

Мария сказала: «Пётр уехал из Москвы».

Результат шага обрезан в выгрузке.

- Строки 6470 → 6471. Внешняя связь: Пропозициональное содержание
- Строки 6472 → 6473. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 6474 → 6475. Вложенное содержание: конец: Закончить после «Москвы» @36; выбранные слова «Пётр уехал из Москвы»
- Строки 6476 → 6477. Родительская часть: начало: Начать с «Мария» @0
- Строки 6478 → 6479. Родительская часть: конец: Закончить после «»» @37; выбранные слова «Мария сказала : « »»
- Строки 6480 → 6481. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр уехал из Москвы»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6482 → 6483. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6484 → 6485. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6486 → 6487. Внешняя связь: Одна предикация / именное описание
- Строки 6488 → 6489. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6490 → 6491. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-15-1-before_point — PASS

В 09:00 пётр уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6496 → 6497. Внешняя связь: Одна предикация / именное описание
- Строки 6498 → 6499. Состав и чтение конструкции: уехать [VERB]; SUBJECT=пётр, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-1-yesterday — PASS

Вчера пётр уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6504 → 6505. Внешняя связь: Одна предикация / именное описание
- Строки 6506 → 6507. Состав и чтение конструкции: уехать [VERB]; SUBJECT=пётр, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-1-question — PASS

Верно ли, что пётр уехал из Москвы?

Результат шага обрезан в выгрузке.

- Строки 6512 → 6513. Внешняя связь: Вопрос
- Строки 6514 → 6515. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6516 → 6517. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6518 → 6519. Проверка разбиения: Proposed split — part 1: «пётр уехал из Москвы»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6520 → 6521. Внешняя связь: Одна предикация / именное описание
- Строки 6522 → 6523. Состав и чтение конструкции: уехать [VERB]; SUBJECT=пётр, SOURCE=Москвы

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-15-2-bare — PASS

Сергей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6528 → 6529. Внешняя связь: Одна предикация / именное описание
- Строки 6530 → 6531. Состав и чтение конструкции: уехать [VERB]; SUBJECT=Сергей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-2-not — PASS

Неверно, что сергей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6536 → 6537. Внешняя связь: Отрицание
- Строки 6538 → 6539. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6540 → 6541. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6542 → 6543. Проверка разбиения: Proposed split — part 1: «сергей уехал из Москвы»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6544 → 6545. Внешняя связь: Одна предикация / именное описание
- Строки 6546 → 6547. Состав и чтение конструкции: уехать [VERB]; SUBJECT=сергей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-2-possible — PASS

Возможно, сергей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6552 → 6553. Внешняя связь: Возможность
- Строки 6554 → 6555. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6556 → 6557. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6558 → 6559. Проверка разбиения: Proposed split — part 1: «сергей уехал из Москвы»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6560 → 6561. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6562 → 6563. Внешняя связь: Одна предикация / именное описание
- Строки 6564 → 6565. Состав и чтение конструкции: уехать [VERB]; SUBJECT=сергей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-2-quoted — FAIL

Мария сказала: «Сергей уехал из Москвы».

Результат шага обрезан в выгрузке.

- Строки 6570 → 6571. Внешняя связь: Пропозициональное содержание
- Строки 6572 → 6573. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 6574 → 6575. Вложенное содержание: конец: Закончить после «Москвы» @38; выбранные слова «Сергей уехал из Москвы»
- Строки 6576 → 6577. Родительская часть: начало: Начать с «Мария» @0
- Строки 6578 → 6579. Родительская часть: конец: Закончить после «.» @40; выбранные слова «Мария сказала : « » .»
- Строки 6580 → 6581. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Сергей уехал из Москвы»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 6582 → 6583. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6584 → 6585. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6586 → 6587. Внешняя связь: Одна предикация / именное описание
- Строки 6588 → 6589. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6590 → 6591. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-15-2-before_point — PASS

В 09:00 сергей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6596 → 6597. Внешняя связь: Одна предикация / именное описание
- Строки 6598 → 6599. Состав и чтение конструкции: уехать [VERB]; SUBJECT=сергей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-2-yesterday — PASS

Вчера сергей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6604 → 6605. Внешняя связь: Одна предикация / именное описание
- Строки 6606 → 6607. Состав и чтение конструкции: уехать [VERB]; SUBJECT=сергей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-2-question — PASS

Верно ли, что сергей уехал из Москвы?

Результат шага обрезан в выгрузке.

- Строки 6612 → 6613. Внешняя связь: Вопрос
- Строки 6614 → 6615. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6616 → 6617. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6618 → 6619. Проверка разбиения: Proposed split — part 1: «сергей уехал из Москвы»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6620 → 6621. Внешняя связь: Одна предикация / именное описание
- Строки 6622 → 6623. Состав и чтение конструкции: уехать [VERB]; SUBJECT=сергей, SOURCE=Москвы

Первая записанная диагностика: SPEECH_ACT_QUERY.

### LANG-15-3-bare — PASS

Алексей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6628 → 6629. Внешняя связь: Одна предикация / именное описание
- Строки 6630 → 6631. Состав и чтение конструкции: уехать [VERB]; SUBJECT=Алексей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-3-not — PASS

Неверно, что алексей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6636 → 6637. Внешняя связь: Отрицание
- Строки 6638 → 6639. Вводящее выражение: начало: Начать с «Неверно» @0
- Строки 6640 → 6641. Вводящее выражение: конец: Закончить после «что» @12; выбранные слова «Неверно , что»
- Строки 6642 → 6643. Проверка разбиения: Proposed split — part 1: «алексей уехал из Москвы»; outer relation occurrences: «Неверно» @0, «что» @9; punctuation outside parts: «, .»
- Строки 6644 → 6645. Внешняя связь: Одна предикация / именное описание
- Строки 6646 → 6647. Состав и чтение конструкции: уехать [VERB]; SUBJECT=алексей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-3-possible — PASS

Возможно, алексей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6652 → 6653. Внешняя связь: Возможность
- Строки 6654 → 6655. Вводящее выражение: начало: Начать с «Возможно» @0
- Строки 6656 → 6657. Вводящее выражение: конец: Закончить после «,» @9; выбранные слова «Возможно ,»
- Строки 6658 → 6659. Проверка разбиения: Proposed split — part 1: «алексей уехал из Москвы»; outer relation occurrences: «Возможно» @0; punctuation outside parts: «, .»
- Строки 6660 → 6661. Управление модальным содержанием: No agreement governor: the child has independent predication
- Строки 6662 → 6663. Внешняя связь: Одна предикация / именное описание
- Строки 6664 → 6665. Состав и чтение конструкции: уехать [VERB]; SUBJECT=алексей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-3-quoted — FAIL

Мария сказала: «Алексей уехал из Москвы».

Результат шага обрезан в выгрузке.

- Строки 6670 → 6671. Внешняя связь: Пропозициональное содержание
- Строки 6672 → 6673. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 6674 → 6675. Вложенное содержание: конец: Закончить после «Москвы» @39; выбранные слова «Алексей уехал из Москвы»
- Строки 6676 → 6677. Родительская часть: начало: Начать с «Мария» @0
- Строки 6678 → 6679. Родительская часть: конец: Закончить после «»» @40; выбранные слова «Мария сказала : « »»
- Строки 6680 → 6681. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей уехал из Москвы»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6682 → 6683. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6684 → 6685. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6686 → 6687. Внешняя связь: Пропозициональное содержание
- Строки 6688 → 6689. Вложенное содержание: начало: Начать с ««» @15
- Строки 6690 → 6691. Вложенное содержание: конец: Закончить после «»» @40; выбранные слова «« »»
- Строки 6692 → 6693. Родительская часть: начало: Начать с «Мария» @0
- Строки 6694 → 6695. Родительская часть: конец: Закончить после «сказала» @13; выбранные слова «Мария сказала»
- Строки 6696 → 6697. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала»; content filling that slot: «« »»; outer relation occurrences: none; punctuation outside parts: «:»
- Строки 6698 → 6699. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 6700 → 6701. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6702 → 6703. Внешняя связь: Одна предикация / именное описание
- Строки 6704 → 6705. Внешняя связь: Одна предикация / именное описание
- Строки 6706 → 6707. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6708 → 6709. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6710 → 6711. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### LANG-15-3-before_point — PASS

В 09:00 алексей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6716 → 6717. Внешняя связь: Одна предикация / именное описание
- Строки 6718 → 6719. Состав и чтение конструкции: уехать [VERB]; SUBJECT=алексей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-3-yesterday — PASS

Вчера алексей уехал из Москвы.

Результат шага обрезан в выгрузке.

- Строки 6724 → 6725. Внешняя связь: Одна предикация / именное описание
- Строки 6726 → 6727. Состав и чтение конструкции: уехать [VERB]; SUBJECT=алексей, SOURCE=Москвы

Первая записанная диагностика: нет.

### LANG-15-3-question — PASS

Верно ли, что алексей уехал из Москвы?

Результат шага обрезан в выгрузке.

- Строки 6732 → 6733. Внешняя связь: Вопрос
- Строки 6734 → 6735. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6736 → 6737. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6738 → 6739. Проверка разбиения: Proposed split — part 1: «алексей уехал из Москвы»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6740 → 6741. Внешняя связь: Одна предикация / именное описание
- Строки 6742 → 6743. Состав и чтение конструкции: уехать [VERB]; SUBJECT=алексей, SOURCE=Москвы

Первая записанная диагностика: SPEECH_ACT_QUERY.

### NONFINITE-00-base — FAIL

Иван хочет читать книгу.

Результат шага обрезан в выгрузке.

- Строки 6748 → 6749. Внешняя связь: Одна предикация / именное описание
- Строки 6750 → 6751. Состав и чтение конструкции: Infinitive area «читать книгу.»; remaining parent «Иван хочет»
- Строки 6752 → 6753. Внешняя связь: Одна предикация / именное описание
- Строки 6754 → 6755. Состав и чтение конструкции: «читать» fills OBJECT of «хочет» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 6756 → 6757. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### NONFINITE-00-quote — FAIL

Пётр сказал: «Иван хочет читать книгу».

Результат шага обрезан в выгрузке.

- Строки 6762 → 6763. Внешняя связь: Пропозициональное содержание
- Строки 6764 → 6765. Вложенное содержание: начало: Начать с «Иван» @14
- Строки 6766 → 6767. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Иван хочет читать книгу»
- Строки 6768 → 6769. Родительская часть: начало: Начать с «Пётр» @0
- Строки 6770 → 6771. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Пётр сказал : « »»
- Строки 6772 → 6773. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Иван хочет читать книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6774 → 6775. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 6776 → 6777. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6778 → 6779. Внешняя связь: Одна предикация / именное описание
- Строки 6780 → 6781. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6782 → 6783. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-00-nested_quote — FAIL

Иван сказал, что Пётр думает: «Иван хочет читать книгу».

Результат шага обрезан в выгрузке.

- Строки 6788 → 6789. Внешняя связь: Пропозициональное содержание
- Строки 6790 → 6791. Вложенное содержание: начало: Начать с «Иван» @31
- Строки 6792 → 6793. Вложенное содержание: конец: Закончить после «книгу» @54; выбранные слова «Иван хочет читать книгу»
- Строки 6794 → 6795. Родительская часть: начало: Начать с «Иван» @0
- Строки 6796 → 6797. Родительская часть: конец: Закончить после «.» @56; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 6798 → 6799. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Иван хочет читать книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 6800 → 6801. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 6802 → 6803. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6804 → 6805. Внешняя связь: Одна предикация / именное описание
- Строки 6806 → 6807. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6808 → 6809. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-00-question — FAIL

Верно ли, что иван хочет читать книгу?

Результат шага обрезан в выгрузке.

- Строки 6814 → 6815. Внешняя связь: Вопрос
- Строки 6816 → 6817. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6818 → 6819. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6820 → 6821. Проверка разбиения: Proposed split — part 1: «иван хочет читать книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6822 → 6823. Внешняя связь: Одна предикация / именное описание
- Строки 6824 → 6825. Состав и чтение конструкции: Infinitive area «читать книгу»; remaining parent «иван хочет»
- Строки 6826 → 6827. Внешняя связь: Одна предикация / именное описание
- Строки 6828 → 6829. Состав и чтение конструкции: «читать» fills OBJECT of «хочет» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 6830 → 6831. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-01-base — FAIL

Иван решил открыть окно.

Результат шага обрезан в выгрузке.

- Строки 6836 → 6837. Внешняя связь: Одна предикация / именное описание
- Строки 6838 → 6839. Состав и чтение конструкции: Infinitive area «открыть окно.»; remaining parent «Иван решил»
- Строки 6840 → 6841. Внешняя связь: Одна предикация / именное описание
- Строки 6842 → 6843. Состав и чтение конструкции: «открыть» fills OBJECT of «решил» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 6844 → 6845. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### NONFINITE-01-quote — FAIL

Пётр сказал: «Иван решил открыть окно».

Результат шага обрезан в выгрузке.

- Строки 6850 → 6851. Внешняя связь: Пропозициональное содержание
- Строки 6852 → 6853. Вложенное содержание: начало: Начать с «Иван» @14
- Строки 6854 → 6855. Вложенное содержание: конец: Закончить после «окно» @37; выбранные слова «Иван решил открыть окно»
- Строки 6856 → 6857. Родительская часть: начало: Начать с «Пётр» @0
- Строки 6858 → 6859. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Пётр сказал : « »»
- Строки 6860 → 6861. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Иван решил открыть окно»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6862 → 6863. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 6864 → 6865. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6866 → 6867. Внешняя связь: Одна предикация / именное описание
- Строки 6868 → 6869. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6870 → 6871. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-01-nested_quote — FAIL

Иван сказал, что Пётр думает: «Иван решил открыть окно».

Результат шага обрезан в выгрузке.

- Строки 6876 → 6877. Внешняя связь: Пропозициональное содержание
- Строки 6878 → 6879. Вложенное содержание: начало: Начать с «Иван» @31
- Строки 6880 → 6881. Вложенное содержание: конец: Закончить после «окно» @54; выбранные слова «Иван решил открыть окно»
- Строки 6882 → 6883. Родительская часть: начало: Начать с «Иван» @0
- Строки 6884 → 6885. Родительская часть: конец: Закончить после «.» @56; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 6886 → 6887. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Иван решил открыть окно»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 6888 → 6889. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 6890 → 6891. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6892 → 6893. Внешняя связь: Одна предикация / именное описание
- Строки 6894 → 6895. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6896 → 6897. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-01-question — FAIL

Верно ли, что иван решил открыть окно?

Результат шага обрезан в выгрузке.

- Строки 6902 → 6903. Внешняя связь: Вопрос
- Строки 6904 → 6905. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6906 → 6907. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6908 → 6909. Проверка разбиения: Proposed split — part 1: «иван решил открыть окно»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 6910 → 6911. Внешняя связь: Одна предикация / именное описание
- Строки 6912 → 6913. Состав и чтение конструкции: Infinitive area «открыть окно»; remaining parent «иван решил»
- Строки 6914 → 6915. Внешняя связь: Одна предикация / именное описание
- Строки 6916 → 6917. Состав и чтение конструкции: «открыть» fills OBJECT of «решил» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 6918 → 6919. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-02-base — FAIL

Пётр намерен уехать.

Результат шага обрезан в выгрузке.

- Строки 6924 → 6925. Внешняя связь: Одна предикация / именное описание
- Строки 6926 → 6927. Состав и чтение конструкции: Infinitive area «уехать.»; remaining parent «Пётр намерен»
- Строки 6928 → 6929. Внешняя связь: Одна предикация / именное описание
- Строки 6930 → 6931. Состав и чтение конструкции: намеренный [ADJS]; SUBJECT=Пётр
- Строки 6932 → 6933. Состав и чтение конструкции: «уехать» fills OBJECT of «намерен» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Пётр» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 6934 → 6935. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### NONFINITE-02-quote — FAIL

Пётр сказал: «Пётр намерен уехать».

Результат шага обрезан в выгрузке.

- Строки 6940 → 6941. Внешняя связь: Пропозициональное содержание
- Строки 6942 → 6943. Вложенное содержание: начало: Начать с «Пётр» @14
- Строки 6944 → 6945. Вложенное содержание: конец: Закончить после «уехать» @33; выбранные слова «Пётр намерен уехать»
- Строки 6946 → 6947. Родительская часть: начало: Начать с «Пётр» @0
- Строки 6948 → 6949. Родительская часть: конец: Закончить после «»» @34; выбранные слова «Пётр сказал : « »»
- Строки 6950 → 6951. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Пётр намерен уехать»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 6952 → 6953. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 6954 → 6955. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6956 → 6957. Внешняя связь: Одна предикация / именное описание
- Строки 6958 → 6959. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6960 → 6961. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-02-nested_quote — FAIL

Иван сказал, что Пётр думает: «Пётр намерен уехать».

Результат шага обрезан в выгрузке.

- Строки 6966 → 6967. Внешняя связь: Пропозициональное содержание
- Строки 6968 → 6969. Вложенное содержание: начало: Начать с «Пётр» @31
- Строки 6970 → 6971. Вложенное содержание: конец: Закончить после «уехать» @50; выбранные слова «Пётр намерен уехать»
- Строки 6972 → 6973. Родительская часть: начало: Начать с «Иван» @0
- Строки 6974 → 6975. Родительская часть: конец: Закончить после «.» @52; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 6976 → 6977. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Пётр намерен уехать»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 6978 → 6979. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 6980 → 6981. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 6982 → 6983. Внешняя связь: Одна предикация / именное описание
- Строки 6984 → 6985. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 6986 → 6987. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-02-question — FAIL

Верно ли, что пётр намерен уехать?

Результат шага обрезан в выгрузке.

- Строки 6992 → 6993. Внешняя связь: Вопрос
- Строки 6994 → 6995. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 6996 → 6997. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 6998 → 6999. Проверка разбиения: Proposed split — part 1: «пётр намерен уехать»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 7000 → 7001. Внешняя связь: Одна предикация / именное описание
- Строки 7002 → 7003. Состав и чтение конструкции: Infinitive area «уехать»; remaining parent «пётр намерен»
- Строки 7004 → 7005. Внешняя связь: Одна предикация / именное описание
- Строки 7006 → 7007. Состав и чтение конструкции: намеренный [ADJS]; SUBJECT=пётр
- Строки 7008 → 7009. Состав и чтение конструкции: «уехать» fills OBJECT of «намерен» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «пётр» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 7010 → 7011. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-03-base — FAIL

Мария просит Ивана принести книгу.

Результат шага обрезан в выгрузке.

- Строки 7016 → 7017. Внешняя связь: Пропозициональное содержание
- Строки 7018 → 7019. Вложенное содержание: начало: Начать с «принести» @19
- Строки 7020 → 7021. Вложенное содержание: конец: Закончить после «книгу» @33; выбранные слова «принести книгу»
- Строки 7022 → 7023. Родительская часть: начало: Начать с «Мария» @0
- Строки 7024 → 7025. Родительская часть: конец: Закончить после «.» @34; выбранные слова «Мария просит Ивана .»
- Строки 7026 → 7027. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария просит Ивана .»; content filling that slot: «принести книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 7028 → 7029. Предикат — владелец содержания: Content belongs to predicate «просит» @6
- Строки 7030 → 7031. Роль и статус вложенного содержания: OBJECT of «просит»; attitude=HYPOTHETICAL; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7032 → 7033. Внешняя связь: Одна предикация / именное описание
- Строки 7034 → 7035. Именная зависимость: Ни один показанный вариант не подошёл (0)
- Строки 7036 → 7037. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7038 → 7039. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-03-quote — FAIL

Пётр сказал: «Мария просит Ивана принести книгу».

Результат шага обрезан в выгрузке.

- Строки 7044 → 7045. Внешняя связь: Пропозициональное содержание
- Строки 7046 → 7047. Вложенное содержание: начало: Начать с «Мария» @14
- Строки 7048 → 7049. Вложенное содержание: конец: Закончить после «книгу» @47; выбранные слова «Мария просит Ивана принести книгу»
- Строки 7050 → 7051. Родительская часть: начало: Начать с «Пётр» @0
- Строки 7052 → 7053. Родительская часть: конец: Закончить после «»» @48; выбранные слова «Пётр сказал : « »»
- Строки 7054 → 7055. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Мария просит Ивана принести книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7056 → 7057. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 7058 → 7059. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7060 → 7061. Внешняя связь: Одна предикация / именное описание
- Строки 7062 → 7063. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7064 → 7065. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-03-nested_quote — FAIL

Иван сказал, что Пётр думает: «Мария просит Ивана принести книгу».

Результат шага обрезан в выгрузке.

- Строки 7070 → 7071. Внешняя связь: Пропозициональное содержание
- Строки 7072 → 7073. Вложенное содержание: начало: Начать с «Мария» @31
- Строки 7074 → 7075. Вложенное содержание: конец: Закончить после «книгу» @64; выбранные слова «Мария просит Ивана принести книгу»
- Строки 7076 → 7077. Родительская часть: начало: Начать с «Иван» @0
- Строки 7078 → 7079. Родительская часть: конец: Закончить после «.» @66; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 7080 → 7081. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Мария просит Ивана принести книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 7082 → 7083. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 7084 → 7085. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7086 → 7087. Внешняя связь: Одна предикация / именное описание
- Строки 7088 → 7089. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7090 → 7091. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-03-question — FAIL

Верно ли, что мария просит Ивана принести книгу?

Результат шага обрезан в выгрузке.

- Строки 7096 → 7097. Внешняя связь: Вопрос
- Строки 7098 → 7099. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 7100 → 7101. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 7102 → 7103. Проверка разбиения: Proposed split — part 1: «мария просит Ивана принести книгу»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 7104 → 7105. Внешняя связь: Одна предикация / именное описание
- Строки 7106 → 7107. Состав и чтение конструкции: Infinitive area «принести книгу»; remaining parent «мария просит Ивана»
- Строки 7108 → 7109. Внешняя связь: Одна предикация / именное описание
- Строки 7110 → 7111. Именная зависимость: Direct role RECIPIENT of predicate «просит» (recipient or addressee of the action); lemma: иван; pos: noun; cases: accusative; number: singular; gender: masculine; features: personal name, animate
- Строки 7112 → 7113. Состав и чтение конструкции: «принести» fills OBJECT of «просит» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME RECIPIENT «Ивана» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 7114 → 7115. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-04-base — FAIL

Мне хочется спать.

Результат шага обрезан в выгрузке.

- Строки 7120 → 7121. Внешняя связь: Одна предикация / именное описание
- Строки 7122 → 7123. Состав и чтение конструкции: Infinitive area «спать.»; remaining parent «Мне хочется»
- Строки 7124 → 7125. Внешняя связь: Одна предикация / именное описание
- Строки 7126 → 7127. Состав и чтение конструкции: хотеться [VERB]; EXPERIENCER=Мне; impersonal state; dative participant experiences it; no separate grammatical subject
- Строки 7128 → 7129. Состав и чтение конструкции: «спать» fills OBJECT of «хочется» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME EXPERIENCER «Мне» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 7130 → 7131. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### NONFINITE-04-quote — FAIL

Пётр сказал: «Мне хочется спать».

Результат шага обрезан в выгрузке.

- Строки 7136 → 7137. Внешняя связь: Пропозициональное содержание
- Строки 7138 → 7139. Вложенное содержание: начало: Начать с «Мне» @14
- Строки 7140 → 7141. Вложенное содержание: конец: Закончить после «спать» @31; выбранные слова «Мне хочется спать»
- Строки 7142 → 7143. Родительская часть: начало: Начать с «Пётр» @0
- Строки 7144 → 7145. Родительская часть: конец: Закончить после «»» @32; выбранные слова «Пётр сказал : « »»
- Строки 7146 → 7147. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Мне хочется спать»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7148 → 7149. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 7150 → 7151. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7152 → 7153. Внешняя связь: Одна предикация / именное описание
- Строки 7154 → 7155. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7156 → 7157. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-04-nested_quote — FAIL

Иван сказал, что Пётр думает: «Мне хочется спать».

Результат шага обрезан в выгрузке.

- Строки 7162 → 7163. Внешняя связь: Пропозициональное содержание
- Строки 7164 → 7165. Вложенное содержание: начало: Начать с «Мне» @31
- Строки 7166 → 7167. Вложенное содержание: конец: Закончить после «спать» @48; выбранные слова «Мне хочется спать»
- Строки 7168 → 7169. Родительская часть: начало: Начать с «Иван» @0
- Строки 7170 → 7171. Родительская часть: конец: Закончить после «.» @50; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 7172 → 7173. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Мне хочется спать»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 7174 → 7175. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 7176 → 7177. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7178 → 7179. Внешняя связь: Одна предикация / именное описание
- Строки 7180 → 7181. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7182 → 7183. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-04-question — FAIL

Верно ли, что мне хочется спать?

Результат шага обрезан в выгрузке.

- Строки 7188 → 7189. Внешняя связь: Вопрос
- Строки 7190 → 7191. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 7192 → 7193. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 7194 → 7195. Проверка разбиения: Proposed split — part 1: «мне хочется спать»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 7196 → 7197. Внешняя связь: Одна предикация / именное описание
- Строки 7198 → 7199. Состав и чтение конструкции: Infinitive area «спать»; remaining parent «мне хочется»
- Строки 7200 → 7201. Внешняя связь: Одна предикация / именное описание
- Строки 7202 → 7203. Состав и чтение конструкции: хотеться [VERB]; EXPERIENCER=мне; impersonal state; dative participant experiences it; no separate grammatical subject
- Строки 7204 → 7205. Состав и чтение конструкции: «спать» fills OBJECT of «хочется» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME EXPERIENCER «мне» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 7206 → 7207. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-05-base — FAIL

Иван надеется вернуться.

Результат шага обрезан в выгрузке.

- Строки 7212 → 7213. Внешняя связь: Одна предикация / именное описание
- Строки 7214 → 7215. Состав и чтение конструкции: Infinitive area «вернуться.»; remaining parent «Иван надеется»
- Строки 7216 → 7217. Внешняя связь: Одна предикация / именное описание
- Строки 7218 → 7219. Состав и чтение конструкции: «вернуться» fills OBJECT of «надеется» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 7220 → 7221. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### NONFINITE-05-quote — FAIL

Пётр сказал: «Иван надеется вернуться».

Результат шага обрезан в выгрузке.

- Строки 7226 → 7227. Внешняя связь: Пропозициональное содержание
- Строки 7228 → 7229. Вложенное содержание: начало: Начать с «Иван» @14
- Строки 7230 → 7231. Вложенное содержание: конец: Закончить после «вернуться» @37; выбранные слова «Иван надеется вернуться»
- Строки 7232 → 7233. Родительская часть: начало: Начать с «Пётр» @0
- Строки 7234 → 7235. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Пётр сказал : « »»
- Строки 7236 → 7237. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Иван надеется вернуться»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7238 → 7239. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 7240 → 7241. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7242 → 7243. Внешняя связь: Одна предикация / именное описание
- Строки 7244 → 7245. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7246 → 7247. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-05-nested_quote — FAIL

Иван сказал, что Пётр думает: «Иван надеется вернуться».

Результат шага обрезан в выгрузке.

- Строки 7252 → 7253. Внешняя связь: Пропозициональное содержание
- Строки 7254 → 7255. Вложенное содержание: начало: Начать с «Иван» @31
- Строки 7256 → 7257. Вложенное содержание: конец: Закончить после «вернуться» @54; выбранные слова «Иван надеется вернуться»
- Строки 7258 → 7259. Родительская часть: начало: Начать с «Иван» @0
- Строки 7260 → 7261. Родительская часть: конец: Закончить после «.» @56; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 7262 → 7263. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Иван надеется вернуться»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 7264 → 7265. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 7266 → 7267. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7268 → 7269. Внешняя связь: Одна предикация / именное описание
- Строки 7270 → 7271. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7272 → 7273. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-05-question — FAIL

Верно ли, что иван надеется вернуться?

Результат шага обрезан в выгрузке.

- Строки 7278 → 7279. Внешняя связь: Вопрос
- Строки 7280 → 7281. Вводящее выражение: начало: Начать с «Верно» @0
- Строки 7282 → 7283. Вводящее выражение: конец: Закончить после «что» @13; выбранные слова «Верно ли , что»
- Строки 7284 → 7285. Проверка разбиения: Proposed split — part 1: «иван надеется вернуться»; outer relation occurrences: «Верно» @0, «ли» @6, «что» @10; punctuation outside parts: «, ?»
- Строки 7286 → 7287. Внешняя связь: Одна предикация / именное описание
- Строки 7288 → 7289. Состав и чтение конструкции: Infinitive area «вернуться»; remaining parent «иван надеется»
- Строки 7290 → 7291. Внешняя связь: Одна предикация / именное описание
- Строки 7292 → 7293. Состав и чтение конструкции: «вернуться» fills OBJECT of «надеется» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 7294 → 7295. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: SPEECH_ACT_QUERY.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-06-base — FAIL

Книгу можно прочитать.

Результат шага обрезан в выгрузке.

- Строки 7300 → 7301. Внешняя связь: Возможность
- Строки 7302 → 7303. Вводящее выражение: начало: Начать с «можно» @6
- Строки 7304 → 7305. Вводящее выражение: конец: Закончить после «прочитать» @21; выбранные слова «можно прочитать»
- Строки 7306 → 7307. Проверка разбиения: Proposed split — part 1: «Книгу»; outer relation occurrences: «можно» @6, «прочитать» @12; punctuation outside parts: «.»
- Строки 7308 → 7309. Высказывание или название события: Nominal event head «Книгу» @0
- Строки 7310 → 7311. Состав и чтение конструкции: книга [NOUN]; SUBJECT=Книгу

Первая записанная диагностика: нет.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Формула непустая, но отличается от эталона по структуре, ролям или значениям; это не простой отказ модели.**

### NONFINITE-06-quote — FAIL

Пётр сказал: «Книгу можно прочитать».

Результат шага обрезан в выгрузке.

- Строки 7316 → 7317. Внешняя связь: Пропозициональное содержание
- Строки 7318 → 7319. Вложенное содержание: начало: Начать с «Книгу» @14
- Строки 7320 → 7321. Вложенное содержание: конец: Закончить после «прочитать» @35; выбранные слова «Книгу можно прочитать»
- Строки 7322 → 7323. Родительская часть: начало: Начать с «Пётр» @0
- Строки 7324 → 7325. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Пётр сказал : « »»
- Строки 7326 → 7327. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Книгу можно прочитать»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7328 → 7329. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 7330 → 7331. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7332 → 7333. Внешняя связь: Одна предикация / именное описание
- Строки 7334 → 7335. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7336 → 7337. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-06-nested_quote — FAIL

Иван сказал, что Пётр думает: «Книгу можно прочитать».

Результат шага обрезан в выгрузке.

- Строки 7342 → 7343. Внешняя связь: Пропозициональное содержание
- Строки 7344 → 7345. Вложенное содержание: начало: Начать с «Книгу» @31
- Строки 7346 → 7347. Вложенное содержание: конец: Закончить после «прочитать» @52; выбранные слова «Книгу можно прочитать»
- Строки 7348 → 7349. Родительская часть: начало: Начать с «Иван» @0
- Строки 7350 → 7351. Родительская часть: конец: Закончить после «.» @54; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 7352 → 7353. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Книгу можно прочитать»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 7354 → 7355. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 7356 → 7357. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7358 → 7359. Внешняя связь: Одна предикация / именное описание
- Строки 7360 → 7361. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7362 → 7363. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-06-question — FAIL

Верно ли, что книгу можно прочитать?

Результат шага обрезан в выгрузке.

- Строки 7368 → 7369. Внешняя связь: Вопрос
- Строки 7370 → 7371. Вводящее выражение: начало: Начать с «что» @10
- Строки 7372 → 7373. Вводящее выражение: конец: Закончить после «прочитать» @35; выбранные слова «что книгу можно прочитать»
- Строки 7374 → 7375. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7376 → 7377. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/generation/gold_patterns`.

### NONFINITE-07-base — FAIL

Нужно открыть окно.

Результат шага обрезан в выгрузке.

- Строки 7382 → 7383. Внешняя связь: Возможность
- Строки 7384 → 7385. Вводящее выражение: начало: Начать с «Нужно» @0
- Строки 7386 → 7387. Вводящее выражение: конец: Закончить после «Нужно» @5; выбранные слова «Нужно»
- Строки 7388 → 7389. Проверка разбиения: Proposed split — part 1: «открыть окно»; outer relation occurrences: «Нужно» @0; punctuation outside parts: «.»
- Строки 7390 → 7391. Управление модальным содержанием: Agreement/controller anchor «Нужно»
- Строки 7392 → 7393. Внешняя связь: Одна предикация / именное описание
- Строки 7394 → 7395. Именная зависимость: Direct role OBJECT of predicate «открыть» (direct object or content of the predicate); lemma: окно; pos: noun; cases: accusative; number: singular; gender: neuter; features: inanimate
- Строки 7396 → 7397. Состав и чтение конструкции: открыть [INFN]; OBJECT=окно
- Строки 7398 → 7399. implicit_argument: The text "Нужно открыть окно" (It is necessary to open the window) is an impersonal construction in Russian. The grammatical features of the omitted participant are specified as `{'gender': 'neut', 'number': 'sing'}`. However, in impersonal sentences with the infinitive (like "нужно + infinitive"), the subject is typically not a specific animate entity but rather an abstract necessity or a generic "one". The text does not provide any antecedent, narrator perspective (first or third person), or specific context to identify a particular individual or group as the subject. The options provided are:
1. Unidentified referent...
2. Current unidentified narrator...
3. A DIFFERENT unidentified narrator...

Since the text is a single sentence fragment without established narration or context linking it to a specific narrator or character, and the construction is impersonal, there is no evidence to support identifying the subject as the narrator (Option 2) or a different narrator (Option 3). The most accurate description based *only* on the supplied text is that the referent is unidentified and no antecedent is established.

1

Первая записанная диагностика: COMPONENT_PROBE_FAILED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-07-quote — FAIL

Пётр сказал: «Нужно открыть окно».

Результат шага обрезан в выгрузке.

- Строки 7404 → 7405. Внешняя связь: Пропозициональное содержание
- Строки 7406 → 7407. Вложенное содержание: начало: Начать с «Нужно» @14
- Строки 7408 → 7409. Вложенное содержание: конец: Закончить после «окно» @32; выбранные слова «Нужно открыть окно»
- Строки 7410 → 7411. Родительская часть: начало: Начать с «Пётр» @0
- Строки 7412 → 7413. Родительская часть: конец: Закончить после «»» @33; выбранные слова «Пётр сказал : « »»
- Строки 7414 → 7415. Проверка разбиения: Proposed split — parent clause with a content slot: «Пётр сказал : « »»; content filling that slot: «Нужно открыть окно»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7416 → 7417. Предикат — владелец содержания: Content belongs to predicate «сказал» @5
- Строки 7418 → 7419. Роль и статус вложенного содержания: OBJECT of «сказал»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7420 → 7421. Внешняя связь: Одна предикация / именное описание
- Строки 7422 → 7423. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7424 → 7425. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-07-nested_quote — FAIL

Иван сказал, что Пётр думает: «Нужно открыть окно».

Результат шага обрезан в выгрузке.

- Строки 7430 → 7431. Внешняя связь: Пропозициональное содержание
- Строки 7432 → 7433. Вложенное содержание: начало: Начать с «Нужно» @31
- Строки 7434 → 7435. Вложенное содержание: конец: Закончить после «окно» @49; выбранные слова «Нужно открыть окно»
- Строки 7436 → 7437. Родительская часть: начало: Начать с «Иван» @0
- Строки 7438 → 7439. Родительская часть: конец: Закончить после «.» @51; выбранные слова «Иван сказал , что Пётр думает : « » .»
- Строки 7440 → 7441. Проверка разбиения: Proposed split — parent clause with a content slot: «Иван сказал , что Пётр думает : « » .»; content filling that slot: «Нужно открыть окно»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 7442 → 7443. Предикат — владелец содержания: Content belongs to predicate «думает» @22
- Строки 7444 → 7445. Роль и статус вложенного содержания: OBJECT of «думает»; attitude=EMBEDDED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7446 → 7447. Внешняя связь: Одна предикация / именное описание
- Строки 7448 → 7449. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7450 → 7451. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

### NONFINITE-07-question — FAIL

Верно ли, что нужно открыть окно?

Результат шага обрезан в выгрузке.

- Строки 7456 → 7457. Внешняя связь: Вопрос
- Строки 7458 → 7459. Вводящее выражение: начало: Начать с «что» @10
- Строки 7460 → 7461. Вводящее выражение: конец: Закончить после «?» @33; выбранные слова «что нужно открыть окно ?»
- Строки 7462 → 7463. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7464 → 7465. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/generation/gold_patterns`.

### OPEN-00-0-asserted — PASS

Иван глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7470 → 7471. Грамматическое чтение неизвестного слова: Source «глоркнул»: predicted inflection; lemma: глоркнуть; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 7472 → 7473. Внешняя связь: Одна предикация / именное описание
- Строки 7474 → 7475. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.

### OPEN-00-0-not — FAIL

Иван не глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7480 → 7481. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7482 → 7483. Внешняя связь: Отрицание
- Строки 7484 → 7485. Вводящее выражение: начало: Начать с «не» @5
- Строки 7486 → 7487. Вводящее выражение: конец: Закончить после «глоркнул» @16; выбранные слова «не глоркнул»
- Строки 7488 → 7489. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7490 → 7491. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-0-quoted — FAIL

Мария сказала: «Иван глоркнул книгу».

Результат шага обрезан в выгрузке.

- Строки 7496 → 7497. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7498 → 7499. Внешняя связь: Пропозициональное содержание
- Строки 7500 → 7501. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 7502 → 7503. Вложенное содержание: конец: Закончить после «книгу» @35; выбранные слова «Иван глоркнул книгу»
- Строки 7504 → 7505. Родительская часть: начало: Начать с «Мария» @0
- Строки 7506 → 7507. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 7508 → 7509. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван глоркнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7510 → 7511. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7512 → 7513. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7514 → 7515. Внешняя связь: Одна предикация / именное описание
- Строки 7516 → 7517. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7518 → 7519. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-0-or — FAIL

Иван глоркнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 7524 → 7525. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7526 → 7527. Внешняя связь: Включающее «или»
- Строки 7528 → 7529. Первая часть: начало: Начать с «Иван» @0
- Строки 7530 → 7531. Первая часть: конец: Закончить после «книгу» @19; выбранные слова «Иван глоркнул книгу»
- Строки 7532 → 7533. Вторая часть: начало: Начать с «Мария» @24
- Строки 7534 → 7535. Вторая часть: конец: Закончить после «уснула» @36; выбранные слова «Мария уснула»
- Строки 7536 → 7537. Проверка разбиения: Proposed split — part 1: «Иван глоркнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @20; punctuation outside parts: «.»
- Строки 7538 → 7539. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7540 → 7541. Внешняя связь: Одна предикация / именное описание
- Строки 7542 → 7543. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 7544 → 7545. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-00-1-asserted — FAIL

Пётр глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7550 → 7551. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7552 → 7553. Внешняя связь: Одна предикация / именное описание
- Строки 7554 → 7555. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-00-1-not — FAIL

Пётр не глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7560 → 7561. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7562 → 7563. Внешняя связь: Отрицание
- Строки 7564 → 7565. Вводящее выражение: начало: Начать с «не» @5
- Строки 7566 → 7567. Вводящее выражение: конец: Закончить после «глоркнул» @16; выбранные слова «не глоркнул»
- Строки 7568 → 7569. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7570 → 7571. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-1-quoted — FAIL

Мария сказала: «Пётр глоркнул книгу».

Результат шага обрезан в выгрузке.

- Строки 7576 → 7577. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7578 → 7579. Внешняя связь: Пропозициональное содержание
- Строки 7580 → 7581. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 7582 → 7583. Вложенное содержание: конец: Закончить после «книгу» @35; выбранные слова «Пётр глоркнул книгу»
- Строки 7584 → 7585. Родительская часть: начало: Начать с «Мария» @0
- Строки 7586 → 7587. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 7588 → 7589. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр глоркнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7590 → 7591. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7592 → 7593. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7594 → 7595. Внешняя связь: Одна предикация / именное описание
- Строки 7596 → 7597. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7598 → 7599. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-1-or — FAIL

Пётр глоркнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 7604 → 7605. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7606 → 7607. Внешняя связь: Включающее «или»
- Строки 7608 → 7609. Первая часть: начало: Начать с «Пётр» @0
- Строки 7610 → 7611. Первая часть: конец: Закончить после «книгу» @19; выбранные слова «Пётр глоркнул книгу»
- Строки 7612 → 7613. Вторая часть: начало: Начать с «Мария» @24
- Строки 7614 → 7615. Вторая часть: конец: Закончить после «уснула» @36; выбранные слова «Мария уснула»
- Строки 7616 → 7617. Проверка разбиения: Proposed split — part 1: «Пётр глоркнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @20; punctuation outside parts: «.»
- Строки 7618 → 7619. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7620 → 7621. Внешняя связь: Одна предикация / именное описание
- Строки 7622 → 7623. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 7624 → 7625. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-00-2-asserted — FAIL

Сергей глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7630 → 7631. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7632 → 7633. Внешняя связь: Одна предикация / именное описание
- Строки 7634 → 7635. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-00-2-not — FAIL

Сергей не глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7640 → 7641. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7642 → 7643. Внешняя связь: Отрицание
- Строки 7644 → 7645. Вводящее выражение: начало: Начать с «не» @7
- Строки 7646 → 7647. Вводящее выражение: конец: Закончить после «глоркнул» @18; выбранные слова «не глоркнул»
- Строки 7648 → 7649. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7650 → 7651. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-2-quoted — FAIL

Мария сказала: «Сергей глоркнул книгу».

Результат шага обрезан в выгрузке.

- Строки 7656 → 7657. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7658 → 7659. Внешняя связь: Пропозициональное содержание
- Строки 7660 → 7661. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 7662 → 7663. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Сергей глоркнул книгу»
- Строки 7664 → 7665. Родительская часть: начало: Начать с «Мария» @0
- Строки 7666 → 7667. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 7668 → 7669. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей глоркнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7670 → 7671. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7672 → 7673. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7674 → 7675. Внешняя связь: Одна предикация / именное описание
- Строки 7676 → 7677. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7678 → 7679. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-2-or — FAIL

Сергей глоркнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 7684 → 7685. Грамматическое чтение неизвестного слова: Source «глоркнул»: predicted inflection; lemma: глоркнуть; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 7686 → 7687. Внешняя связь: Включающее «или»
- Строки 7688 → 7689. Первая часть: начало: Начать с «Сергей» @0
- Строки 7690 → 7691. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Сергей глоркнул книгу»
- Строки 7692 → 7693. Вторая часть: начало: Начать с «Мария» @26
- Строки 7694 → 7695. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 7696 → 7697. Проверка разбиения: Proposed split — part 1: «Сергей глоркнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 7698 → 7699. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7700 → 7701. Внешняя связь: Одна предикация / именное описание
- Строки 7702 → 7703. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 7704 → 7705. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-00-3-asserted — FAIL

Алексей глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7710 → 7711. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7712 → 7713. Внешняя связь: Одна предикация / именное описание
- Строки 7714 → 7715. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-00-3-not — FAIL

Алексей не глоркнул книгу.

Результат шага обрезан в выгрузке.

- Строки 7720 → 7721. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7722 → 7723. Внешняя связь: Отрицание
- Строки 7724 → 7725. Вводящее выражение: начало: Начать с «не» @8
- Строки 7726 → 7727. Вводящее выражение: конец: Закончить после «глоркнул» @19; выбранные слова «не глоркнул»
- Строки 7728 → 7729. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7730 → 7731. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-3-quoted — FAIL

Мария сказала: «Алексей глоркнул книгу».

Результат шага обрезан в выгрузке.

- Строки 7736 → 7737. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7738 → 7739. Внешняя связь: Пропозициональное содержание
- Строки 7740 → 7741. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 7742 → 7743. Вложенное содержание: конец: Закончить после «книгу» @38; выбранные слова «Алексей глоркнул книгу»
- Строки 7744 → 7745. Родительская часть: начало: Начать с «Мария» @0
- Строки 7746 → 7747. Родительская часть: конец: Закончить после «»» @39; выбранные слова «Мария сказала : « »»
- Строки 7748 → 7749. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей глоркнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7750 → 7751. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7752 → 7753. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7754 → 7755. Внешняя связь: Одна предикация / именное описание
- Строки 7756 → 7757. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7758 → 7759. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-00-3-or — FAIL

Алексей глоркнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 7764 → 7765. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7766 → 7767. Внешняя связь: Включающее «или»
- Строки 7768 → 7769. Первая часть: начало: Начать с «Алексей» @0
- Строки 7770 → 7771. Первая часть: конец: Закончить после «книгу» @22; выбранные слова «Алексей глоркнул книгу»
- Строки 7772 → 7773. Вторая часть: начало: Начать с «Мария» @27
- Строки 7774 → 7775. Вторая часть: конец: Закончить после «уснула» @39; выбранные слова «Мария уснула»
- Строки 7776 → 7777. Проверка разбиения: Proposed split — part 1: «Алексей глоркнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @23; punctuation outside parts: «.»
- Строки 7778 → 7779. Грамматическое чтение неизвестного слова: Source «глоркнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7780 → 7781. Внешняя связь: Одна предикация / именное описание
- Строки 7782 → 7783. Именная зависимость: Direct role OBJECT of predicate «глоркнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 7784 → 7785. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-0-asserted — FAIL

Иван зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 7790 → 7791. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7792 → 7793. Внешняя связь: Одна предикация / именное описание
- Строки 7794 → 7795. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-0-not — FAIL

Иван не зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 7800 → 7801. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7802 → 7803. Внешняя связь: Отрицание
- Строки 7804 → 7805. Вводящее выражение: начало: Начать с «не» @5
- Строки 7806 → 7807. Вводящее выражение: конец: Закончить после «не» @7; выбранные слова «не»
- Строки 7808 → 7809. Проверка разбиения: Proposed split — part 1: «Иван зумбировал книгу»; outer relation occurrences: «не» @5; punctuation outside parts: «.»
- Строки 7810 → 7811. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7812 → 7813. Внешняя связь: Одна предикация / именное описание
- Строки 7814 → 7815. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-0-quoted — FAIL

Мария сказала: «Иван зумбировал книгу».

Результат шага обрезан в выгрузке.

- Строки 7820 → 7821. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7822 → 7823. Внешняя связь: Пропозициональное содержание
- Строки 7824 → 7825. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 7826 → 7827. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Иван зумбировал книгу»
- Строки 7828 → 7829. Родительская часть: начало: Начать с «Мария» @0
- Строки 7830 → 7831. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 7832 → 7833. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван зумбировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7834 → 7835. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7836 → 7837. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7838 → 7839. Внешняя связь: Одна предикация / именное описание
- Строки 7840 → 7841. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7842 → 7843. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-0-or — FAIL

Иван зумбировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 7848 → 7849. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7850 → 7851. Внешняя связь: Включающее «или»
- Строки 7852 → 7853. Первая часть: начало: Начать с «Иван» @0
- Строки 7854 → 7855. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Иван зумбировал книгу»
- Строки 7856 → 7857. Вторая часть: начало: Начать с «Мария» @26
- Строки 7858 → 7859. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 7860 → 7861. Проверка разбиения: Proposed split — part 1: «Иван зумбировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 7862 → 7863. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7864 → 7865. Внешняя связь: Одна предикация / именное описание
- Строки 7866 → 7867. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 7868 → 7869. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-1-asserted — FAIL

Пётр зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 7874 → 7875. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7876 → 7877. Внешняя связь: Одна предикация / именное описание
- Строки 7878 → 7879. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-1-not — FAIL

Пётр не зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 7884 → 7885. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7886 → 7887. Внешняя связь: Отрицание
- Строки 7888 → 7889. Вводящее выражение: начало: Начать с «не» @5
- Строки 7890 → 7891. Вводящее выражение: конец: Закончить после «зумбировал» @18; выбранные слова «не зумбировал»
- Строки 7892 → 7893. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7894 → 7895. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-1-quoted — FAIL

Мария сказала: «Пётр зумбировал книгу».

Результат шага обрезан в выгрузке.

- Строки 7900 → 7901. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7902 → 7903. Внешняя связь: Пропозициональное содержание
- Строки 7904 → 7905. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 7906 → 7907. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Пётр зумбировал книгу»
- Строки 7908 → 7909. Родительская часть: начало: Начать с «Мария» @0
- Строки 7910 → 7911. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 7912 → 7913. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр зумбировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7914 → 7915. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7916 → 7917. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7918 → 7919. Внешняя связь: Одна предикация / именное описание
- Строки 7920 → 7921. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 7922 → 7923. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-1-or — FAIL

Пётр зумбировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 7928 → 7929. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7930 → 7931. Внешняя связь: Включающее «или»
- Строки 7932 → 7933. Первая часть: начало: Начать с «Пётр» @0
- Строки 7934 → 7935. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Пётр зумбировал книгу»
- Строки 7936 → 7937. Вторая часть: начало: Начать с «Мария» @26
- Строки 7938 → 7939. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 7940 → 7941. Проверка разбиения: Proposed split — part 1: «Пётр зумбировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 7942 → 7943. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7944 → 7945. Внешняя связь: Одна предикация / именное описание
- Строки 7946 → 7947. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 7948 → 7949. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-2-asserted — PASS

Сергей зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 7954 → 7955. Грамматическое чтение неизвестного слова: Source «зумбировал»: predicted inflection; lemma: зумбировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 7956 → 7957. Внешняя связь: Одна предикация / именное описание
- Строки 7958 → 7959. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.

### OPEN-01-2-not — FAIL

Сергей не зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 7964 → 7965. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7966 → 7967. Внешняя связь: Отрицание
- Строки 7968 → 7969. Вводящее выражение: начало: Начать с «не» @7
- Строки 7970 → 7971. Вводящее выражение: конец: Закончить после «зумбировал» @20; выбранные слова «не зумбировал»
- Строки 7972 → 7973. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 7974 → 7975. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-2-quoted — FAIL

Мария сказала: «Сергей зумбировал книгу».

Результат шага обрезан в выгрузке.

- Строки 7980 → 7981. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 7982 → 7983. Внешняя связь: Пропозициональное содержание
- Строки 7984 → 7985. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 7986 → 7987. Вложенное содержание: конец: Закончить после «книгу» @39; выбранные слова «Сергей зумбировал книгу»
- Строки 7988 → 7989. Родительская часть: начало: Начать с «Мария» @0
- Строки 7990 → 7991. Родительская часть: конец: Закончить после «»» @40; выбранные слова «Мария сказала : « »»
- Строки 7992 → 7993. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей зумбировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 7994 → 7995. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 7996 → 7997. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 7998 → 7999. Внешняя связь: Одна предикация / именное описание
- Строки 8000 → 8001. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8002 → 8003. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-2-or — FAIL

Сергей зумбировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8008 → 8009. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8010 → 8011. Внешняя связь: Включающее «или»
- Строки 8012 → 8013. Первая часть: начало: Начать с «Сергей» @0
- Строки 8014 → 8015. Первая часть: конец: Закончить после «книгу» @23; выбранные слова «Сергей зумбировал книгу»
- Строки 8016 → 8017. Вторая часть: начало: Начать с «Мария» @28
- Строки 8018 → 8019. Вторая часть: конец: Закончить после «уснула» @40; выбранные слова «Мария уснула»
- Строки 8020 → 8021. Проверка разбиения: Proposed split — part 1: «Сергей зумбировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @24; punctuation outside parts: «.»
- Строки 8022 → 8023. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8024 → 8025. Внешняя связь: Одна предикация / именное описание
- Строки 8026 → 8027. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8028 → 8029. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-3-asserted — FAIL

Алексей зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8034 → 8035. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8036 → 8037. Внешняя связь: Одна предикация / именное описание
- Строки 8038 → 8039. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-01-3-not — FAIL

Алексей не зумбировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8044 → 8045. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8046 → 8047. Внешняя связь: Отрицание
- Строки 8048 → 8049. Вводящее выражение: начало: Начать с «не» @8
- Строки 8050 → 8051. Вводящее выражение: конец: Закончить после «книгу» @27; выбранные слова «не зумбировал книгу»
- Строки 8052 → 8053. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8054 → 8055. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-3-quoted — FAIL

Мария сказала: «Алексей зумбировал книгу».

Результат шага обрезан в выгрузке.

- Строки 8060 → 8061. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8062 → 8063. Внешняя связь: Пропозициональное содержание
- Строки 8064 → 8065. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 8066 → 8067. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Алексей зумбировал книгу»
- Строки 8068 → 8069. Родительская часть: начало: Начать с «Мария» @0
- Строки 8070 → 8071. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 8072 → 8073. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей зумбировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8074 → 8075. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8076 → 8077. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8078 → 8079. Внешняя связь: Одна предикация / именное описание
- Строки 8080 → 8081. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8082 → 8083. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-01-3-or — FAIL

Алексей зумбировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8088 → 8089. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8090 → 8091. Внешняя связь: Включающее «или»
- Строки 8092 → 8093. Первая часть: начало: Начать с «Алексей» @0
- Строки 8094 → 8095. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Алексей зумбировал книгу»
- Строки 8096 → 8097. Вторая часть: начало: Начать с «Мария» @29
- Строки 8098 → 8099. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 8100 → 8101. Проверка разбиения: Proposed split — part 1: «Алексей зумбировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 8102 → 8103. Грамматическое чтение неизвестного слова: Source «зумбировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8104 → 8105. Внешняя связь: Одна предикация / именное описание
- Строки 8106 → 8107. Именная зависимость: Direct role OBJECT of predicate «зумбировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8108 → 8109. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-0-asserted — FAIL

Иван флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8114 → 8115. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8116 → 8117. Внешняя связь: Одна предикация / именное описание
- Строки 8118 → 8119. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-0-not — FAIL

Иван не флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8124 → 8125. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8126 → 8127. Внешняя связь: Отрицание
- Строки 8128 → 8129. Вводящее выражение: начало: Начать с «не» @5
- Строки 8130 → 8131. Вводящее выражение: конец: Закончить после «флукнул» @15; выбранные слова «не флукнул»
- Строки 8132 → 8133. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8134 → 8135. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-0-quoted — FAIL

Мария сказала: «Иван флукнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8140 → 8141. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8142 → 8143. Внешняя связь: Пропозициональное содержание
- Строки 8144 → 8145. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 8146 → 8147. Вложенное содержание: конец: Закончить после «книгу» @34; выбранные слова «Иван флукнул книгу»
- Строки 8148 → 8149. Родительская часть: начало: Начать с «Мария» @0
- Строки 8150 → 8151. Родительская часть: конец: Закончить после «»» @35; выбранные слова «Мария сказала : « »»
- Строки 8152 → 8153. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван флукнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8154 → 8155. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8156 → 8157. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8158 → 8159. Внешняя связь: Одна предикация / именное описание
- Строки 8160 → 8161. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8162 → 8163. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-0-or — FAIL

Иван флукнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8168 → 8169. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8170 → 8171. Внешняя связь: Включающее «или»
- Строки 8172 → 8173. Первая часть: начало: Начать с «Иван» @0
- Строки 8174 → 8175. Первая часть: конец: Закончить после «книгу» @18; выбранные слова «Иван флукнул книгу»
- Строки 8176 → 8177. Вторая часть: начало: Начать с «Мария» @23
- Строки 8178 → 8179. Вторая часть: конец: Закончить после «уснула» @35; выбранные слова «Мария уснула»
- Строки 8180 → 8181. Проверка разбиения: Proposed split — part 1: «Иван флукнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @19; punctuation outside parts: «.»
- Строки 8182 → 8183. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8184 → 8185. Внешняя связь: Одна предикация / именное описание
- Строки 8186 → 8187. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8188 → 8189. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-1-asserted — FAIL

Пётр флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8194 → 8195. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8196 → 8197. Внешняя связь: Одна предикация / именное описание
- Строки 8198 → 8199. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-1-not — FAIL

Пётр не флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8204 → 8205. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8206 → 8207. Внешняя связь: Отрицание
- Строки 8208 → 8209. Вводящее выражение: начало: Начать с «не» @5
- Строки 8210 → 8211. Вводящее выражение: конец: Закончить после «флукнул» @15; выбранные слова «не флукнул»
- Строки 8212 → 8213. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8214 → 8215. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-1-quoted — FAIL

Мария сказала: «Пётр флукнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8220 → 8221. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8222 → 8223. Внешняя связь: Пропозициональное содержание
- Строки 8224 → 8225. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 8226 → 8227. Вложенное содержание: конец: Закончить после «книгу» @34; выбранные слова «Пётр флукнул книгу»
- Строки 8228 → 8229. Родительская часть: начало: Начать с «Мария» @0
- Строки 8230 → 8231. Родительская часть: конец: Закончить после «»» @35; выбранные слова «Мария сказала : « »»
- Строки 8232 → 8233. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр флукнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8234 → 8235. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8236 → 8237. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8238 → 8239. Внешняя связь: Одна предикация / именное описание
- Строки 8240 → 8241. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8242 → 8243. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-1-or — FAIL

Пётр флукнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8248 → 8249. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8250 → 8251. Внешняя связь: Включающее «или»
- Строки 8252 → 8253. Первая часть: начало: Начать с «Пётр» @0
- Строки 8254 → 8255. Первая часть: конец: Закончить после «книгу» @18; выбранные слова «Пётр флукнул книгу»
- Строки 8256 → 8257. Вторая часть: начало: Начать с «Мария» @23
- Строки 8258 → 8259. Вторая часть: конец: Закончить после «уснула» @35; выбранные слова «Мария уснула»
- Строки 8260 → 8261. Проверка разбиения: Proposed split — part 1: «Пётр флукнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @19; punctuation outside parts: «.»
- Строки 8262 → 8263. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8264 → 8265. Внешняя связь: Одна предикация / именное описание
- Строки 8266 → 8267. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8268 → 8269. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-2-asserted — FAIL

Сергей флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8274 → 8275. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8276 → 8277. Внешняя связь: Одна предикация / именное описание
- Строки 8278 → 8279. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-2-not — FAIL

Сергей не флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8284 → 8285. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8286 → 8287. Внешняя связь: Отрицание
- Строки 8288 → 8289. Вводящее выражение: начало: Начать с «не» @7
- Строки 8290 → 8291. Вводящее выражение: конец: Закончить после «флукнул» @17; выбранные слова «не флукнул»
- Строки 8292 → 8293. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8294 → 8295. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-2-quoted — FAIL

Мария сказала: «Сергей флукнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8300 → 8301. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8302 → 8303. Внешняя связь: Пропозициональное содержание
- Строки 8304 → 8305. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 8306 → 8307. Вложенное содержание: конец: Закончить после «книгу» @36; выбранные слова «Сергей флукнул книгу»
- Строки 8308 → 8309. Родительская часть: начало: Начать с «Мария» @0
- Строки 8310 → 8311. Родительская часть: конец: Закончить после «.» @38; выбранные слова «Мария сказала : « » .»
- Строки 8312 → 8313. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Сергей флукнул книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 8314 → 8315. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8316 → 8317. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8318 → 8319. Внешняя связь: Одна предикация / именное описание
- Строки 8320 → 8321. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8322 → 8323. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-2-or — FAIL

Сергей флукнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8328 → 8329. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8330 → 8331. Внешняя связь: Включающее «или»
- Строки 8332 → 8333. Первая часть: начало: Начать с «Сергей» @0
- Строки 8334 → 8335. Первая часть: конец: Закончить после «книгу» @20; выбранные слова «Сергей флукнул книгу»
- Строки 8336 → 8337. Вторая часть: начало: Начать с «Мария» @25
- Строки 8338 → 8339. Вторая часть: конец: Закончить после «уснула» @37; выбранные слова «Мария уснула»
- Строки 8340 → 8341. Проверка разбиения: Proposed split — part 1: «Сергей флукнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @21; punctuation outside parts: «.»
- Строки 8342 → 8343. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8344 → 8345. Внешняя связь: Одна предикация / именное описание
- Строки 8346 → 8347. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8348 → 8349. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-3-asserted — FAIL

Алексей флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8354 → 8355. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8356 → 8357. Внешняя связь: Одна предикация / именное описание
- Строки 8358 → 8359. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-02-3-not — FAIL

Алексей не флукнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8364 → 8365. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8366 → 8367. Внешняя связь: Отрицание
- Строки 8368 → 8369. Вводящее выражение: начало: Начать с «не» @8
- Строки 8370 → 8371. Вводящее выражение: конец: Закончить после «флукнул» @18; выбранные слова «не флукнул»
- Строки 8372 → 8373. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8374 → 8375. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-3-quoted — FAIL

Мария сказала: «Алексей флукнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8380 → 8381. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8382 → 8383. Внешняя связь: Пропозициональное содержание
- Строки 8384 → 8385. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 8386 → 8387. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Алексей флукнул книгу»
- Строки 8388 → 8389. Родительская часть: начало: Начать с «Мария» @0
- Строки 8390 → 8391. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 8392 → 8393. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей флукнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8394 → 8395. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8396 → 8397. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8398 → 8399. Внешняя связь: Одна предикация / именное описание
- Строки 8400 → 8401. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8402 → 8403. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-02-3-or — FAIL

Алексей флукнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8408 → 8409. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8410 → 8411. Внешняя связь: Включающее «или»
- Строки 8412 → 8413. Первая часть: начало: Начать с «Алексей» @0
- Строки 8414 → 8415. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Алексей флукнул книгу»
- Строки 8416 → 8417. Вторая часть: начало: Начать с «Мария» @26
- Строки 8418 → 8419. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 8420 → 8421. Проверка разбиения: Proposed split — part 1: «Алексей флукнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 8422 → 8423. Грамматическое чтение неизвестного слова: Source «флукнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8424 → 8425. Внешняя связь: Одна предикация / именное описание
- Строки 8426 → 8427. Именная зависимость: Direct role OBJECT of predicate «флукнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8428 → 8429. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-0-asserted — FAIL

Иван квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8434 → 8435. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8436 → 8437. Внешняя связь: Одна предикация / именное описание
- Строки 8438 → 8439. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-0-not — FAIL

Иван не квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8444 → 8445. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8446 → 8447. Внешняя связь: Отрицание
- Строки 8448 → 8449. Вводящее выражение: начало: Начать с «не» @5
- Строки 8450 → 8451. Вводящее выражение: конец: Закончить после «квелировал» @18; выбранные слова «не квелировал»
- Строки 8452 → 8453. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8454 → 8455. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-0-quoted — FAIL

Мария сказала: «Иван квелировал книгу».

Результат шага обрезан в выгрузке.

- Строки 8460 → 8461. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8462 → 8463. Внешняя связь: Одна предикация / именное описание
- Строки 8464 → 8465. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-0-or — FAIL

Иван квелировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8470 → 8471. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8472 → 8473. Внешняя связь: Включающее «или»
- Строки 8474 → 8475. Первая часть: начало: Начать с «Иван» @0
- Строки 8476 → 8477. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Иван квелировал книгу»
- Строки 8478 → 8479. Вторая часть: начало: Начать с «Мария» @26
- Строки 8480 → 8481. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 8482 → 8483. Проверка разбиения: Proposed split — part 1: «Иван квелировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 8484 → 8485. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8486 → 8487. Внешняя связь: Одна предикация / именное описание
- Строки 8488 → 8489. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8490 → 8491. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-1-asserted — FAIL

Пётр квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8496 → 8497. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8498 → 8499. Внешняя связь: Одна предикация / именное описание
- Строки 8500 → 8501. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-1-not — FAIL

Пётр не квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8506 → 8507. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8508 → 8509. Внешняя связь: Отрицание
- Строки 8510 → 8511. Вводящее выражение: начало: Начать с «не» @5
- Строки 8512 → 8513. Вводящее выражение: конец: Закончить после «не» @7; выбранные слова «не»
- Строки 8514 → 8515. Проверка разбиения: Proposed split — part 1: «Пётр квелировал книгу»; outer relation occurrences: «не» @5; punctuation outside parts: «.»
- Строки 8516 → 8517. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8518 → 8519. Внешняя связь: Одна предикация / именное описание
- Строки 8520 → 8521. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-1-quoted — FAIL

Мария сказала: «Пётр квелировал книгу».

Результат шага обрезан в выгрузке.

- Строки 8526 → 8527. Грамматическое чтение неизвестного слова: Source «квелировал»: predicted inflection; lemma: квелировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 8528 → 8529. Внешняя связь: Пропозициональное содержание
- Строки 8530 → 8531. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 8532 → 8533. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Пётр квелировал книгу»
- Строки 8534 → 8535. Родительская часть: начало: Начать с «Мария» @0
- Строки 8536 → 8537. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 8538 → 8539. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр квелировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8540 → 8541. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8542 → 8543. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8544 → 8545. Внешняя связь: Одна предикация / именное описание
- Строки 8546 → 8547. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8548 → 8549. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-1-or — FAIL

Пётр квелировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8554 → 8555. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8556 → 8557. Внешняя связь: Включающее «или»
- Строки 8558 → 8559. Первая часть: начало: Начать с «Пётр» @0
- Строки 8560 → 8561. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Пётр квелировал книгу»
- Строки 8562 → 8563. Вторая часть: начало: Начать с «Мария» @26
- Строки 8564 → 8565. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 8566 → 8567. Проверка разбиения: Proposed split — part 1: «Пётр квелировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 8568 → 8569. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8570 → 8571. Внешняя связь: Одна предикация / именное описание
- Строки 8572 → 8573. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8574 → 8575. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-2-asserted — FAIL

Сергей квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8580 → 8581. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8582 → 8583. Внешняя связь: Одна предикация / именное описание
- Строки 8584 → 8585. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-2-not — FAIL

Сергей не квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8590 → 8591. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8592 → 8593. Внешняя связь: Отрицание
- Строки 8594 → 8595. Вводящее выражение: начало: Начать с «не» @7
- Строки 8596 → 8597. Вводящее выражение: конец: Закончить после «книгу» @26; выбранные слова «не квелировал книгу»
- Строки 8598 → 8599. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8600 → 8601. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-2-quoted — FAIL

Мария сказала: «Сергей квелировал книгу».

Результат шага обрезан в выгрузке.

- Строки 8606 → 8607. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8608 → 8609. Внешняя связь: Одна предикация / именное описание
- Строки 8610 → 8611. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-2-or — FAIL

Сергей квелировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8616 → 8617. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8618 → 8619. Внешняя связь: Включающее «или»
- Строки 8620 → 8621. Первая часть: начало: Начать с «Сергей» @0
- Строки 8622 → 8623. Первая часть: конец: Закончить после «книгу» @23; выбранные слова «Сергей квелировал книгу»
- Строки 8624 → 8625. Вторая часть: начало: Начать с «Мария» @28
- Строки 8626 → 8627. Вторая часть: конец: Закончить после «уснула» @40; выбранные слова «Мария уснула»
- Строки 8628 → 8629. Проверка разбиения: Proposed split — part 1: «Сергей квелировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @24; punctuation outside parts: «.»
- Строки 8630 → 8631. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8632 → 8633. Внешняя связь: Одна предикация / именное описание
- Строки 8634 → 8635. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8636 → 8637. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-3-asserted — FAIL

Алексей квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8642 → 8643. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8644 → 8645. Внешняя связь: Одна предикация / именное описание
- Строки 8646 → 8647. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-03-3-not — FAIL

Алексей не квелировал книгу.

Результат шага обрезан в выгрузке.

- Строки 8652 → 8653. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8654 → 8655. Внешняя связь: Отрицание
- Строки 8656 → 8657. Вводящее выражение: начало: Начать с «не» @8
- Строки 8658 → 8659. Вводящее выражение: конец: Закончить после «квелировал» @21; выбранные слова «не квелировал»
- Строки 8660 → 8661. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8662 → 8663. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-3-quoted — FAIL

Мария сказала: «Алексей квелировал книгу».

Результат шага обрезан в выгрузке.

- Строки 8668 → 8669. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8670 → 8671. Внешняя связь: Пропозициональное содержание
- Строки 8672 → 8673. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 8674 → 8675. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Алексей квелировал книгу»
- Строки 8676 → 8677. Родительская часть: начало: Начать с «Мария» @0
- Строки 8678 → 8679. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 8680 → 8681. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей квелировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8682 → 8683. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8684 → 8685. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8686 → 8687. Внешняя связь: Одна предикация / именное описание
- Строки 8688 → 8689. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8690 → 8691. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-03-3-or — FAIL

Алексей квелировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8696 → 8697. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8698 → 8699. Внешняя связь: Включающее «или»
- Строки 8700 → 8701. Первая часть: начало: Начать с «Алексей» @0
- Строки 8702 → 8703. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Алексей квелировал книгу»
- Строки 8704 → 8705. Вторая часть: начало: Начать с «Мария» @29
- Строки 8706 → 8707. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 8708 → 8709. Проверка разбиения: Proposed split — part 1: «Алексей квелировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 8710 → 8711. Грамматическое чтение неизвестного слова: Source «квелировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8712 → 8713. Внешняя связь: Одна предикация / именное описание
- Строки 8714 → 8715. Именная зависимость: Direct role OBJECT of predicate «квелировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8716 → 8717. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-0-asserted — FAIL

Иван бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8722 → 8723. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8724 → 8725. Внешняя связь: Одна предикация / именное описание
- Строки 8726 → 8727. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-0-not — FAIL

Иван не бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8732 → 8733. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8734 → 8735. Внешняя связь: Отрицание
- Строки 8736 → 8737. Вводящее выражение: начало: Начать с «не» @5
- Строки 8738 → 8739. Вводящее выражение: конец: Закончить после «бронкнул» @16; выбранные слова «не бронкнул»
- Строки 8740 → 8741. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8742 → 8743. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-0-quoted — FAIL

Мария сказала: «Иван бронкнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8748 → 8749. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8750 → 8751. Внешняя связь: Пропозициональное содержание
- Строки 8752 → 8753. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 8754 → 8755. Вложенное содержание: конец: Закончить после «книгу» @35; выбранные слова «Иван бронкнул книгу»
- Строки 8756 → 8757. Родительская часть: начало: Начать с «Мария» @0
- Строки 8758 → 8759. Родительская часть: конец: Закончить после «»» @36; выбранные слова «Мария сказала : « »»
- Строки 8760 → 8761. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван бронкнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 8762 → 8763. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8764 → 8765. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8766 → 8767. Внешняя связь: Одна предикация / именное описание
- Строки 8768 → 8769. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8770 → 8771. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-0-or — FAIL

Иван бронкнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8776 → 8777. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8778 → 8779. Внешняя связь: Включающее «или»
- Строки 8780 → 8781. Первая часть: начало: Начать с «Иван» @0
- Строки 8782 → 8783. Первая часть: конец: Закончить после «книгу» @19; выбранные слова «Иван бронкнул книгу»
- Строки 8784 → 8785. Вторая часть: начало: Начать с «Мария» @24
- Строки 8786 → 8787. Вторая часть: конец: Закончить после «уснула» @36; выбранные слова «Мария уснула»
- Строки 8788 → 8789. Проверка разбиения: Proposed split — part 1: «Иван бронкнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @20; punctuation outside parts: «.»
- Строки 8790 → 8791. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8792 → 8793. Внешняя связь: Одна предикация / именное описание
- Строки 8794 → 8795. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8796 → 8797. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-1-asserted — FAIL

Пётр бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8802 → 8803. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8804 → 8805. Внешняя связь: Одна предикация / именное описание
- Строки 8806 → 8807. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-1-not — FAIL

Пётр не бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8812 → 8813. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8814 → 8815. Внешняя связь: Отрицание
- Строки 8816 → 8817. Вводящее выражение: начало: Начать с «не» @5
- Строки 8818 → 8819. Вводящее выражение: конец: Закончить после «бронкнул» @16; выбранные слова «не бронкнул»
- Строки 8820 → 8821. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8822 → 8823. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-1-quoted — FAIL

Мария сказала: «Пётр бронкнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8828 → 8829. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8830 → 8831. Внешняя связь: Пропозициональное содержание
- Строки 8832 → 8833. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 8834 → 8835. Вложенное содержание: конец: Закончить после «книгу» @35; выбранные слова «Пётр бронкнул книгу»
- Строки 8836 → 8837. Родительская часть: начало: Начать с «Мария» @0
- Строки 8838 → 8839. Родительская часть: конец: Закончить после «.» @37; выбранные слова «Мария сказала : « » .»
- Строки 8840 → 8841. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Пётр бронкнул книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 8842 → 8843. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8844 → 8845. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8846 → 8847. Внешняя связь: Одна предикация / именное описание
- Строки 8848 → 8849. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8850 → 8851. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-1-or — FAIL

Пётр бронкнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8856 → 8857. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8858 → 8859. Внешняя связь: Включающее «или»
- Строки 8860 → 8861. Первая часть: начало: Начать с «Пётр» @0
- Строки 8862 → 8863. Первая часть: конец: Закончить после «книгу» @19; выбранные слова «Пётр бронкнул книгу»
- Строки 8864 → 8865. Вторая часть: начало: Начать с «Мария» @24
- Строки 8866 → 8867. Вторая часть: конец: Закончить после «уснула» @36; выбранные слова «Мария уснула»
- Строки 8868 → 8869. Проверка разбиения: Proposed split — part 1: «Пётр бронкнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @20; punctuation outside parts: «.»
- Строки 8870 → 8871. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8872 → 8873. Внешняя связь: Одна предикация / именное описание
- Строки 8874 → 8875. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8876 → 8877. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-2-asserted — FAIL

Сергей бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8882 → 8883. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8884 → 8885. Внешняя связь: Одна предикация / именное описание
- Строки 8886 → 8887. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-2-not — FAIL

Сергей не бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8892 → 8893. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8894 → 8895. Внешняя связь: Отрицание
- Строки 8896 → 8897. Вводящее выражение: начало: Начать с «не» @7
- Строки 8898 → 8899. Вводящее выражение: конец: Закончить после «бронкнул» @18; выбранные слова «не бронкнул»
- Строки 8900 → 8901. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8902 → 8903. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-2-quoted — FAIL

Мария сказала: «Сергей бронкнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8908 → 8909. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8910 → 8911. Внешняя связь: Пропозициональное содержание
- Строки 8912 → 8913. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 8914 → 8915. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Сергей бронкнул книгу»
- Строки 8916 → 8917. Родительская часть: начало: Начать с «Мария» @0
- Строки 8918 → 8919. Родительская часть: конец: Закончить после «.» @39; выбранные слова «Мария сказала : « » .»
- Строки 8920 → 8921. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Сергей бронкнул книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 8922 → 8923. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 8924 → 8925. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 8926 → 8927. Внешняя связь: Одна предикация / именное описание
- Строки 8928 → 8929. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 8930 → 8931. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-2-or — FAIL

Сергей бронкнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 8936 → 8937. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8938 → 8939. Внешняя связь: Включающее «или»
- Строки 8940 → 8941. Первая часть: начало: Начать с «Сергей» @0
- Строки 8942 → 8943. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Сергей бронкнул книгу»
- Строки 8944 → 8945. Вторая часть: начало: Начать с «Мария» @26
- Строки 8946 → 8947. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 8948 → 8949. Проверка разбиения: Proposed split — part 1: «Сергей бронкнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 8950 → 8951. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8952 → 8953. Внешняя связь: Одна предикация / именное описание
- Строки 8954 → 8955. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 8956 → 8957. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-3-asserted — FAIL

Алексей бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8962 → 8963. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8964 → 8965. Внешняя связь: Одна предикация / именное описание
- Строки 8966 → 8967. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-04-3-not — FAIL

Алексей не бронкнул книгу.

Результат шага обрезан в выгрузке.

- Строки 8972 → 8973. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8974 → 8975. Внешняя связь: Отрицание
- Строки 8976 → 8977. Вводящее выражение: начало: Начать с «не» @8
- Строки 8978 → 8979. Вводящее выражение: конец: Закончить после «бронкнул» @19; выбранные слова «не бронкнул»
- Строки 8980 → 8981. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 8982 → 8983. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-3-quoted — FAIL

Мария сказала: «Алексей бронкнул книгу».

Результат шага обрезан в выгрузке.

- Строки 8988 → 8989. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 8990 → 8991. Внешняя связь: Пропозициональное содержание
- Строки 8992 → 8993. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 8994 → 8995. Вложенное содержание: конец: Закончить после «книгу» @38; выбранные слова «Алексей бронкнул книгу»
- Строки 8996 → 8997. Родительская часть: начало: Начать с «Мария» @0
- Строки 8998 → 8999. Родительская часть: конец: Закончить после «»» @39; выбранные слова «Мария сказала : « »»
- Строки 9000 → 9001. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей бронкнул книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9002 → 9003. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9004 → 9005. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9006 → 9007. Внешняя связь: Одна предикация / именное описание
- Строки 9008 → 9009. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9010 → 9011. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-04-3-or — FAIL

Алексей бронкнул книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9016 → 9017. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9018 → 9019. Внешняя связь: Включающее «или»
- Строки 9020 → 9021. Первая часть: начало: Начать с «Алексей» @0
- Строки 9022 → 9023. Первая часть: конец: Закончить после «книгу» @22; выбранные слова «Алексей бронкнул книгу»
- Строки 9024 → 9025. Вторая часть: начало: Начать с «Мария» @27
- Строки 9026 → 9027. Вторая часть: конец: Закончить после «уснула» @39; выбранные слова «Мария уснула»
- Строки 9028 → 9029. Проверка разбиения: Proposed split — part 1: «Алексей бронкнул книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @23; punctuation outside parts: «.»
- Строки 9030 → 9031. Грамматическое чтение неизвестного слова: Source «бронкнул»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9032 → 9033. Внешняя связь: Одна предикация / именное описание
- Строки 9034 → 9035. Именная зависимость: Direct role OBJECT of predicate «бронкнул» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9036 → 9037. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-05-0-asserted — FAIL

Иван шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9042 → 9043. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9044 → 9045. Внешняя связь: Одна предикация / именное описание
- Строки 9046 → 9047. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-05-0-not — FAIL

Иван не шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9052 → 9053. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9054 → 9055. Внешняя связь: Отрицание
- Строки 9056 → 9057. Вводящее выражение: начало: Начать с «не» @5
- Строки 9058 → 9059. Вводящее выражение: конец: Закончить после «книгу» @24; выбранные слова «не шарпировал книгу»
- Строки 9060 → 9061. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9062 → 9063. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-0-quoted — FAIL

Мария сказала: «Иван шарпировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9068 → 9069. Грамматическое чтение неизвестного слова: Source «шарпировал»: predicted inflection; lemma: шарпировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 9070 → 9071. Внешняя связь: Пропозициональное содержание
- Строки 9072 → 9073. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 9074 → 9075. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Иван шарпировал книгу»
- Строки 9076 → 9077. Родительская часть: начало: Начать с «Мария» @0
- Строки 9078 → 9079. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 9080 → 9081. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван шарпировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9082 → 9083. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9084 → 9085. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9086 → 9087. Внешняя связь: Одна предикация / именное описание
- Строки 9088 → 9089. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9090 → 9091. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-0-or — PASS

Иван шарпировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9096 → 9097. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9098 → 9099. Внешняя связь: Включающее «или»
- Строки 9100 → 9101. Первая часть: начало: Начать с «Иван» @0
- Строки 9102 → 9103. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Иван шарпировал книгу»
- Строки 9104 → 9105. Вторая часть: начало: Начать с «Мария» @26
- Строки 9106 → 9107. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 9108 → 9109. Проверка разбиения: Proposed split — part 1: «Иван шарпировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 9110 → 9111. Грамматическое чтение неизвестного слова: Source «шарпировал»: predicted inflection; lemma: шарпировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: imperfective, transitive; lexical meaning remains unknown
- Строки 9112 → 9113. Внешняя связь: Одна предикация / именное описание
- Строки 9114 → 9115. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9116 → 9117. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.

### OPEN-05-1-asserted — FAIL

Пётр шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9122 → 9123. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9124 → 9125. Внешняя связь: Одна предикация / именное описание
- Строки 9126 → 9127. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-05-1-not — FAIL

Пётр не шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9132 → 9133. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9134 → 9135. Внешняя связь: Отрицание
- Строки 9136 → 9137. Вводящее выражение: начало: Начать с «не» @5
- Строки 9138 → 9139. Вводящее выражение: конец: Закончить после «шарпировал» @18; выбранные слова «не шарпировал»
- Строки 9140 → 9141. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9142 → 9143. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-1-quoted — FAIL

Мария сказала: «Пётр шарпировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9148 → 9149. Грамматическое чтение неизвестного слова: Source «шарпировал»: predicted inflection; lemma: шарпировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 9150 → 9151. Внешняя связь: Пропозициональное содержание
- Строки 9152 → 9153. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 9154 → 9155. Вложенное содержание: конец: Закончить после «книгу» @37; выбранные слова «Пётр шарпировал книгу»
- Строки 9156 → 9157. Родительская часть: начало: Начать с «Мария» @0
- Строки 9158 → 9159. Родительская часть: конец: Закончить после «»» @38; выбранные слова «Мария сказала : « »»
- Строки 9160 → 9161. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр шарпировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9162 → 9163. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9164 → 9165. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9166 → 9167. Внешняя связь: Одна предикация / именное описание
- Строки 9168 → 9169. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9170 → 9171. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-1-or — FAIL

Пётр шарпировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9176 → 9177. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9178 → 9179. Внешняя связь: Включающее «или»
- Строки 9180 → 9181. Первая часть: начало: Начать с «Пётр» @0
- Строки 9182 → 9183. Первая часть: конец: Закончить после «книгу» @21; выбранные слова «Пётр шарпировал книгу»
- Строки 9184 → 9185. Вторая часть: начало: Начать с «Мария» @26
- Строки 9186 → 9187. Вторая часть: конец: Закончить после «уснула» @38; выбранные слова «Мария уснула»
- Строки 9188 → 9189. Проверка разбиения: Proposed split — part 1: «Пётр шарпировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @22; punctuation outside parts: «.»
- Строки 9190 → 9191. Грамматическое чтение неизвестного слова: The target phrase is "Пётр шарпировал книгу".
1.  **Syntactic Role**: "Пётр" is the subject (Nominative). "книгу" is the direct object (Accusative). The word "шарпировал" connects the subject and the object, functioning as the predicate. This indicates it is a verb.
2.  **Morphology**: The ending "-л" in Russian typically marks the past tense, 3rd person singular, masculine gender.
3.  **Transitivity**: Since there is a direct object ("книгу"), the verb must be transitive.
4.  **Aspect**: The instruction states "Do not infer a known lexical meaning from a predicted lemma." However, we must choose a grammatical reading. The options distinguish between imperfective and perfective. Without knowing the specific lexical aspect of the unknown word "шарпировать", we look at the options.
    *   Option 1 is a generic VERB with unknown features.
    *   Option 4 is imperfective, intransitive. (Incorrect, it has an object).
    *   Option 5 is perfective, transitive.
    *   Option 6 is imperfective, transitive.
    *   Options 7 and 8 are nouns. (Incorrect).
    *   Option 2 is an infinitive. (Incorrect, it's conjugated).
    *   Option 3 is an adverb. (Incorrect).

The choice is between Option 1 (generic), Option 5 (perfective, transitive), and Option 6 (imperfective, transitive).
The prompt says: "Choose the grammatical reading... If only the function is clear, choose a reading with unknown lemma. Do not infer a known lexical meaning from a predicted lemma."
However, options 5 and 6 provide specific aspectual features. Usually, in these tasks, if the aspect cannot be determined from context (no context indicating completion vs process), and the lemma is unknown, we might default to the most specific grammatical description that fits the morphology and syntax, or the generic one if aspect is truly ambiguous.
Let's re-read carefully: "Predicted inflections describe possible forms... Use agreement and sentence meaning to distinguish them."
The sentence "Пётр шарпировал книгу" is a simple past tense statement. It doesn't inherently force perfective or imperfective without more context (e.g., "he was sharpening" vs "he sharpened"). However, the form "-л" is standard for both.
Option 1 says "lemma and all other unsupported features remain unknown". This is the safest bet if we cannot distinguish aspect.
But let's look at the options again. Options 4, 5, 6 are "predicted inflection" with specific lemmas. The prompt says "Do not infer a known lexical meaning from a predicted lemma." This implies we shouldn't assume the word means "to sharpen" just because the lemma is "шарпировать". But we must pick a structure.
If the aspect is not specified in the source or context, can we pick 5 or 6?
Usually, if the aspect is not clear, Option 1 is the correct "unknown" reading.
However, often in these specific NLP tasks, if a verb takes a direct object, it is transitive. The aspect is the only differentiator between 5 and 6.
Is there a clue? "шарпировал" sounds like a made-up word or a very rare one.
Let's look at the "Current parent requirements": "Already handled outside the target... Select another such relation only if the target words themselves express it." This refers to the logical connective "или" (or) in the surrounding text, which is outside the target. So we ignore that.

Let's evaluate Option 1 vs 5/6.
Option 1: VERB; cases=[]; lemma and all other unsupported features remain unknown.
Option 5: ... features: perfective, transitive ...
Option 6: ... features: imperfective, transitive ...

If the word is truly unknown, we cannot know if it is perfective or imperfective. Therefore, asserting it is perfective (5) or imperfective (6) is an inference not supported by the text. Option 1 explicitly states that unsupported features remain unknown. This aligns with the instruction "If only the function is clear, choose a reading with unknown lemma." The function (verb, transitive) is clear, but the aspect is not.
Wait, Option 1 does not specify transitivity. It just says "VERB".
Options 5 and 6 specify "transitive".
Is transitivity "supported"?
- Строки 9192 → 9193. Внешняя связь: Одна предикация / именное описание
- Строки 9194 → 9195. Состав и чтение конструкции: Ни один показанный вариант не подошёл (0)
- Строки 9196 → 9197. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-2-asserted — FAIL

Сергей шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9202 → 9203. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9204 → 9205. Внешняя связь: Одна предикация / именное описание
- Строки 9206 → 9207. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-05-2-not — FAIL

Сергей не шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9212 → 9213. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9214 → 9215. Внешняя связь: Отрицание
- Строки 9216 → 9217. Вводящее выражение: начало: Начать с «не» @7
- Строки 9218 → 9219. Вводящее выражение: конец: Закончить после «шарпировал» @20; выбранные слова «не шарпировал»
- Строки 9220 → 9221. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9222 → 9223. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-2-quoted — FAIL

Мария сказала: «Сергей шарпировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9228 → 9229. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9230 → 9231. Внешняя связь: Пропозициональное содержание
- Строки 9232 → 9233. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 9234 → 9235. Вложенное содержание: конец: Закончить после «книгу» @39; выбранные слова «Сергей шарпировал книгу»
- Строки 9236 → 9237. Родительская часть: начало: Начать с «Мария» @0
- Строки 9238 → 9239. Родительская часть: конец: Закончить после «»» @40; выбранные слова «Мария сказала : « »»
- Строки 9240 → 9241. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей шарпировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9242 → 9243. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9244 → 9245. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9246 → 9247. Внешняя связь: Одна предикация / именное описание
- Строки 9248 → 9249. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9250 → 9251. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-2-or — PASS

Сергей шарпировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9256 → 9257. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9258 → 9259. Внешняя связь: Включающее «или»
- Строки 9260 → 9261. Первая часть: начало: Начать с «Сергей» @0
- Строки 9262 → 9263. Первая часть: конец: Закончить после «книгу» @23; выбранные слова «Сергей шарпировал книгу»
- Строки 9264 → 9265. Вторая часть: начало: Начать с «Мария» @28
- Строки 9266 → 9267. Вторая часть: конец: Закончить после «уснула» @40; выбранные слова «Мария уснула»
- Строки 9268 → 9269. Проверка разбиения: Proposed split — part 1: «Сергей шарпировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @24; punctuation outside parts: «.»
- Строки 9270 → 9271. Грамматическое чтение неизвестного слова: Source «шарпировал»: predicted inflection; lemma: шарпировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: imperfective, transitive; lexical meaning remains unknown
- Строки 9272 → 9273. Внешняя связь: Одна предикация / именное описание
- Строки 9274 → 9275. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9276 → 9277. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.

### OPEN-05-3-asserted — FAIL

Алексей шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9282 → 9283. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9284 → 9285. Внешняя связь: Одна предикация / именное описание
- Строки 9286 → 9287. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-05-3-not — FAIL

Алексей не шарпировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9292 → 9293. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9294 → 9295. Внешняя связь: Отрицание
- Строки 9296 → 9297. Вводящее выражение: начало: Начать с «не» @8
- Строки 9298 → 9299. Вводящее выражение: конец: Закончить после «шарпировал» @21; выбранные слова «не шарпировал»
- Строки 9300 → 9301. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9302 → 9303. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-3-quoted — FAIL

Мария сказала: «Алексей шарпировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9308 → 9309. Грамматическое чтение неизвестного слова: Source «шарпировал»: predicted inflection; lemma: шарпировать; pos: conjugated verb; number: singular; gender: masculine; tense: past; mood: indicative; features: perfective, transitive; lexical meaning remains unknown
- Строки 9310 → 9311. Внешняя связь: Пропозициональное содержание
- Строки 9312 → 9313. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 9314 → 9315. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Алексей шарпировал книгу»
- Строки 9316 → 9317. Родительская часть: начало: Начать с «Мария» @0
- Строки 9318 → 9319. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 9320 → 9321. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей шарпировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9322 → 9323. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9324 → 9325. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9326 → 9327. Внешняя связь: Одна предикация / именное описание
- Строки 9328 → 9329. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9330 → 9331. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-05-3-or — FAIL

Алексей шарпировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9336 → 9337. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9338 → 9339. Внешняя связь: Включающее «или»
- Строки 9340 → 9341. Первая часть: начало: Начать с «Алексей» @0
- Строки 9342 → 9343. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Алексей шарпировал книгу»
- Строки 9344 → 9345. Вторая часть: начало: Начать с «Мария» @29
- Строки 9346 → 9347. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 9348 → 9349. Проверка разбиения: Proposed split — part 1: «Алексей шарпировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 9350 → 9351. Грамматическое чтение неизвестного слова: Source «шарпировал»: VERB; cases=[]; lemma and all other unsupported features remain unknown
- Строки 9352 → 9353. Внешняя связь: Одна предикация / именное описание
- Строки 9354 → 9355. Именная зависимость: Direct role OBJECT of predicate «шарпировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9356 → 9357. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: OOV_KEEP_AS_IS.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.
**Различаются только метки OPEN-предикатов; остальные записанные поля формулы совпадают.**

### OPEN-06-0-asserted — PASS

Иван переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9362 → 9363. Внешняя связь: Одна предикация / именное описание
- Строки 9364 → 9365. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### OPEN-06-0-not — FAIL

Иван не переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9370 → 9371. Внешняя связь: Отрицание
- Строки 9372 → 9373. Вводящее выражение: начало: Начать с «не» @5
- Строки 9374 → 9375. Вводящее выражение: конец: Закончить после «переадресовал» @21; выбранные слова «не переадресовал»
- Строки 9376 → 9377. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9378 → 9379. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-0-quoted — FAIL

Мария сказала: «Иван переадресовал книгу».

Результат шага обрезан в выгрузке.

- Строки 9384 → 9385. Внешняя связь: Пропозициональное содержание
- Строки 9386 → 9387. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 9388 → 9389. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Иван переадресовал книгу»
- Строки 9390 → 9391. Родительская часть: начало: Начать с «Мария» @0
- Строки 9392 → 9393. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 9394 → 9395. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван переадресовал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9396 → 9397. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9398 → 9399. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9400 → 9401. Внешняя связь: Одна предикация / именное описание
- Строки 9402 → 9403. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9404 → 9405. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-0-or — PASS

Иван переадресовал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9410 → 9411. Внешняя связь: Включающее «или»
- Строки 9412 → 9413. Первая часть: начало: Начать с «Иван» @0
- Строки 9414 → 9415. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Иван переадресовал книгу»
- Строки 9416 → 9417. Вторая часть: начало: Начать с «Мария» @29
- Строки 9418 → 9419. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 9420 → 9421. Проверка разбиения: Proposed split — part 1: «Иван переадресовал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 9422 → 9423. Внешняя связь: Одна предикация / именное описание
- Строки 9424 → 9425. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9426 → 9427. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-06-1-asserted — PASS

Пётр переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9432 → 9433. Внешняя связь: Одна предикация / именное описание
- Строки 9434 → 9435. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### OPEN-06-1-not — FAIL

Пётр не переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9440 → 9441. Внешняя связь: Отрицание
- Строки 9442 → 9443. Вводящее выражение: начало: Начать с «не» @5
- Строки 9444 → 9445. Вводящее выражение: конец: Закончить после «переадресовал» @21; выбранные слова «не переадресовал»
- Строки 9446 → 9447. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9448 → 9449. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-1-quoted — FAIL

Мария сказала: «Пётр переадресовал книгу».

Результат шага обрезан в выгрузке.

- Строки 9454 → 9455. Внешняя связь: Пропозициональное содержание
- Строки 9456 → 9457. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 9458 → 9459. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Пётр переадресовал книгу»
- Строки 9460 → 9461. Родительская часть: начало: Начать с «Мария» @0
- Строки 9462 → 9463. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 9464 → 9465. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр переадресовал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9466 → 9467. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9468 → 9469. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9470 → 9471. Внешняя связь: Одна предикация / именное описание
- Строки 9472 → 9473. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9474 → 9475. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-1-or — PASS

Пётр переадресовал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9480 → 9481. Внешняя связь: Включающее «или»
- Строки 9482 → 9483. Первая часть: начало: Начать с «Пётр» @0
- Строки 9484 → 9485. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Пётр переадресовал книгу»
- Строки 9486 → 9487. Вторая часть: начало: Начать с «Мария» @29
- Строки 9488 → 9489. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 9490 → 9491. Проверка разбиения: Proposed split — part 1: «Пётр переадресовал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 9492 → 9493. Внешняя связь: Одна предикация / именное описание
- Строки 9494 → 9495. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9496 → 9497. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-06-2-asserted — PASS

Сергей переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9502 → 9503. Внешняя связь: Одна предикация / именное описание
- Строки 9504 → 9505. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### OPEN-06-2-not — FAIL

Сергей не переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9510 → 9511. Внешняя связь: Отрицание
- Строки 9512 → 9513. Вводящее выражение: начало: Начать с «не» @7
- Строки 9514 → 9515. Вводящее выражение: конец: Закончить после «переадресовал» @23; выбранные слова «не переадресовал»
- Строки 9516 → 9517. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9518 → 9519. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-2-quoted — FAIL

Мария сказала: «Сергей переадресовал книгу».

Результат шага обрезан в выгрузке.

- Строки 9524 → 9525. Внешняя связь: Пропозициональное содержание
- Строки 9526 → 9527. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 9528 → 9529. Вложенное содержание: конец: Закончить после «книгу» @42; выбранные слова «Сергей переадресовал книгу»
- Строки 9530 → 9531. Родительская часть: начало: Начать с «Мария» @0
- Строки 9532 → 9533. Родительская часть: конец: Закончить после «»» @43; выбранные слова «Мария сказала : « »»
- Строки 9534 → 9535. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей переадресовал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9536 → 9537. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9538 → 9539. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9540 → 9541. Внешняя связь: Одна предикация / именное описание
- Строки 9542 → 9543. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9544 → 9545. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-2-or — PASS

Сергей переадресовал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9550 → 9551. Внешняя связь: Включающее «или»
- Строки 9552 → 9553. Первая часть: начало: Начать с «Сергей» @0
- Строки 9554 → 9555. Первая часть: конец: Закончить после «книгу» @26; выбранные слова «Сергей переадресовал книгу»
- Строки 9556 → 9557. Вторая часть: начало: Начать с «Мария» @31
- Строки 9558 → 9559. Вторая часть: конец: Закончить после «уснула» @43; выбранные слова «Мария уснула»
- Строки 9560 → 9561. Проверка разбиения: Proposed split — part 1: «Сергей переадресовал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @27; punctuation outside parts: «.»
- Строки 9562 → 9563. Внешняя связь: Одна предикация / именное описание
- Строки 9564 → 9565. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9566 → 9567. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-06-3-asserted — PASS

Алексей переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9572 → 9573. Внешняя связь: Одна предикация / именное описание
- Строки 9574 → 9575. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate

Первая записанная диагностика: нет.

### OPEN-06-3-not — FAIL

Алексей не переадресовал книгу.

Результат шага обрезан в выгрузке.

- Строки 9580 → 9581. Внешняя связь: Отрицание
- Строки 9582 → 9583. Вводящее выражение: начало: Начать с «не» @8
- Строки 9584 → 9585. Вводящее выражение: конец: Закончить после «переадресовал» @24; выбранные слова «не переадресовал»
- Строки 9586 → 9587. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9588 → 9589. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-3-quoted — FAIL

Мария сказала: «Алексей переадресовал книгу».

Результат шага обрезан в выгрузке.

- Строки 9594 → 9595. Внешняя связь: Пропозициональное содержание
- Строки 9596 → 9597. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 9598 → 9599. Вложенное содержание: конец: Закончить после «книгу» @43; выбранные слова «Алексей переадресовал книгу»
- Строки 9600 → 9601. Родительская часть: начало: Начать с «Мария» @0
- Строки 9602 → 9603. Родительская часть: конец: Закончить после «.» @45; выбранные слова «Мария сказала : « » .»
- Строки 9604 → 9605. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « » .»; content filling that slot: «Алексей переадресовал книгу»; outer relation occurrences: none; punctuation outside parts: «»
- Строки 9606 → 9607. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9608 → 9609. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9610 → 9611. Внешняя связь: Одна предикация / именное описание
- Строки 9612 → 9613. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9614 → 9615. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-06-3-or — PASS

Алексей переадресовал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9620 → 9621. Внешняя связь: Включающее «или»
- Строки 9622 → 9623. Первая часть: начало: Начать с «Алексей» @0
- Строки 9624 → 9625. Первая часть: конец: Закончить после «книгу» @27; выбранные слова «Алексей переадресовал книгу»
- Строки 9626 → 9627. Вторая часть: начало: Начать с «Мария» @32
- Строки 9628 → 9629. Вторая часть: конец: Закончить после «уснула» @44; выбранные слова «Мария уснула»
- Строки 9630 → 9631. Проверка разбиения: Proposed split — part 1: «Алексей переадресовал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @28; punctuation outside parts: «.»
- Строки 9632 → 9633. Внешняя связь: Одна предикация / именное описание
- Строки 9634 → 9635. Именная зависимость: Direct role OBJECT of predicate «переадресовал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9636 → 9637. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-07-0-asserted — PASS

Иван траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9642 → 9643. Внешняя связь: Одна предикация / именное описание
- Строки 9644 → 9645. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9646 → 9647. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Иван, OBJECT=книгу

Первая записанная диагностика: нет.

### OPEN-07-0-not — FAIL

Иван не траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9652 → 9653. Внешняя связь: Отрицание
- Строки 9654 → 9655. Вводящее выражение: начало: Начать с «не» @5
- Строки 9656 → 9657. Вводящее выражение: конец: Закончить после «траверсировал» @21; выбранные слова «не траверсировал»
- Строки 9658 → 9659. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9660 → 9661. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-0-quoted — FAIL

Мария сказала: «Иван траверсировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9666 → 9667. Внешняя связь: Пропозициональное содержание
- Строки 9668 → 9669. Вложенное содержание: начало: Начать с «Иван» @16
- Строки 9670 → 9671. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Иван траверсировал книгу»
- Строки 9672 → 9673. Родительская часть: начало: Начать с «Мария» @0
- Строки 9674 → 9675. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 9676 → 9677. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Иван траверсировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9678 → 9679. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9680 → 9681. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9682 → 9683. Внешняя связь: Одна предикация / именное описание
- Строки 9684 → 9685. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9686 → 9687. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-0-or — PASS

Иван траверсировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9692 → 9693. Внешняя связь: Включающее «или»
- Строки 9694 → 9695. Первая часть: начало: Начать с «Иван» @0
- Строки 9696 → 9697. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Иван траверсировал книгу»
- Строки 9698 → 9699. Вторая часть: начало: Начать с «Мария» @29
- Строки 9700 → 9701. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 9702 → 9703. Проверка разбиения: Proposed split — part 1: «Иван траверсировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 9704 → 9705. Внешняя связь: Одна предикация / именное описание
- Строки 9706 → 9707. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9708 → 9709. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Иван, OBJECT=книгу
- Строки 9710 → 9711. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-07-1-asserted — PASS

Пётр траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9716 → 9717. Внешняя связь: Одна предикация / именное описание
- Строки 9718 → 9719. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9720 → 9721. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Пётр, OBJECT=книгу

Первая записанная диагностика: нет.

### OPEN-07-1-not — FAIL

Пётр не траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9726 → 9727. Внешняя связь: Отрицание
- Строки 9728 → 9729. Вводящее выражение: начало: Начать с «не» @5
- Строки 9730 → 9731. Вводящее выражение: конец: Закончить после «траверсировал» @21; выбранные слова «не траверсировал»
- Строки 9732 → 9733. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9734 → 9735. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-1-quoted — FAIL

Мария сказала: «Пётр траверсировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9740 → 9741. Внешняя связь: Пропозициональное содержание
- Строки 9742 → 9743. Вложенное содержание: начало: Начать с «Пётр» @16
- Строки 9744 → 9745. Вложенное содержание: конец: Закончить после «книгу» @40; выбранные слова «Пётр траверсировал книгу»
- Строки 9746 → 9747. Родительская часть: начало: Начать с «Мария» @0
- Строки 9748 → 9749. Родительская часть: конец: Закончить после «»» @41; выбранные слова «Мария сказала : « »»
- Строки 9750 → 9751. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Пётр траверсировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9752 → 9753. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9754 → 9755. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9756 → 9757. Внешняя связь: Одна предикация / именное описание
- Строки 9758 → 9759. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9760 → 9761. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-1-or — PASS

Пётр траверсировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9766 → 9767. Внешняя связь: Включающее «или»
- Строки 9768 → 9769. Первая часть: начало: Начать с «Пётр» @0
- Строки 9770 → 9771. Первая часть: конец: Закончить после «книгу» @24; выбранные слова «Пётр траверсировал книгу»
- Строки 9772 → 9773. Вторая часть: начало: Начать с «Мария» @29
- Строки 9774 → 9775. Вторая часть: конец: Закончить после «уснула» @41; выбранные слова «Мария уснула»
- Строки 9776 → 9777. Проверка разбиения: Proposed split — part 1: «Пётр траверсировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @25; punctuation outside parts: «.»
- Строки 9778 → 9779. Внешняя связь: Одна предикация / именное описание
- Строки 9780 → 9781. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9782 → 9783. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Пётр, OBJECT=книгу
- Строки 9784 → 9785. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-07-2-asserted — PASS

Сергей траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9790 → 9791. Внешняя связь: Одна предикация / именное описание
- Строки 9792 → 9793. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9794 → 9795. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Сергей, OBJECT=книгу

Первая записанная диагностика: нет.

### OPEN-07-2-not — FAIL

Сергей не траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9800 → 9801. Внешняя связь: Отрицание
- Строки 9802 → 9803. Вводящее выражение: начало: Начать с «не» @7
- Строки 9804 → 9805. Вводящее выражение: конец: Закончить после «траверсировал» @23; выбранные слова «не траверсировал»
- Строки 9806 → 9807. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9808 → 9809. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-2-quoted — FAIL

Мария сказала: «Сергей траверсировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9814 → 9815. Внешняя связь: Пропозициональное содержание
- Строки 9816 → 9817. Вложенное содержание: начало: Начать с «Сергей» @16
- Строки 9818 → 9819. Вложенное содержание: конец: Закончить после «книгу» @42; выбранные слова «Сергей траверсировал книгу»
- Строки 9820 → 9821. Родительская часть: начало: Начать с «Мария» @0
- Строки 9822 → 9823. Родительская часть: конец: Закончить после «»» @43; выбранные слова «Мария сказала : « »»
- Строки 9824 → 9825. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Сергей траверсировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9826 → 9827. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9828 → 9829. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9830 → 9831. Внешняя связь: Одна предикация / именное описание
- Строки 9832 → 9833. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9834 → 9835. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-2-or — PASS

Сергей траверсировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9840 → 9841. Внешняя связь: Включающее «или»
- Строки 9842 → 9843. Первая часть: начало: Начать с «Сергей» @0
- Строки 9844 → 9845. Первая часть: конец: Закончить после «книгу» @26; выбранные слова «Сергей траверсировал книгу»
- Строки 9846 → 9847. Вторая часть: начало: Начать с «Мария» @31
- Строки 9848 → 9849. Вторая часть: конец: Закончить после «уснула» @43; выбранные слова «Мария уснула»
- Строки 9850 → 9851. Проверка разбиения: Proposed split — part 1: «Сергей траверсировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @27; punctuation outside parts: «.»
- Строки 9852 → 9853. Внешняя связь: Одна предикация / именное описание
- Строки 9854 → 9855. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9856 → 9857. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Сергей, OBJECT=книгу
- Строки 9858 → 9859. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### OPEN-07-3-asserted — PASS

Алексей траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9864 → 9865. Внешняя связь: Одна предикация / именное описание
- Строки 9866 → 9867. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9868 → 9869. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Алексей, OBJECT=книгу

Первая записанная диагностика: нет.

### OPEN-07-3-not — FAIL

Алексей не траверсировал книгу.

Результат шага обрезан в выгрузке.

- Строки 9874 → 9875. Внешняя связь: Отрицание
- Строки 9876 → 9877. Вводящее выражение: начало: Начать с «не» @8
- Строки 9878 → 9879. Вводящее выражение: конец: Закончить после «траверсировал» @24; выбранные слова «не траверсировал»
- Строки 9880 → 9881. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9882 → 9883. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-3-quoted — FAIL

Мария сказала: «Алексей траверсировал книгу».

Результат шага обрезан в выгрузке.

- Строки 9888 → 9889. Внешняя связь: Пропозициональное содержание
- Строки 9890 → 9891. Вложенное содержание: начало: Начать с «Алексей» @16
- Строки 9892 → 9893. Вложенное содержание: конец: Закончить после «книгу» @43; выбранные слова «Алексей траверсировал книгу»
- Строки 9894 → 9895. Родительская часть: начало: Начать с «Мария» @0
- Строки 9896 → 9897. Родительская часть: конец: Закончить после «»» @44; выбранные слова «Мария сказала : « »»
- Строки 9898 → 9899. Проверка разбиения: Proposed split — parent clause with a content slot: «Мария сказала : « »»; content filling that slot: «Алексей траверсировал книгу»; outer relation occurrences: none; punctuation outside parts: «.»
- Строки 9900 → 9901. Предикат — владелец содержания: Content belongs to predicate «сказала» @6
- Строки 9902 → 9903. Роль и статус вложенного содержания: OBJECT of «сказала»; attitude=QUOTED; content specifying what the parent predicate is about, including an action whose phase is described (QUOTED=reported, EMBEDDED=mental content, HYPOTHETICAL=intended/possible, UNKNOWN=unspecified; none asserts the child)
- Строки 9904 → 9905. Внешняя связь: Одна предикация / именное описание
- Строки 9906 → 9907. Пересмотр разбора: No different reading is supported; leave the parse unresolved
- Строки 9908 → 9909. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: COMPONENT_SCOPE_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/open/capabilities`, `/generation/gold_patterns`.

### OPEN-07-3-or — PASS

Алексей траверсировал книгу или Мария уснула.

Результат шага обрезан в выгрузке.

- Строки 9914 → 9915. Внешняя связь: Включающее «или»
- Строки 9916 → 9917. Первая часть: начало: Начать с «Алексей» @0
- Строки 9918 → 9919. Первая часть: конец: Закончить после «книгу» @27; выбранные слова «Алексей траверсировал книгу»
- Строки 9920 → 9921. Вторая часть: начало: Начать с «Мария» @32
- Строки 9922 → 9923. Вторая часть: конец: Закончить после «уснула» @44; выбранные слова «Мария уснула»
- Строки 9924 → 9925. Проверка разбиения: Proposed split — part 1: «Алексей траверсировал книгу»; part 2: «Мария уснула»; outer relation occurrences: «или» @28; punctuation outside parts: «.»
- Строки 9926 → 9927. Внешняя связь: Одна предикация / именное описание
- Строки 9928 → 9929. Именная зависимость: Direct role OBJECT of predicate «траверсировал» (direct object or content of the predicate); lemma: книга; pos: noun; cases: accusative; number: singular; gender: feminine; features: inanimate
- Строки 9930 → 9931. Состав и чтение конструкции: траверсировать [VERB]; SUBJECT=Алексей, OBJECT=книгу
- Строки 9932 → 9933. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LEXICAL-SCOPE-начать — PASS

Иван начал читать книгу.

Результат шага обрезан в выгрузке.

- Строки 9938 → 9939. Внешняя связь: Одна предикация / именное описание
- Строки 9940 → 9941. Состав и чтение конструкции: Infinitive area «читать книгу.»; remaining parent «Иван начал»
- Строки 9942 → 9943. Внешняя связь: Одна предикация / именное описание
- Строки 9944 → 9945. Состав и чтение конструкции: «читать» fills OBJECT of «начал» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 9946 → 9947. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LEXICAL-SCOPE-перестать — PASS

Иван перестал читать книгу.

Результат шага обрезан в выгрузке.

- Строки 9952 → 9953. Внешняя связь: Одна предикация / именное описание
- Строки 9954 → 9955. Состав и чтение конструкции: Infinitive area «читать книгу.»; remaining parent «Иван перестал»
- Строки 9956 → 9957. Внешняя связь: Одна предикация / именное описание
- Строки 9958 → 9959. Состав и чтение конструкции: «читать» fills OBJECT of «перестал» (content specifying what the parent predicate is about, including an action whose phase is described); its omitted subject is the SAME SUBJECT «Иван» of that predicate; attitude=UNKNOWN; does not assert that the infinitive event occurred
- Строки 9960 → 9961. Внешняя связь: Одна предикация / именное описание

Первая записанная диагностика: нет.

### LEXICAL-SCOPE-снова-мочь — FAIL

Иван снова смог читать книгу.

Результат шага обрезан в выгрузке.

- Строки 9966 → 9967. Внешняя связь: Возможность
- Строки 9968 → 9969. Вводящее выражение: начало: Начать с «смог» @11
- Строки 9970 → 9971. Вводящее выражение: конец: Закончить после «смог» @15; выбранные слова «смог»
- Строки 9972 → 9973. Проверка разбиения: Ни один показанный вариант не подошёл (0)
- Строки 9974 → 9975. Пересмотр разбора: No different reading is supported; leave the parse unresolved

Первая записанная диагностика: STRUCTURAL_TASK_UNRESOLVED.
Несовпавшие проверки: `/assertions/ah`, `/assertions/ir`, `/assertions/journal`, `/generation/gold_patterns`.

## Незавершённые случаи

Нет.
