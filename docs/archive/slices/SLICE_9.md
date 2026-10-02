# Slice 9 — text-only Qwen loader + compact perception protocol

Срез исправляет две проблемы, обнаруженные на реальном локальном Qwen3.6-27B.

## 1. Text-only loader

АГент в текущей архитектуре текстовый. Наличие `vision_config` в checkpoint больше не переводит `loader_type=auto` в `AutoProcessor`.

Нормальный путь:

```text
local multimodal/composite Qwen checkpoint
        ↓
AutoTokenizer
AutoModelForCausalLM
        ↓
text-only Perception + Agent roles
```

`image_text_to_text` остаётся явным будущим режимом и только он требует image processor.

## 2. Compact Perception wire protocol

Архитектурный `PerceptionResult` не упрощён. Упрощён только формат, который обязана сгенерировать LLM.

```json
{"a":[{"id":"A1","p":"спит","n":"спать","neg":false,"r":[["SUBJECT","Мария"]]}],"q":[],"c":[]}
```

Adapter разворачивает его в существующие runtime dataclasses. Legacy full JSON продолжает читаться.

Поля `evidence`, `parser_confidence`, `semantic_hint`, `alternatives` не удалены из contracts; compact protocol просто не заставляет модель генерировать их без необходимости.

## 3. JSON repair

При malformed output разрешён один дополнительный stateless role-call `perception_repair`. Он исправляет только wire-format. Каноническая память до успешной валидации не меняется.

## 4. LLM role isolation

Одна модель и один worker по-прежнему обслуживают parser и agent, но hidden conversation history остаётся нулевой:

```text
history_messages = 0
```

Каждый parser call получает только perception prompt + текущий текст. Каждый agent call получает только agent prompt + текущий `AgentContext`.
