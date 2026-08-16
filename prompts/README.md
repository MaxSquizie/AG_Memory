# LLM roles

Один `LocalLLMProcessBackend` загружает одну локальную модель и обслуживает Perception и Agent без скрытой chat history (`llm.history_messages = 0`).

## Perception: adaptive_v3

LLM не получает знания об АГ-памяти и не сериализует `PerceptionResult`.

Runtime сначала строит linguistic candidate graph: альтернативные морфологические разборы, predicate candidates, clauses, phrase candidates и coordination. Однозначные решения принимаются без LLM. Для оставшейся неоднозначности модель получает один короткий stateless probe и фактически допустимые варианты.

Активные micro-prompts не содержат examples/few-shot demonstrations. Retry повторяет тот же чистый запрос и не показывает предыдущий ошибочный ответ.

Русский source сохраняется в `surface/mention/evidence` и lexical `S`. Predicate `S`, используемый `T`, детерминированно нормализуется к source-language лексеме; observed формы расширяют тот же `R_text`.

## Agent

`agent.txt` получает deterministic `AgentContext` и генерирует естественный ответ. Собственный ответ записывается в `H` как пережитое событие и по умолчанию не проходит повторный Perception в C/P.

Clarification replies use `clarification_answer.txt`: the model may only identify which already-presented user-visible option the NEW answer explicitly names; canonical `k -> m` replacement remains deterministic.

## v0.12.39 TemplateCandidate policy

Production T discovery uses only explicit semantic roles already present in the current assertion/query/command. It does not guess hidden SUBJECT/OBJECT/RECIPIENT/SOURCE slots. `template_hidden_valency` is retained only for the standalone model capability diagnostic and never authorizes canonical T mutation. All active protocol instructions and labels are English.

The sections below are historical notes for older slices and are not descriptions of the current production template path.

## v0.12.32 TemplateCandidate directional probes

Hidden directional semantics no longer use semantic class names as model outputs. `template_event_directionality` and `template_event_direction` expose only two short descriptions and require `FIRST` or `SECOND`. Each decision is repeated with descriptions swapped; deterministic code accepts only semantic agreement after reverse mapping. The model still never sees AH UIDs or creates `T/N/L/k`.

## v0.12.33 TemplateCandidate semantic completion scoring

Hidden directional valency no longer scores protocol labels such as `FIRST/SECOND` or semantic class names. `template_event_semantics` supplies a minimal lexical context and the worker scores complete English semantic continuations directly. The same continuations are also scored under an `UNKNOWN_VERB` calibration context; Perception uses only the context-induced score delta. `semantic_completion_system.txt` is dedicated to this scoring mode and does not ask the model to return a label. Deterministic code maps the accepted runtime cue to at most one `RECIPIENT` or `SOURCE`; canonical `T` creation remains in Integration.

For `PURPOSE -> infinitive`, a single parent `OBJECT` is treated as an object-control grammar cue inside Perception. No predicate-specific control table and no canonical mutation are introduced.


## v0.12.34 Additional-valency target

`template_event_semantics` now receives the predicate-specific source context plus textual bindings for roles already known to the runtime `TemplateCandidate` (`SUBJECT: Иван`, `OBJECT: книга`). The scored completions ask only whether an **additional** receiver-side or source-side slot exists beyond those roles. A participant already occupying SUBJECT/OBJECT must not be counted again. The neutral calibration prompt keeps the same role shape with `[known subject]` / `[known object]` placeholders and removes the concrete verb/context. Canonical AH UIDs are never exposed; accepted cues are still mapped and validated deterministically before canonical T registration.

## v0.12.35 Bounded generative TemplateCandidate cue

Hidden directional valency no longer uses continuation likelihood, ordinal labels, score margins, or content-free calibration in the active Perception path. After deterministic SUBJECT/OBJECT narrowing, one ordinary temperature-zero generation receives the predicate-specific source text and textual role bindings already known to the runtime candidate. It must return exactly `NONE`, `RECIPIENT`, `SOURCE`, `RECIPIENT,SOURCE`, or `AMBIGUOUS`.

`template_candidate_system.txt` and `template_hidden_valency.txt` define this finite protocol. The model receives no canonical UID/ref and cannot create or register `T`. Python validates the protocol and maps allowed labels to runtime roles; deterministic Integration remains the only layer that validates and registers canonical `T`. `AMBIGUOUS` fails closed under deferred T valency evolution.


## v0.12.36 Binary hidden-valency generation

The active hidden directional path no longer asks Qwen to choose among `NONE`, `RECIPIENT`, `SOURCE`, a combined outcome, and ambiguity. Python asks at most two ordinary generation questions in sequence: RECIPIENT first, then SOURCE only after an exact negative recipient answer.

`template_hidden_valency.txt` is intentionally generic and short. The runtime prompt contains the source sentence, lexical verb, textual known-role bindings, one narrow question and exactly two labels. The ordinary `probe_system.txt` is reused; the retired dedicated template-candidate system/scoring prompts are not active.

Only exact labels are accepted. No choice scoring, calibration, margins or token-probability fallback is used. Python maps a positive cue to at most one runtime `ActantRole`; deterministic Integration remains the only layer that validates and registers canonical `T`.

## v0.12.40 Binary semantic probe policy

When deterministic code has narrowed a semantic decision to exactly two labels, the active parser uses ordinary temperature-zero generation and requires one exact English label. It does not request `choice_outputs`, continuation scores, calibration, or a margin. The scorer remains only for still-unaudited decisions with more than two alternatives.

Nested frame prompts now distinguish **content/complement** from **purpose**: wanted/requested/selected child situations are `OBJECT -> candidate_ref(child)` content; `PURPOSE` means the goal for which the parent action itself is performed. The retired deterministic `PURPOSE + OBJECT` controller shortcut is no longer active.

## v0.12.41 Delayed participant-role probes

- Ordinary accusative OBJECT extraction is deterministic; there is no general animate/pronoun `OBJECT / RECIPIENT` prompt.
- `content_addressee.txt` is invoked only after deterministic structure has established a nested proposition as semantic OBJECT content and one explicit participant occupies that OBJECT slot.
- `control_subject.txt` receives participant descriptions separately from a `CHOICES` block containing only exact protocol labels (`FIRST`, `SECOND`, ...).
- Exact binary labels remain fail-closed; prompts do not ask the model to emit descriptions, JSON, canonical UIDs or full frame schemas.

## v0.12.42 Sticky semantic relation

After a nested child has been accepted as `CONTENT_LINK`, a later participant-role conflict cannot cause the parser to retry the same child as `GOAL_LINK` or another relation. The remaining participant probe is limited to one semantic cue after CONTENT is already known. An unresolved conflict fails closed.

## v0.12.43 Semantic cue / AH-role separation

`content_addressee.txt` does not expose the canonical role name as the model's decision. It asks only whether the known content is directed to the explicit participant and accepts `CONTENT_ADDRESSEE / NOT_CONTENT_ADDRESSEE`. Python maps the positive cue to runtime `RECIPIENT`. This keeps AH ontology construction outside the model and makes the model solve only the natural-language distinction.
