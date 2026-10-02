# Slice 9.4 — robust perception boundary

Изменения:

- default protocol: `span_v1`;
- Perception получает только текущую пользовательскую реплику, без Workspace/AgentContext;
- LLM выбирает номера source-token spans вместо копирования произвольного текста;
- deterministic adapter восстанавливает `PredicateCandidate` / `ActantCandidate` и evidence offsets;
- parser max output сокращён до 96 tokens;
- schema/prompt echo не может пройти span validation;
- собственный ответ агента всегда записывается в H, но по умолчанию без второго LLM perception-call;
- semantic reparse собственного ответа остаётся опциональным H-only режимом;
- sanitizer распознаёт context echo и без двоеточий (`CURRENT INPUT`, `ACTIVE MEMORY`).

Причина: модель в реальном прогоне копировала описание line_v1 вместо разбора, а последний Parser RAW фактически относился к повторному разбору agent response, который содержал echo AgentContext.
