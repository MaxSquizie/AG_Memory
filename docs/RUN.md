# Запуск и эксплуатация AH Agent

Канонический ops-документ для локального desktop runtime.

## Prerequisites

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/)
- Для **Ollama**: [Ollama](https://ollama.com/) (`ollama serve`, порт `11434`)
- Для **PyTorch worker**: CUDA или CPU, локальный Hugging Face checkpoint

## Установка (uv)

Базовый runtime **без PyTorch** — достаточно для `backend = "ollama"`:

```bash
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -e ".[gui]"
```

Локальный HF/PyTorch subprocess (`backend = "builtin_process"`) — **отдельная** команда:

```bash
uv pip install -e ".[llm]"
```

Опционально поверх `[llm]`:

```bash
uv pip install -e ".[llm-lora]"
uv pip install -e ".[llm-vision]"
```

## Профили config

| Профиль | Файл | Backend | Нужен `[llm]` |
|---------|------|---------|---------------|
| Ollama (рекомендуется для первого запуска) | `config/ollama.toml` | `ollama` | нет |
| Локальный HF/PyTorch | `config/default.toml` | `builtin_process` | да |

### Ollama

```bash
ollama serve                       # если ещё не запущен как сервис
ollama pull qwen2.5:7b             # или другая модель из config
curl http://127.0.0.1:11434/api/tags
```

В `config/ollama.toml`:

```toml
[llm]
backend = "ollama"
ollama_base_url = "http://127.0.0.1:11434"
ollama_model = "qwen2.5:7b"
```

Модель можно сменить в GUI на панели **LLM** (ComboBox + «Обновить»).

### PyTorch worker

В `config/default.toml` укажите `paths.llm_model_dir` (или выберите папку в GUI → **Конфигурация** → «Папка LLM…»).

```toml
[llm]
backend = "builtin_process"
```

Без `uv pip install -e ".[llm]"` кнопка **Start LLM** выдаст понятную ошибку.

## Запуск GUI (Win / macOS / Linux)

Каноническая команда:

```bash
ah-gui --config config/ollama.toml
ah-gui --config config/default.toml
```

Обёртки в корне репозитория:

| ОС | Команда |
|----|---------|
| Windows | `run_gui.bat` |
| macOS / Linux | `./run_gui.sh` |

Переменная окружения `AH_CONFIG` переопределяет путь к config (по умолчанию `config/ollama.toml`).

Без активации venv:

```bash
uv run --extra gui ah-gui --config config/ollama.toml
```

## Workflow в GUI

1. **Start LLM** — подключение к Ollama или запуск subprocess worker
2. **Start Ignition** — фоновый tick clock
3. Диалог / acceptance / диагностика
4. После смены модели Ollama или полей с меткой `RESTART_LLM` — **Restart** на панели LLM

## Linux: Qt / OpenGL

При ошибке `Could not load the Qt platform plugin "xcb"` (Debian/Ubuntu):

```bash
sudo apt install libxcb-xinerama0 libxcb-cursor0 libgl1
```

## Troubleshooting

| Симптом | Решение |
|---------|---------|
| `Ollama unreachable` | `ollama serve`, проверить `ollama_base_url` |
| Модель не в списке | `ollama pull <model>` → «Обновить» в GUI |
| `PyTorch worker is not installed` | `uv pip install -e ".[llm]"` |
| `paths.llm_model_dir is required` | Указать путь для `builtin_process` или переключиться на `ollama` |
| GUI extras not installed | `uv pip install -e ".[gui]"` |

## Session logs

Каждый запуск GUI/CLI пишет в `paths.logs_dir` (по умолчанию `logs/`):

- `logs/latest.log` — короткие строки (роли, sanitize/repair, границы хода)
- `logs/latest.jsonl` — полные prompt/response LLM, в том числе `agent_repair`
- `logs/session-<timestamp>-<id>.jsonl` / `.log` — тот же сеанс, не перезаписывается

```bash
tail -f logs/latest.log
```

## CLI (без полного диалога)

```bash
ah-agent --config config/ollama.toml summary
```

## Тесты

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
