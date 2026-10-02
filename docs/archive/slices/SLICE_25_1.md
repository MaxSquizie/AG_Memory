# Slice v0.25.1 — GUI binding для M1 adversarial acceptance

## Задача

В v0.25.0 новый adversarial M1 corpus был доступен через CLI `semantic-acceptance`, но GUI-кнопка `Прогнать acceptance-файл` оставалась привязана к старой broad-паре. Для живой диагностики это неудобно и легко приводит к запуску не того корпуса.

## Изменение

В dock `Диалог` добавлена отдельная кнопка:

`M1: adversarial acceptance`

Она запускает тот же production diagnostic path `run_acceptance_suite`, но с отдельной парой:

- `data/acceptance_cases_m1_adversarial.txt`
- `data/acceptance_oracle_m1_adversarial.json`

и отдельным каталогом результатов:

- `data/acceptance_runs_m1_adversarial/`

Исходная кнопка `Прогнать acceptance-файл` не изменена семантически и продолжает использовать `acceptance_cases.txt` / `acceptance_oracle.json`.

## Runtime safety

Оба acceptance-run используют один `_acceptance_worker`, поэтому одновременно запустить broad и adversarial suite нельзя. Новая кнопка также блокируется на время Document acceptance, Hidden-valency и M2, а эти режимы блокируют её симметрично.

## Regression

Добавлен `tests/test_gui_m1_adversarial_acceptance_v0251.py`, который фиксирует:

1. наличие отдельной кнопки и signal binding;
2. точные filenames adversarial cases/oracle;
3. отдельный `runs_dirname`;
4. использование реального `run_acceptance_suite`;
5. обновление tooltip при смене `data_dir`.
