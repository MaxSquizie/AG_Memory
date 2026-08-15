# LLM roles

Один `LocalLLMProcessBackend` загружает одну локальную модель и обслуживает Perception и Agent без скрытой chat history (`llm.history_messages = 0`).

## Perception: adaptive_v3

LLM не получает знания об АГ-памяти и не сериализует `PerceptionResult`.

Runtime сначала строит linguistic candidate graph: альтернативные морфологические разборы, predicate candidates, clauses, phrase candidates и coordination. Однозначные решения принимаются без LLM. Для оставшейся неоднозначности модель получает один короткий stateless probe и фактически допустимые варианты.

Активные micro-prompts не содержат examples/few-shot demonstrations. Retry повторяет тот же чистый запрос и не показывает предыдущий ошибочный ответ.

Русский source сохраняется в `surface/mention/evidence` и lexical `S`. Predicate `S`, используемый `T`, детерминированно нормализуется к source-language лексеме; observed формы расширяют тот же `R_text`.

## Agent

`agent.txt` получает deterministic `AgentContext` и генерирует естественный ответ. Собственный ответ записывается в `H` как пережитое событие и по умолчанию не проходит повторный Perception в C/P.
