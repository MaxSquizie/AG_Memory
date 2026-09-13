from .contracts import (
    ActivationSeedRequest,
    ClarificationOption,
    ClarificationRequest,
    ClarificationResolutionCommit,
    ClarificationUse,
    IdentityMergeResult,
    IntegratedAssertion,
    IntegratedConditional,
    IntegratedExistential,
    IntegratedFormula,
    IntegratedQuantifiedQuery,
    IntegratedTemporalScope,
    IntegratedConflict,
    IntegratedRelation,
    IntegrationCommit,
    RefutationRequest,
    SeedReason,
    TemplateRequest,
    TemplateSenseOption,
)
from .correction import CorrectionCommit, ContradictionCommit, RefutationCommit, SemanticCorrectionService
from .errors import (
    CandidateValidationError,
    EntityResolutionError,
    IntegrationError,
    UnresolvedDiscourseReferenceError,
    UnresolvedTemporalReferenceError,
    TemplateResolutionError,
)
from .formalization import (
    BatchKind,
    FormalizationBatch,
    CandidateIR,
    DiscourseRef,
    ExistentialBinding,
    UniversalBinding,
    TemporalScopeBinding,
    UnresolvedTemporalRef,
    MutationPlan,
    SemanticConsolidator,
    merge_formalization_units,
    namespace_perception_result,
)
from .service import IntegrationConfig, IntegrationService as _BaseIntegrationService
from .naming_service import NamingAwareIntegrationService
from .identity_naming_service import CanonicalNamingIntegrationService
from .identity_query_service import IdentityQueryIntegrationService
from .template_completion import TemplateCompletionService

# Runtime construction imports IntegrationService from the package. Keep the large
# canonical writer unchanged and expose narrow semantic adapters around it: naming,
# open-event queries and entity-identity query shells are consumed before ordinary
# fact/T integration, while inflected naming values are indexed by their morphology-
# normalized form.
IntegrationService = IdentityQueryIntegrationService

__all__ = [
    "namespace_perception_result",
    "merge_formalization_units",
    "FormalizationBatch",
    "SemanticConsolidator",
    "MutationPlan",
    "DiscourseRef",
    "ExistentialBinding",
    "UniversalBinding",
    "TemporalScopeBinding",
    "UnresolvedTemporalRef",
    "CandidateIR",
    "BatchKind",
    "ActivationSeedRequest",
    "ClarificationOption",
    "ClarificationRequest",
    "ClarificationResolutionCommit",
    "ClarificationUse",
    "CandidateValidationError",
    "EntityResolutionError",
    "IdentityMergeResult",
    "IntegratedAssertion",
    "IntegratedConditional",
    "IntegratedExistential",
    "IntegratedFormula",
    "IntegratedQuantifiedQuery",
    "IntegratedTemporalScope",
    "IntegratedConflict",
    "IntegratedRelation",
    "IntegrationCommit",
    "IntegrationConfig",
    "IntegrationError",
    "UnresolvedDiscourseReferenceError",
    "UnresolvedTemporalReferenceError",
    "IntegrationService",
    "NamingAwareIntegrationService",
    "CanonicalNamingIntegrationService",
    "IdentityQueryIntegrationService",
    "TemplateCompletionService",
    "RefutationRequest",
    "RefutationCommit",
    "CorrectionCommit",
    "ContradictionCommit",
    "SemanticCorrectionService",
    "SeedReason",
    "TemplateRequest",
    "TemplateSenseOption",
    "TemplateResolutionError",
]
