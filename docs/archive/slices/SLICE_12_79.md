# v0.12.79 — LM Studio model discovery compatibility fix

- LM Studio model discovery now uses the OpenAI-compatible `GET /v1/models` endpoint.
- Removed startup dependency on native `GET /api/v1/models`, which can fail on some LM Studio server builds even when OpenAI-compatible inference is available.
- `/v1/models` responses are normalized into the existing LM Studio backend model shape.
- A configured model name may uniquely match the final component of a returned model id, so publisher/path prefixes do not force a config change.
- Inference remains stateless through `POST /v1/chat/completions` with `stream=false`.
