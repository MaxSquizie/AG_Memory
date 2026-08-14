# LLM roles

Один `LocalLLMProcessBackend` загружает одну локальную модель и обслуживает две роли без скрытой chat history (`llm.history_messages = 0`).

## Perception: adaptive_v2

`adaptive_v2` специально рассчитан на слабую локальную LLM, которая ничего не знает об АГ-памяти.
Модель не получает UID, `T/N/L`, C/P/H, правила интеграции, граф памяти или язык сериализации.

Большинство решений — выбор **одного числа из явно показанного `OPTIONS`**:

```text
ACT TYPE          -> 0/1/2/3
PREDICATE START   -> номер токена / 0 implicit / -1 none
PREDICATE END     -> один из явно показанных end-token
NEGATION          -> 0/1, причём очевидное отсутствие отрицания решается Python без LLM
ACTANT START      -> один из доступных token numbers / 0 none
ACTANT END        -> один из допустимых end-token; варианты показывают готовую source-фразу
ROLE FAMILY       -> 1/2/3 по обычным человеческим описаниям
EXACT ROLE        -> число из короткого списка обычных описаний
QUERY MODE        -> 1 yes/no, 2 missing value
```

Канонические `ActantRole` модель выбирать и знать не обязана: numeric option переводится в enum Python-кодом.
Единственный неизбежно open-text шаг — `predicate_symbol`: неизвестному русскому предикату нужно дать короткое английское semantic имя для predicate `S`, используемого `T`. Ответ жёстко валидируется как lowercase ASCII/snake_case; несколько частых английских irregular forms (`is/are/was -> be`, `has/had -> have`) нормализуются детерминированно.

Python выполняет tokenization, candidate enumeration, exclusions, span assembly, role mapping, validation, evidence offsets и сборку `PerceptionResult`. Retry одного probe выполняется с тем же чистым input; предыдущий ошибочный ответ модели ей не показывается.

Русский source text сохраняется в `surface`, `mention`, `evidence` и lexical `S` сенсорного слоя. Семантический predicate `S`, на который ссылается `T`, нормализуется в английский symbol (`be`, `have`, `move_to`, ...). Русская surface-форма автоматически в этот predicate `S` не подмешивается.

## Agent

`agent.txt` получает только deterministic `AgentContext` и генерирует естественный ответ. Собственный ответ по умолчанию записывается в `H` как пережитое событие без второго LLM Perception прохода.
