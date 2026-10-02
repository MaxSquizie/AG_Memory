# Slice 7.1 — VisPy label initialization fix

Исправлена совместимость `GraphCanvasWidget` с текущим `vispy.visuals.TextVisual`.

`TextVisual` нельзя создавать с `pos` длины 0. Label layer теперь создаётся с одной
невидимой placeholder-позицией `(0, 0, 0)`, а при отсутствии подписей скрывается через
`visible = False`. Семантика AH, Ignition и визуализации не изменена.
