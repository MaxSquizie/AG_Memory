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


def test_document_pipeline_uses_public_completion_one_document_batch_and_complete_source_context():
    source = (ROOT / "src" / "ah" / "documents" / "pipeline.py").read_text(encoding="utf-8")
    assert "TemplateCompletionService" in source
    assert "_complete_dynamic_templates" not in source
    assert "integrate_external_batch" in source
    assert "BatchKind.DOCUMENT" in source
    assert "build_complete_source" in source
    assert "agent.respond(context.agent_context)" in source
