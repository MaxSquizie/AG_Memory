# Инвентаризация содержания проб

База: `606f96e6a535e0ef5b0f3c3084b32449526e227e`. Аудит: [основной документ](../PROBE_CONTENT_AUDIT_2026-10-16.md).

83 места вызова, включая обёртки и общие функции; количество не означает число независимых вопросов. Строки относятся к указанной базе. Статическое наличие не доказывает достижимость в текущей конфигурации.

| Файл | Строки и вызовы |
|---|---|
| `src/ah/formalizer/attitude_composition.py` | 88 `_probe` |
| `src/ah/formalizer/component_clause.py` | 64 `_probe` |
| `src/ah/formalizer/component_dependency_reduction.py` | 84 `_probe` |
| `src/ah/formalizer/component_infinitives.py` | 30 `_probe`, 63 `_probe` |
| `src/ah/formalizer/component_nominal_groups.py` | 49 `_probe` |
| `src/ah/formalizer/component_nominal_questions.py` | 10 `_probe`, 27 `choose`, 69 `choose`, 114 `choose` |
| `src/ah/formalizer/component_participants.py` | 109 `_probe` |
| `src/ah/formalizer/component_predication.py` | 172 `_probe` |
| `src/ah/formalizer/component_refinement.py` | 332 `_probe`, 153 `choose`, 370 `choose`, 396 `choose` |
| `src/ah/formalizer/component_temporal_scope.py` | 20 `_probe` |
| `src/ah/formalizer/composition_boundaries.py` | 52 `_probe` |
| `src/ah/formalizer/composition_children.py` | 40 `choose`, 44 `_probe` |
| `src/ah/formalizer/contextual_agreement.py` | 54 `_probe` |
| `src/ah/formalizer/contextual_oov.py` | 42 `choose` |
| `src/ah/formalizer/coreference.py` | 258 `_probe` |
| `src/ah/formalizer/directional_goal.py` | 36 `_probe` |
| `src/ah/formalizer/discourse_scopes.py` | 72 `_probe`, 118 `_probe` |
| `src/ah/formalizer/document_scopes.py` | 44 `_probe` |
| `src/ah/formalizer/native_frontend.py` | 1077 `_probe` |
| `src/ah/formalizer/nominal_functions.py` | 34 `choose`, 51 `source_set`, 57 `choose`, 76 `choose`, 83 `choose` |
| `src/ah/formalizer/nominal_reference_groups.py` | 78 `_probe` |
| `src/ah/formalizer/nominal_reference_memory.py` | 68 `_probe` |
| `src/ah/formalizer/partition_domain.py` | 76 `span` |
| `src/ah/formalizer/predicate_functions.py` | 20 `choose`, 41 `choose`, 55 `choose` |
| `src/ah/formalizer/qualitative_quantity.py` | 52 `_probe` |
| `src/ah/formalizer/quantifier_composition.py` | 116 `_probe` |
| `src/ah/formalizer/refinement_boundaries.py` | 9 `source_set`, 14 `choose`, 105 `_probe`, 23 `choose`, 74 `choose` |
| `src/ah/formalizer/region_probes.py` | 45 `_probe` |
| `src/ah/formalizer/relation_composition.py` | 91 `choose`, 182 `choose`, 295 `choose`, 328 `choose`, 126 `choose`, 351 `choose`, 153 `choose`, 256 `choose` |
| `src/ah/formalizer/relation_markers.py` | 19 `choose` |
| `src/ah/formalizer/relation_partitions.py` | 14 `domain.span`, 59 `domain.span`, 68 `domain.span`, 89 `domain.span`, 41 `domain.span` |
| `src/ah/formalizer/relation_quantifiers.py` | 12 `domain.span`, 19 `choose`, 35 `choose` |
| `src/ah/formalizer/relative_composition.py` | 40 `_probe` |
| `src/ah/formalizer/relative_pronoun.py` | 21 `choose`, 27 `choose`, 42 `_probe` |
| `src/ah/formalizer/scope_assignment.py` | 190 `_probe` |
| `src/ah/formalizer/soft_clause_boundaries.py` | 34 `_probe` |
| `src/ah/formalizer/source_areas.py` | 41 `choose` |
| `src/ah/formalizer/source_assertions.py` | 57 `_probe` |
| `src/ah/formalizer/spatial_references.py` | 125 `_probe`, 26 `_probe`, 41 `_probe` |
| `src/ah/formalizer/structural_tasks.py` | 216 `span`, 84 `_probe`, 200 `choose`, 236 `choose`, 250 `choose`, 186 `choose` |
| `src/ah/formalizer/temporal_functions.py` | 17 `choose`, 35 `source_set` |

Дополнительно рассмотрены прямые селекторы: `native_frontend.py`, `pipeline.py`, `naming_probe.py`, `open_set_probe.py`, `numeral_extraction.py`. `lexical_embedding.py` использует транспорт эмбеддингов, не языковую микропробу; не включён в языковой инвентарь.

## Наблюдавшиеся исторические слоты

Наличие в старом прогоне не доказывает качество нынешней формулировки. Семейства start/end/continue/piece_end используют общие сборщики границ.

- `child_slot`
- `component_attachment`
- `lexical_recovery`
- `nominal_coordination`
- `nominal_dependency`
- `nominal_function`
- `nominal_function_head`
- `nominal_function_source_continue`
- `nominal_function_source_end`
- `nominal_function_source_piece_end`
- `nominal_function_source_start`
- `nominal_identity_function`
- `predicate_argument_reading`
- `predicate_argument_role`
- `predicate_function`
- `predicate_value`
- `relation_marker_role`
- `spatial_function`
- `speech_act`
- `structural_content_continue`
- `structural_content_end`
- `structural_content_piece_end`
- `structural_content_role`
- `structural_content_start`
- `structural_control`
- `structural_event_head`
- `structural_function_owner`
- `structural_governor`
- `structural_introducer_continue`
- `structural_introducer_end`
- `structural_introducer_piece_end`
- `structural_introducer_start`
- `structural_oov_function`
- `structural_operand_1_continue`
- `structural_operand_1_end`
- `structural_operand_1_piece_end`
- `structural_operand_1_start`
- `structural_operand_2_continue`
- `structural_operand_2_end`
- `structural_operand_2_start`
- `structural_owner`
- `structural_parent_continue`
- `structural_parent_end`
- `structural_parent_piece_end`
- `structural_parent_start`
- `structural_partition`
- `structural_relation`
- `temporal_function`
- `temporal_source_continue`
- `temporal_source_end`
