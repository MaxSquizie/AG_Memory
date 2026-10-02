# Lexical Recovery V1 — архитектурная заметка

## Назначение

Lexical Recovery — отдельный предварительный слой восстановления ввода перед semantic formalization.

Он не является частью semantic parser и не создаёт фактов напрямую.

Цель: устойчивость к локальному шуму текста (опечатки, пропуски символов, лишние символы, простые ошибки раскладки) без нарушения принципа:

```
deterministic narrowing first
semantic decision second
canonical AH commit last
```

## Pipeline

```
Raw text
  |
  v
Lexical Recovery
  |
  +-- exact token
  |
  +-- typo candidate generation (Levenshtein)
  |
  +-- contextual ranking (embeddings)
  |
  +-- morphology validation
  |
  v
TokenCandidate
  |
  v
Existing semantic formalizer
  |
  v
Canonical AH
```

## Основной принцип

Lexical Recovery может предложить исправление:

```
"докмент" -> "документ"
"клюём" -> "ключом"
```

но не имеет права самостоятельно создавать semantic proposition.

Неверное исправление опаснее пропуска ошибки, потому что может привести к ложному знанию в AH.

## Confidence states

Допустимые состояния:

- EXACT — слово найдено без изменения.
- CORRECTED_HIGH_CONFIDENCE — исправление подтверждено несколькими сигналами.
- AMBIGUOUS — несколько кандидатов остаются равноправными.
- UNKNOWN_TOKEN — восстановление невозможно.

Только EXACT и CORRECTED_HIGH_CONFIDENCE могут автоматически передаваться дальше.

## Сигналы

### Levenshtein

Используется для генерации кандидатов:

- пропуск символа;
- лишний символ;
- перестановка соседних символов.

### Embedding similarity

Используется только для ранжирования кандидатов в контексте предложения.

Embedding similarity не является доказательством замены слова.

### Morphology validation

pymorphy и существующие морфологические правила используются для проверки:

- части речи;
- падежа;
- числа;
- согласования с ролью в предложении.

## Ограничения V1

Не входит:

- полноценная грамматическая коррекция;
- перефразирование;
- смысловая замена слов;
- исправление имён собственных без подтверждения;
- автоматическое изменение неоднозначных токенов.

## Acceptance

Lexical Recovery должен тестироваться отдельно от semantic formalization.

Нельзя смешивать:

```
"не распознали слово"
```

и

```
"неправильно построили semantic proposition"
```

Это разные классы ошибок.
