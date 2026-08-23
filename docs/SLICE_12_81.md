# v0.12.81 — semantic-boundary reliability before M2

Основание: live acceptance на `qwen3.8-27b-nvfp4-q5k-no-mtp` после отключения thinking дал `Runtime OK 200/200`, `Semantic PASS 169/200`, `FAIL 31`. Аудит показал, что большая часть красных кейсов возникала не из-за одной общей «слабости модели», а из-за нескольких архитектурных границ, где runtime семантика использовалась слишком широко.

## Исправления

1. **Embedded content != inference request.** `SemanticGoalCompiler` компилирует embedded propositions только как descendants явного `QUERY/COMMAND` root. Обычное assertion с embedded content не создаёт публичный `QueryExecution`.

2. **Pronoun morphology remains a candidate lattice.** Для закрытого класса third-person/anaphoric pronouns не применяется open-class probability floor. Косвенная masculine third-person paradigm также допускает neuter antecedent и не использует animacy как жёсткий identity constraint. После этого действуют прежние deterministic same-role / discourse rules; отсутствие структурного основания по-прежнему сохраняет ambiguity.

3. **Structural attachment is decided by grammar before plausibility.** Если post-nominal PP имеет event-owner и nominal-owner и его complement морфологически instrumental, ambiguity не отдаётся LLM на «правдоподобный» выбор: создаётся structural clarification. Неинструментальные PP продолжают старый bounded attachment path.

4. **Counted nominal normalization.** После semantic role classification leading `NUMR/numeric + nominal` разделяется на semantic participant и `AMOUNT`. `DURATION` исключён из splitting и сохраняет цельное значение.

5. **Selected T constrains query fillers.** Если known query filler оказался ролью вне выбранного existing T, deterministic layer вычисляет только свободные роли этого T (кроме WH-requested role). При нескольких вариантах модель решает один UID-free bounded role choice. Остаточный out-of-schema query filler не расширяет T: QueryGoalBuilder должен fail closed.

6. **Nominal predication is not pairwise taxonomy.** Parser помечает noun-headed copular frames как `NOMINAL_PREDICATION`; GoalSemanticService не применяет к таким frame общий SUBJECT/OBJECT `IS-A` classifier. Это исключает ложные связи вида `X IS-A <complement of naming/property relation>`. Unary nominal class facts остаются обычными T/N.

7. **Label projection probe sharpened.** Локальный semantic check теперь прямо различает `SUBJECT is the name/title/label/designation of complement referent` и остальные nominal relations. Canonical projection остаётся deterministic и происходит только при `YES`.

## Проверки

Добавлен `tests/test_semantic_reliability_v081.py` с лексически независимыми fixtures:

- orphan EMBEDDED не становится goal;
- oblique personal-pronoun syncretism сохраняет neuter object antecedent;
- instrumental PP ambiguity требует clarification без model vote;
- directional PP не получает blanket ambiguity;
- counted object -> OBJECT + AMOUNT, duration не split-ится;
- query role repair ограничен selected T;
- nominal complement не классифицируется как IS-A.

Полный regression suite: **495 passed, 22 subtests passed**.

Live LM Studio acceptance в контейнере не запускается: нужен пользовательский локальный LM Studio + модель. Следующая проверка — повторный 200-case run на том же `acceptance_oracle.json`; после стабилизации acceptance переходим к M2.
