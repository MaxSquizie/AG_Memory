from __future__ import annotations

from pathlib import Path

from ah.diagnostics import BoundedHistory


ROOT = Path(__file__).resolve().parents[1]


def test_bounded_diagnostic_history_keeps_exactly_the_last_twenty_items():
    history = BoundedHistory[int](20)
    history.extend(range(27))
    assert history.items == tuple(range(7, 27))
    assert history.latest == 26


def test_metrics_gui_has_separate_m1_m2_m3_tabs_and_no_unmeasured_m4_surface():
    source = (ROOT / "src" / "ah" / "gui" / "metrics_panel.py").read_text(encoding="utf-8")
    assert '"M1 · Formalization"' in source
    assert '"M2 · UID tracing"' in source
    assert '"M3 · GC"' in source
    assert "SnapshotCanvasView" in source
    assert "ProofCanvasView" in source
    assert "BoundedHistory(20)" in source
    assert "M4" not in source


def test_m1_gui_exposes_every_bound_acceptance_family_and_raw_prompt_evidence():
    source = (ROOT / "src" / "ah" / "gui" / "metrics_panel.py").read_text(encoding="utf-8")
    for dirname in (
        "acceptance_runs",
        "acceptance_runs_m1_adversarial",
        "acceptance_runs_m1_inversion",
        "acceptance_runs_m1_ellipsis",
        "acceptance_runs_m1_typo",
    ):
        assert dirname in source
    assert "Исходный промпт" in source
    assert "Домен" in source
    assert "Связи" in source


def test_main_window_keeps_documents_and_metrics_out_of_monitor_preset_and_feeds_histories():
    source = (ROOT / "src" / "ah" / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "_build_document_dock()" in source
    assert "_build_metrics_dock()" in source
    assert 'QAction("Документы"' in source
    assert 'QAction("Метрики M1–M3"' in source
    assert "result.formalization_traces" in source
    assert "set_m2_acceptance_result(result)" in source
    monitor_block = source[source.index("monitor_docks = ("):source.index("# removeDockWidget", source.index("monitor_docks = ("))]
    assert "document_dock" not in monitor_block
    assert "metrics_dock" not in monitor_block


def test_document_pipeline_uses_one_document_batch_and_bounded_source_continuation():
    pipeline = (ROOT / "src" / "ah" / "documents" / "pipeline.py").read_text(encoding="utf-8")
    runtime = (ROOT / "src" / "ah" / "documents" / "runtime.py").read_text(encoding="utf-8")
    public_api = (ROOT / "src" / "ah" / "documents" / "__init__.py").read_text(encoding="utf-8")
    panel = (ROOT / "src" / "ah" / "gui" / "document_panel.py").read_text(encoding="utf-8")

    assert "TemplateCompletionService" in pipeline
    assert "_complete_dynamic_templates" not in pipeline
    assert "integrate_external_batch" in pipeline
    assert "BatchKind.DOCUMENT" in pipeline
    assert "build_source_slice" in pipeline
    assert "SourceProjectionCursor" in pipeline
    assert "raw source/chunk" in pipeline

    assert "DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS = 4096" in runtime
    assert "_reduce_partial_results" in runtime
    assert "ProjectionBudgetExceeded" in runtime
    assert "source_primary_total" in runtime
    assert "stop_reason" in runtime
    assert "from .runtime import" in public_api
    assert "DocumentProcessor" in public_api

    assert "last_document_summary_runtime_state" in panel
    assert "cursor" in panel
    assert "overlap" in panel
    assert "stop=" in panel
