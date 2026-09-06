# Проверки v0.25.13

Окружение: Python 3.12.13, pytest 9.1.1, pymorphy3 2.0.6, русский словарь 2.4.417150.4580142, numpy. PyTorch в проверочном окружении отсутствует.

| Набор | Результат |
|---|---|
| Весь исходный v0.25.12 в этом окружении | 739 passed, 14 failed, 38 subtests passed |
| 106 новых проверок на исходном коде | 38 passed, 68 failed |
| 106 новых проверок после изменений | 106 passed |
| Новые + прежние проверки эллипсиса | 114 passed |
| Весь проект v0.25.13 | 847 passed, 12 failed, 38 subtests passed |
| compileall src tests | OK |

Множество оставшихся 12 failures является подмножеством исходных 14. Два исходных сбоя устранило восстановление имени reference-файла. Новых падений в общем наборе не появилось.

## Оставшиеся failures

- 2 требуют отсутствующего PyTorch: calibration/fixed-choice scoring worker.
- 7 тестов старого дискретного протокола не согласуются с текущим поведением auto-morphology/lexeme comparison.
- 2 теста possessive projection останавливаются на неразрешённой discourse reference `торжество его`.
- 1 тест неоднозначного genitive/dative требует не предусмотренного его backend-фикстурой nominal attachment probe.

Это классификация наблюдаемых ошибок, а не утверждение, что все они безусловно являются только ошибками тестов. Точные traceback сохранены в `verification/02513/final_full.txt`.

- `tests/test_architecture_alignment_1233.py::ArchitectureAlignment1233Tests::test_worker_calibration_can_reverse_a_raw_continuation_prior`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_act_type_probe_puts_plain_options_before_task_and_does_not_show_tokens`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_command_uses_same_discrete_span_and_role_pipeline`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_numeric_normalization_does_not_extract_choice_from_prose`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_numeric_probes_accept_terminal_punctuation_only`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_parser_uses_english_semantic_labels_and_numeric_token_choices`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_probe_retry_is_clean_and_never_receives_previous_bad_answer`
- `tests/test_llm_roles.py::LLMRoleTests::test_adaptive_query_fill_role_is_built_from_numeric_choices`
- `tests/test_llm_roles.py::LLMRoleTests::test_worker_fixed_choice_scoring_returns_only_allowed_option`
- `tests/test_nominal_relations_v090.py::test_integration_materializes_head_plus_possessor_link_not_flat_phrase_entity`
- `tests/test_nominal_relations_v090.py::test_negated_assertion_does_not_leak_possession_into_world_graph`
- `tests/test_semantic_boundaries_1258.py::StructuralNarrowing1258Tests::test_ambiguous_genitive_dative_nominal_is_not_absorbed_into_previous_np`

## Команды

```bash
python -m pytest -q
python -m pytest -q tests/test_ellipsis_invariants_02513.py tests/test_ellipsis_canonical_02513.py tests/test_ellipsis_recovery_0257.py
python -m compileall -q src tests
```

Для сравнения новые тесты также запущены с `-o pythonpath=<распакованный оригинал>/src`; исходные файлы не исправлялись в этом сравнении.
Результат живого acceptance из LM Studio не пересчитывался и не экстраполируется из offline-тестов.
