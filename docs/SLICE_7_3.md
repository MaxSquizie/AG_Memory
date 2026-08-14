# Slice 7.3 — VisPy empty-visual hardening

Исправлен startup crash в `LineVisual`: пустые `pos/color` массивы больше не используются как визуальное состояние.

Все GPU layers (`Line`, `Markers`, propagation particles, labels) создаются с безопасными non-empty placeholder-данными и скрываются через `visible = False`, пока данных нет. Это важно для пустой AH-памяти при первом запуске GUI.

Поведение памяти и Ignition не изменено: это только read-only rendering fix.
