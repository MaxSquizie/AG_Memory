# Что взято из `infer_ext.zip`

Архив использован как источник проверенных инженерных решений для локальной LLM-инфраструктуры. Архитектура памяти из старого проекта не переносилась.

## Перенесённые идеи

- LLM живёт в отдельном subprocess, а когнитивный runtime не держит `torch/transformers/CUDA` внутри AH Core.
- Родитель и worker общаются построчным JSON через stdin/stdout.
- Жизненный цикл: `start → ready → request(req_id) → response(req_id) → stop`.
- UTF-8 жёстко задаётся для канала родитель/дочерний процесс.
- Модель загружается только из локальной директории; путь приходит из центрального config.
- Раздельно настраиваются model/tokenizer/LoRA adapter paths.
- Для текущего text-agent runtime используется `AutoTokenizer + AutoModelForCausalLM` даже для composite/multimodal Qwen checkpoint. Vision processor не загружается. Multimodal loader оставлен только как явный будущий opt-in.
- `device_map`, dtype, 4-bit, context limit и sampling вынесены в config.
- При greedy generation нейтрализуются sampling-поля model generation config, чтобы не получать предупреждения/неожиданную семантику.
- Prompt обрезается по токен-бюджету до `ctx_total - max_new_tokens`.

## Что сознательно не перенесено

- VLM/image pipeline;
- эмоции, neuro-delta, VTube/TTS/GUI;
- старая vector-memory;
- проектные stop-фильтры и стилистические post-processors;
- старый orchestration core.

Текущий `ah.llm.worker` оставлен минимальным text-only worker. При необходимости в `llm.engine_script` можно указать внешний `infer_ext.py`; родительский backend содержит совместимый режим запуска.
