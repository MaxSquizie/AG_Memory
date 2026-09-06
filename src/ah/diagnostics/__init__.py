from .acceptance_runner import AcceptanceCase, AcceptanceRunResult, load_acceptance_cases, run_acceptance_suite
from .semantic_oracle import (
    DEFAULT_ORACLE_FILENAME,
    SemanticCaseVerdict,
    SemanticOracleCase,
    SemanticOracleError,
    SemanticOracleReport,
    evaluate_acceptance_bundle,
    load_semantic_oracle,
    validate_oracle_alignment,
)
from .document_acceptance import (
    DEFAULT_DOCUMENT_ORACLE,
    DOCUMENT_RUNS_DIRNAME,
    DocumentAcceptanceError,
    DocumentAcceptanceRunResult,
    DocumentParagraph,
    DocumentSpec,
    DocumentVerdict,
    evaluate_document_graph,
    load_document_specs,
    run_document_acceptance,
)
from .hidden_valency_diagnostic import (
    HiddenValencyDiagnosticCase,
    HiddenValencyDiagnosticResult,
    run_hidden_valency_diagnostic,
)
from .graph_dump import GraphInspector, GraphSnapshot, LinkDiagnostic, NodeDiagnostic, StructuralEdgeDiagnostic
from .summary import RuntimeDiagnostics, RuntimeSummary
from .trace_view import TraceView
from .inference_proof import (
    ProofCheck, ProofChainSnapshot, ProofEdgeSnapshot, ProofNodeSnapshot,
    ProofSnapshotBuilder, ProofStepSnapshot,
)
from .m2_acceptance import (
    M2AcceptanceCaseResult,
    M2AcceptanceRunResult,
    run_m2_attention_acceptance,
    run_m2_cold_workspace_acceptance,
)
from .hackathon_preflight import (
    HackathonPreflightInspector, HackathonPreflightReport, HyperparameterRecord,
)

from .hackathon_metrics import (
    M1Report, M2QuestionObservation, M2ScoreReport, M3Report, M4Report, M5Report, TickBenchmarkReport,
    RoleMetric, run_m3_gc_acceptance, score_m1_acceptance_bundle, score_m1_role_f1,
    score_m2_explainability, score_m4_comparison, score_m5_robustness, run_tick_benchmark, write_metric_report,
)

from .propagation_audit import (
    FanoutAudit, PropagationAudit, PropagationEdgeAudit, analyze_propagation, propagation_edges,
)

__all__ = [
    "AcceptanceCase",
    "AcceptanceRunResult",
    "load_acceptance_cases",
    "run_acceptance_suite",
    "DEFAULT_ORACLE_FILENAME",
    "SemanticCaseVerdict",
    "SemanticOracleCase",
    "SemanticOracleError",
    "SemanticOracleReport",
    "evaluate_acceptance_bundle",
    "load_semantic_oracle",
    "validate_oracle_alignment",
    "DEFAULT_DOCUMENT_ORACLE",
    "DOCUMENT_RUNS_DIRNAME",
    "DocumentAcceptanceError",
    "DocumentAcceptanceRunResult",
    "DocumentParagraph",
    "DocumentSpec",
    "DocumentVerdict",
    "evaluate_document_graph",
    "load_document_specs",
    "run_document_acceptance",
    "HiddenValencyDiagnosticCase",
    "HiddenValencyDiagnosticResult",
    "run_hidden_valency_diagnostic",
    "GraphInspector",
    "GraphSnapshot",
    "LinkDiagnostic",
    "NodeDiagnostic",
    "StructuralEdgeDiagnostic",
    "RuntimeDiagnostics",
    "RuntimeSummary",
    "TraceView",
    "ProofCheck",
    "ProofChainSnapshot",
    "ProofEdgeSnapshot",
    "ProofNodeSnapshot",
    "ProofSnapshotBuilder",
    "ProofStepSnapshot",
    "M2AcceptanceCaseResult",
    "M2AcceptanceRunResult",
    "run_m2_attention_acceptance",
    "run_m2_cold_workspace_acceptance",
    "HackathonPreflightInspector",
    "HackathonPreflightReport",
    "HyperparameterRecord",
    "RoleMetric",
    "M1Report",
    "M2QuestionObservation",
    "M2ScoreReport",
    "M3Report",
    "M4Report",
    "M5Report",
    "TickBenchmarkReport",
    "score_m1_role_f1",
    "score_m1_acceptance_bundle",
    "score_m2_explainability",
    "run_m3_gc_acceptance",
    "score_m4_comparison",
    "score_m5_robustness",
    "run_tick_benchmark",
    "write_metric_report",
    "FanoutAudit",
    "PropagationAudit",
    "PropagationEdgeAudit",
    "analyze_propagation",
    "propagation_edges",
]
