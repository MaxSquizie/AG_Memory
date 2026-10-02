# Slice 7.4 — node focus + manual node manager

## Что добавлено

1. `paths.llm_model_dir = "C:/AI/qwen_3.6_27B_uncesored"` в default config.
2. Hover/selection являются только GUI state и не мутируют AH.
3. Для focused узла строится immediate neighborhood по обычным `L` и structural edges (`T→S`, `N→T`, `N→actant`, `g→operand`, `k→member`).
4. Selection сохраняется после клика; hover временный. Selection рисуется cyan, hover — yellow.
5. `ManualNodeManager` композирует только public `AHCore` operations под `RuntimeServices.operation_lock`.
6. GUI manager пока создаёт `S` и `m`; можно одновременно создать `L` к выделенному узлу и/или подать diagnostic seed.
7. Все коэффициенты focus/hover находятся в `[gui]` и доступны через существующий config editor.

## Инварианты

- layout/focus/hover не записываются в AH;
- выделение узла не означает Workspace membership;
- подсветка связи не меняет `L.w`;
- manual seed явно управляется оператором и не является semantic assertion/H-experience;
- manual manager не обходит AH Core.
