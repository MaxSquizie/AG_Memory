# Slice 7 — GPU GUI / 2.5D cognitive graph

## Решение по GUI

Tkinter не используется. Desktop shell построен на **PySide6**, а центральная визуализация — на **VisPy SceneCanvas/OpenGL**.

Причина: GUI должен одновременно поддерживать dock-панели, редактирование runtime-конфига и GPU-отрисовку динамического графа с тысячами изменяемых visual attributes без привязки когнитивного tick к UI frame rate.

## Canvas

`GraphCanvasWidget` — read-only observer AH runtime:

```text
GraphInspector.snapshot()
        ↓
GraphVisualMapper
        ↓
VisPy GPU buffers
        ↓
2.5D / 3D scene
```

Визуальная семантика:

```text
Z-layer       → C / P / H / S domain band
base hue      → domain
brightness    → x / x_max
node size     → excitation
white flash   → activation/reactivation event
cyan outline  → Workspace membership
yellow outline→ pending incoming impulse
edge alpha    → L.w
moving particle → actual TickResult propagation event
```

Положение узлов — только визуализация и никогда не возвращается в AH/Ignition/Inference.

## Полный AH-граф

Diagnostics теперь экспортирует не только `L`, но и structural edges:

```text
T -> S           PREDICATE
N -> T           TEMPLATE
N -> actant      role
G -> operand
K -> member
```

Поэтому canvas показывает структуру гиперграфа, а не только сеть `L`.

## Propagation diagnostics

`TickResult.propagations` — side-channel для GUI/debug. Он содержит реально вычисленные импульсы текущего tick:

```text
source
receiver
via_uid
via_kind (L/N)
relation/role
amount
```

Это не AH, не H и не влияет на когнитивное состояние.

## Config Editor

В GUI отображаются все scalar/array поля TOML, включая `paths.llm_model_dir`.

Поля классифицируются:

```text
LIVE
NEXT_TURN
RESTART_LLM
RESTART_RUNTIME
```

Перед записью полный config прогоняется через canonical `load_config`. Запись атомарная.

Hot-safe параметры обновляют:

```text
Ignition f/g/h/t/ν
Workspace
Lifecycle/GC policy
Inference budget
Integration initial weights
Context projection
LLM request generation defaults
GUI rendering
```

Параметры загрузки модели требуют `RESTART_LLM`; persistence path и identity — `RESTART_RUNTIME`.

## Runtime concurrency

Добавлен общий `RuntimeServices.operation_lock`.

IgnitionClock берёт его только на один cognitive tick. Orchestrator берёт его только на короткие memory phases, оставляя долгие LLM calls вне lock. Это предотвращает одновременную canonical mutation и tick snapshot, но позволяет Ignition продолжать работать, пока LLM генерирует текст.

## GUI shell

```text
QMainWindow
├── central: VisPy 2.5D/3D graph
├── dock: Dialogue
├── dock: Config
├── dock: Node Inspector
├── dock: Runtime / UID Trace
└── toolbar
    ├── Start/Stop LLM
    ├── Start/Stop Ignition
    ├── Manual Tick
    ├── Save AH
    └── Reset Camera
```

Запуск после установки extras:

```powershell
pip install -e ".[gui,llm]"
ah-gui --config config/default.toml
```
