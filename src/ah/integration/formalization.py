from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Mapping
import re

from ah.agent import InteractionContext
from ah.model import ActantRole, Domain, Ref, VariableSort
from ah.integration.errors import CandidateValidationError
from ah.temporal import TemporalAnchorContext, TemporalNormalizer, temporal_value_from_ref
from ah.perception import (
    ActDependencyCandidate,
    ActRelationCandidate,
    ActantCandidate,
    AssertionCandidate,
    CommandCandidate,
    ConditionalCandidate,
    NominalRelationCandidate,
    PerceptionResult,
    PropositionExprCandidate,
    QuantifierCandidate,
    QuantifierKind,
    PropositionRootCandidate,
    QuantifiedQuerySpec,
    QueryCandidate,
    SituationRelationCandidate,
    SituationRelationHintCandidate,
)
from ah.perception.quantifier_formalization import (
    QuantifierFormalizationError,
    QuantifierFormalizer,
)
from ah.perception.morphology import Morphology, build_morphology, material_analyses
from ah.perception.scoping import apply_speech_act_scoping

from .candidate_validator import CandidateValidator
from .deixis_resolver import DeixisResolver


class BatchKind(str, Enum):
    """Runtime ingestion boundary.

    The value affects consolidation policy only.  It is not a canonical AH kind
    and is never persisted as a semantic node.
    """

    MESSAGE = "MESSAGE"
    DOCUMENT = "DOCUMENT"


@dataclass(frozen=True, slots=True)
class FormalizationBatch:
    """One complete runtime batch before semantic consolidation.

    A document may be perceived in bounded source windows for operational reasons,
    but the windows remain staging units.  Their candidate graphs are namespaced and
    merged before the single canonical commit.  Raw window boundaries therefore do
    not become semantic episode boundaries by themselves.
    """

    source_text: str
    units: tuple[PerceptionResult, ...]
    batch_kind: BatchKind = BatchKind.MESSAGE
    source_ref: str | None = None
    unit_offsets: tuple[int, ...] | None = None
    # Technical source/document timestamp used only as a relative-time anchor.
    # It is provenance/runtime context and is not copied into every semantic fact.
    source_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_text.strip() and any(unit.source_text.strip() for unit in self.units):
            raise ValueError("FormalizationBatch.source_text must contain the batch source")
        if not self.units:
            raise ValueError("FormalizationBatch requires at least one perception unit")
        if self.batch_kind is BatchKind.MESSAGE and len(self.units) != 1:
            raise ValueError("MESSAGE batch must contain exactly one perception unit")
        if self.unit_offsets is not None:
            if len(self.unit_offsets) != len(self.units):
                raise ValueError("FormalizationBatch.unit_offsets must match units")
            if any(value < 0 for value in self.unit_offsets):
                raise ValueError("FormalizationBatch.unit_offsets must be >= 0")


@dataclass(frozen=True, slots=True)
class DiscourseRef:
    """Runtime-only unresolved discourse referent.

    A DiscourseRef deliberately has no AH UID.  It records only the source-bound
    constraints required to keep an unresolved mention explicit until later
    consolidation/clarification.  Canonical Integration must never materialize the
    descriptor itself as ``m`` merely to make an actant slot non-empty.
    """

    local_id: str
    mention: str
    assertion_id: str
    role: ActantRole
    grammatical_number: str | None = None
    grammatical_gender: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    candidate_entity_refs: tuple[str, ...] = ()
    nominal_relation_index: int | None = None

    def __post_init__(self) -> None:
        if not self.local_id.strip() or not self.mention.strip() or not self.assertion_id.strip():
            raise ValueError("DiscourseRef identifiers/mention must be non-empty")
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("DiscourseRef source_start/source_end must be both set or both None")
        if self.nominal_relation_index is not None and self.nominal_relation_index < 0:
            raise ValueError("nominal_relation_index must be non-negative")
        if any(not value.strip() for value in self.candidate_entity_refs):
            raise ValueError("DiscourseRef candidate_entity_refs must be non-empty identifiers")


@dataclass(frozen=True, slots=True)
class ExistentialBinding:
    """Runtime-only binding for one genuinely unknown discourse participant.

    ``entity_ref`` is a parser-local identity handle, not a canonical UID.  The
    binding instructs Integration to use a scoped ``BoundVar`` and an ``EXISTS``
    formula instead of fabricating ``m_UNKNOWN``/``m_КТО-ТО``.  Several source
    assertions may reuse the same handle and therefore the same variable.
    """

    entity_ref: str
    variable_id: int
    sort: VariableSort = VariableSort.ENTITY
    # Optional prior cross-turn existential scope. These references are runtime
    # continuation evidence only; they do not create a new canonical node kind.
    anchor_ref: Ref | None = None
    anchor_member_refs: tuple[Ref, ...] = ()
    negative: bool = False
    restriction_lemma: str | None = None

    def __post_init__(self) -> None:
        if not self.entity_ref.strip():
            raise ValueError("ExistentialBinding.entity_ref must be non-empty")
        if self.variable_id < 0:
            raise ValueError("ExistentialBinding.variable_id must be >= 0")
        if self.anchor_ref is not None and self.anchor_ref.kind.value != "G":
            raise ValueError("ExistentialBinding.anchor_ref must be G")
        if self.anchor_ref is None and self.anchor_member_refs:
            raise ValueError("anchor_member_refs require anchor_ref")
        if self.negative and self.anchor_ref is not None:
            raise ValueError("negative existentials cannot continue a prior existential anchor")
        if self.restriction_lemma is not None:
            value = self.restriction_lemma.strip().casefold().replace("ё", "е")
            object.__setattr__(self, "restriction_lemma", value or None)


@dataclass(frozen=True, slots=True)
class UniversalBinding:
    """Runtime-only binding for a universal determiner plus restriction class.

    ``entity_ref`` is a parser-local handle, not a canonical UID. Integration
    uses a scoped ``BoundVar`` and an asserted ``FORALL``/``IMPLIES`` rule instead
    of fabricating ``m_все_люди``. ``negate_quantifier`` is the §24.2 ``не все``
    reading; body negation is kept on the assertion itself.
    """

    entity_ref: str
    variable_id: int
    restriction_lemma: str
    sort: VariableSort = VariableSort.ENTITY
    negate_quantifier: bool = False

    def __post_init__(self) -> None:
        if not self.entity_ref.strip():
            raise ValueError("UniversalBinding.entity_ref must be non-empty")
        if self.variable_id < 0:
            raise ValueError("UniversalBinding.variable_id must be >= 0")
        if not self.restriction_lemma.strip():
            raise ValueError("UniversalBinding.restriction_lemma must be non-empty")


@dataclass(frozen=True, slots=True)
class UnresolvedTemporalRef:
    """Runtime-only relative TIME actant that lacks a legal anchor."""

    local_id: str
    assertion_id: str
    role: ActantRole
    mention: str
    reason: str
    source_start: int | None = None
    source_end: int | None = None

    def __post_init__(self) -> None:
        if not self.local_id.strip() or not self.assertion_id.strip() or not self.mention.strip():
            raise ValueError("UnresolvedTemporalRef identifiers/mention must be non-empty")
        if self.role is not ActantRole.TIME:
            raise ValueError("UnresolvedTemporalRef role must be TIME")
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("source_start/source_end must be both set or both None")


@dataclass(frozen=True, slots=True)
class CandidateIR:
    """Validated runtime semantic candidate graph before canonical mutation."""

    source_text: str
    perception: PerceptionResult
    ordered_assertion_ids: tuple[str, ...]
    discourse_refs: tuple[DiscourseRef, ...] = ()
    existential_bindings: tuple[ExistentialBinding, ...] = ()
    universal_bindings: tuple[UniversalBinding, ...] = ()
    temporal_refs: tuple[UnresolvedTemporalRef, ...] = ()
    batch_kind: BatchKind = BatchKind.MESSAGE
    source_ref: str | None = None
    source_timestamp: datetime | None = None
    experience_timestamp: datetime | None = None

    def assertion(self, local_id: str) -> AssertionCandidate:
        for item in self.perception.assertions:
            if item.local_id == local_id:
                return item
        raise KeyError(local_id)


@dataclass(frozen=True, slots=True)
class MutationPlan:
    """Immutable, prevalidated staging plan consumed by the canonical write boundary.

    UID allocation and actual canonical objects are intentionally absent here.
    They are produced only inside ``AHCore.transaction()`` after this plan has been
    validated.  A failed transaction therefore cannot leave a half-integrated AH.
    """

    candidate_ir: CandidateIR
    forced_domain: Domain | None
    speaker_ref: Ref
    existing_experience_ref: Ref | None = None

    @property
    def perception(self) -> PerceptionResult:
        return self.candidate_ir.perception

    @property
    def ordered_assertions(self) -> tuple[AssertionCandidate, ...]:
        return tuple(self.candidate_ir.assertion(uid) for uid in self.candidate_ir.ordered_assertion_ids)




def _offset_evidence(evidence, offset: int):
    if evidence is None or offset == 0 or evidence.start is None:
        return evidence
    return replace(evidence, start=evidence.start + offset, end=evidence.end + offset)


def _offset_predicate(predicate, offset: int):
    return replace(predicate, evidence=_offset_evidence(predicate.evidence, offset))


def _offset_composition(composition, offset: int):
    if composition is None:
        return None
    return replace(
        composition,
        members=tuple(
            replace(member, evidence=_offset_evidence(member.evidence, offset))
            for member in composition.members
        ),
    )


def _offset_actant(actant: ActantCandidate, offset: int) -> ActantCandidate:
    return replace(
        actant,
        evidence=_offset_evidence(actant.evidence, offset),
        quantifier=(
            None
            if actant.quantifier is None
            else replace(
                actant.quantifier,
                evidence=_offset_evidence(actant.quantifier.evidence, offset),
            )
        ),
        composition=_offset_composition(actant.composition, offset),
        nominal_relations=tuple(
            replace(relation, evidence=_offset_evidence(relation.evidence, offset))
            for relation in actant.nominal_relations
        ),
    )


def _unit_offsets(batch: FormalizationBatch) -> tuple[int, ...]:
    """Return document-global offsets for bounded perception units.

    Explicit offsets are preferred.  Otherwise units are located monotonically in
    the original batch text.  Failing to locate a non-empty unit is an ingestion
    contract error: silently retaining unit-local spans would make provenance from
    different windows collide.
    """

    if batch.unit_offsets is not None:
        return batch.unit_offsets
    if len(batch.units) == 1:
        return (0,)
    out: list[int] = []
    cursor = 0
    for index, unit in enumerate(batch.units):
        text = unit.source_text
        if not text:
            out.append(cursor)
            continue
        found = batch.source_text.find(text, cursor)
        if found < 0:
            raise ValueError(
                f"Cannot locate perception unit {index} in FormalizationBatch.source_text; "
                "provide explicit unit_offsets"
            )
        out.append(found)
        cursor = found + len(text)
    return tuple(out)

def _prefix_local(value: str | None, prefix: str) -> str | None:
    return None if value is None else f"{prefix}{value}"


def _namespace_expr(expr: PropositionExprCandidate | None, prefix: str) -> PropositionExprCandidate | None:
    if expr is None:
        return None
    if expr.ref is not None:
        return replace(expr, ref=f"{prefix}{expr.ref}")
    return replace(expr, members=tuple(_namespace_expr(item, prefix) for item in expr.members))


def _namespace_proposition_root(
    item: PropositionRootCandidate,
    prefix: str,
    source_offset: int = 0,
) -> PropositionRootCandidate:
    return replace(
        item,
        local_id=f"{prefix}{item.local_id}",
        expression=_namespace_expr(item.expression, prefix),
        evidence=_offset_evidence(item.evidence, source_offset),
        operator_source_refs=tuple(f"{prefix}{ref}" for ref in item.operator_source_refs),
    )


def _namespace_actant(actant: ActantCandidate, prefix: str, source_offset: int = 0) -> ActantCandidate:
    nominal_relations = tuple(
        replace(
            relation,
            dependent_entity_ref=_prefix_local(relation.dependent_entity_ref, prefix),
            evidence=_offset_evidence(relation.evidence, source_offset),
        )
        for relation in actant.nominal_relations
    )
    return replace(
        actant,
        candidate_ref=_prefix_local(actant.candidate_ref, prefix),
        entity_ref=_prefix_local(actant.entity_ref, prefix),
        proposition=_namespace_expr(actant.proposition, prefix),
        nominal_relations=nominal_relations,
        evidence=_offset_evidence(actant.evidence, source_offset),
        quantifier=(
            None
            if actant.quantifier is None
            else replace(
                actant.quantifier,
                evidence=_offset_evidence(actant.quantifier.evidence, source_offset),
            )
        ),
        composition=_offset_composition(actant.composition, source_offset),
    )


def _namespace_quantified_query(
    spec: QuantifiedQuerySpec | None,
    prefix: str,
) -> QuantifiedQuerySpec | None:
    if spec is None:
        return None
    return replace(
        spec,
        bindings=tuple(
            replace(binding, entity_ref=f"{prefix}{binding.entity_ref}")
            for binding in spec.bindings
        ),
    )


def _namespace_assertion(item: AssertionCandidate, prefix: str, source_offset: int = 0) -> AssertionCandidate:
    local_id = f"{prefix}{item.local_id}"
    alternatives = tuple(
        replace(
            alt,
            local_id=local_id,
            predicate=_offset_predicate(alt.predicate, source_offset),
            actants=tuple(_namespace_actant(actant, prefix, source_offset) for actant in alt.actants),
            evidence=_offset_evidence(alt.evidence, source_offset),
            alternatives=(),
        )
        for alt in item.alternatives
    )
    return replace(
        item,
        local_id=local_id,
        predicate=_offset_predicate(item.predicate, source_offset),
        actants=tuple(_namespace_actant(actant, prefix, source_offset) for actant in item.actants),
        evidence=_offset_evidence(item.evidence, source_offset),
        alternatives=alternatives,
    )


def namespace_perception_result(
    result: PerceptionResult, unit_index: int, *, source_offset: int = 0
) -> PerceptionResult:
    """Make one staging unit collision-free inside a document batch.

    Parser-local assertion/entity identifiers have no meaning outside their unit.
    Prefixing them before merge prevents accidental cross-window identity caused by
    counters restarting from ``A1``/``E1``.  Canonical identity is still resolved
    later from semantic evidence, not from this namespace.
    """

    if unit_index < 0:
        raise ValueError("unit_index must be >= 0")
    prefix = f"B{unit_index}:"
    assertions = tuple(_namespace_assertion(item, prefix, source_offset) for item in result.assertions)
    queries = tuple(
        replace(
            item,
            local_id=_prefix_local(item.local_id, prefix),
            predicate=_offset_predicate(item.predicate, source_offset),
            actants=tuple(_namespace_actant(actant, prefix, source_offset) for actant in item.actants),
            quantified=_namespace_quantified_query(item.quantified, prefix),
        )
        for item in result.queries
    )
    commands = tuple(
        replace(
            item,
            local_id=_prefix_local(item.local_id, prefix),
            predicate=_offset_predicate(item.predicate, source_offset),
            actants=tuple(_namespace_actant(actant, prefix, source_offset) for actant in item.actants),
        )
        for item in result.commands
    )
    relations = tuple(
        replace(
            item,
            source_ref=f"{prefix}{item.source_ref}",
            target_ref=f"{prefix}{item.target_ref}",
            evidence=_offset_evidence(item.evidence, source_offset),
        )
        for item in result.relations
    )
    act_relations = tuple(
        replace(item, act_ref=f"{prefix}{item.act_ref}") for item in result.act_relations
    )
    conditionals = tuple(
        replace(
            item,
            antecedent_refs=tuple(f"{prefix}{ref}" for ref in item.antecedent_refs),
            consequent_refs=tuple(f"{prefix}{ref}" for ref in item.consequent_refs),
            antecedent_expr=_namespace_expr(item.antecedent_expr, prefix),
            consequent_expr=_namespace_expr(item.consequent_expr, prefix),
            evidence=_offset_evidence(item.evidence, source_offset),
        )
        for item in result.conditionals
    )
    dependencies = tuple(
        replace(item, parent_ref=f"{prefix}{item.parent_ref}", child_ref=f"{prefix}{item.child_ref}")
        for item in result.act_dependencies
    )
    hints = tuple(
        replace(
            item,
            source_ref=f"{prefix}{item.source_ref}",
            target_ref=f"{prefix}{item.target_ref}",
            evidence=_offset_evidence(item.evidence, source_offset),
        )
        for item in result.relation_hints
    )
    return replace(
        result,
        assertions=assertions,
        queries=queries,
        commands=commands,
        relations=relations,
        act_relations=act_relations,
        conditionals=conditionals,
        proposition_roots=tuple(
            _namespace_proposition_root(item, prefix, source_offset)
            for item in result.proposition_roots
        ),
        act_dependencies=dependencies,
        relation_hints=hints,
    )


def merge_formalization_units(batch: FormalizationBatch) -> PerceptionResult:
    """Merge namespaced staging units into one PerceptionResult for one commit."""

    offsets = _unit_offsets(batch)
    units = tuple(
        namespace_perception_result(unit, index, source_offset=offsets[index])
        for index, unit in enumerate(batch.units)
    )
    return PerceptionResult(
        source_text=batch.source_text,
        assertions=tuple(item for unit in units for item in unit.assertions),
        queries=tuple(item for unit in units for item in unit.queries),
        commands=tuple(item for unit in units for item in unit.commands),
        diagnostics=tuple(
            f"B{index}:{diagnostic}"
            for index, unit in enumerate(units)
            for diagnostic in unit.diagnostics
        ),
        relations=tuple(item for unit in units for item in unit.relations),
        act_relations=tuple(item for unit in units for item in unit.act_relations),
        conditionals=tuple(item for unit in units for item in unit.conditionals),
        proposition_roots=tuple(item for unit in units for item in unit.proposition_roots),
        act_dependencies=tuple(item for unit in units for item in unit.act_dependencies),
        relation_hints=tuple(item for unit in units for item in unit.relation_hints),
    )


class SemanticConsolidator:
    """Deterministic pre-commit consolidation boundary for one complete batch.

    The existing parser remains responsible for morphology/syntax and bounded
    semantic probes.  This component does not invent semantics and does not write
    AH.  It normalizes assertion scope, validates the full candidate graph, fixes a
    deterministic dependency order and exposes unresolved discourse references as
    runtime descriptors before canonical Integration starts.
    """

    def __init__(
        self,
        validator: CandidateValidator | None = None,
        morphology: Morphology | None = None,
    ) -> None:
        self.validator = validator or CandidateValidator()
        self.morphology = morphology or build_morphology("auto")
        self.temporal = TemporalNormalizer()
        self.quantifier_formalizer = QuantifierFormalizer(self.morphology)

    @staticmethod
    def _actant_variants(assertion: AssertionCandidate, role: ActantRole) -> tuple[ActantCandidate, ...]:
        if assertion.alternatives:
            return tuple(
                actant
                for alternative in assertion.alternatives
                for actant in alternative.actants
                if actant.role is role
            )
        return tuple(actant for actant in assertion.actants if actant.role is role)

    @staticmethod
    def _referent_text(actant: ActantCandidate) -> str:
        # A decomposed NP denotes its head; a dependent pronoun has a separate
        # identity obligation. Never use the last modifier as the whole referent.
        if actant.nominal_relations:
            relation = actant.nominal_relations[0]
            return (relation.head_mention or relation.head_normalized_hint or "").strip()
        return (actant.mention or actant.normalized_hint or "").strip()

    @staticmethod
    def _dependent_candidate(actant: ActantCandidate, index: int) -> ActantCandidate:
        relation = actant.nominal_relations[index]
        return ActantCandidate(
            role=actant.role,
            mention=relation.dependent_mention,
            normalized_hint=relation.dependent_normalized_hint,
            entity_ref=relation.dependent_entity_ref,
            evidence=relation.evidence,
        )

    def _third_person_signature(self, actant: ActantCandidate) -> tuple[str | None, str | None] | None:
        if actant.candidate_ref is not None or actant.composition is not None or actant.proposition is not None:
            return None
        text = self._referent_text(actant)
        if not text:
            return None
        # Source grammar, not a keyword -> semantic operator table.  The closed
        # personal-pronoun class is identified through morphology.
        import re

        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", text)
        if not words:
            return None
        try:
            analyses = tuple(self.morphology.analyze_all(words[-1]))
        except AttributeError:
            item = self.morphology.analyze(words[-1])
            analyses = () if item is None else (item,)
        infos = tuple(
            info
            for info in material_analyses(analyses)
            if info.pos == "NPRO" and "3per" in info.grammemes
        )
        if not infos:
            # Some morphology backends omit the person grammeme but preserve the
            # canonical third-person lemma.  This fallback is still grammatical,
            # not a semantic marker-word rule.
            infos = tuple(
                info
                for info in material_analyses(analyses)
                if info.pos == "NPRO" and info.normal_form.casefold() in {"он", "она", "оно", "они"}
            )
        if not infos:
            return None
        numbers = {str(info.number) for info in infos if info.number}
        genders = {str(info.gender) for info in infos if info.gender}
        number = next(iter(numbers)) if len(numbers) == 1 else None
        gender = next(iter(genders)) if len(genders) == 1 else None
        return number, gender

    def _referent_signature(self, actant: ActantCandidate) -> tuple[str | None, str | None]:
        """Return only grammatical identity constraints for a source mention.

        This helper intentionally does not score semantic plausibility.  It is used
        only to bound the candidate list that a later deterministic rule or semantic
        probe may inspect.
        """

        text = self._referent_text(actant)
        if not text:
            return actant.grammatical_number, None
        import re

        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", text)
        if not words:
            return actant.grammatical_number, None
        try:
            analyses = tuple(self.morphology.analyze_all(words[-1]))
        except AttributeError:
            item = self.morphology.analyze(words[-1])
            analyses = () if item is None else (item,)
        infos = tuple(material_analyses(analyses))
        numbers = {str(info.number) for info in infos if info.number}
        genders = {str(info.gender) for info in infos if info.gender}
        number = actant.grammatical_number or (next(iter(numbers)) if len(numbers) == 1 else None)
        gender = next(iter(genders)) if len(genders) == 1 else None
        return number, gender

    @staticmethod
    def _signatures_compatible(
        pronoun: tuple[str | None, str | None],
        candidate: tuple[str | None, str | None],
    ) -> bool:
        p_number, p_gender = pronoun
        c_number, c_gender = candidate
        if p_number is not None and c_number is not None and p_number != c_number:
            return False
        if p_gender is not None and c_gender is not None and p_gender != c_gender:
            return False
        return True

    def _entity_anchor_candidates(
        self, result: PerceptionResult
    ) -> dict[str, tuple[ActantCandidate, ...]]:
        grouped: dict[str, list[ActantCandidate]] = {}
        for assertion in result.assertions:
            variants = assertion.alternatives or (assertion,)
            for variant in variants:
                for actant in variant.actants:
                    if (
                        actant.entity_ref is None
                        or actant.candidate_ref is not None
                        or actant.composition is not None
                        or actant.proposition is not None
                    ):
                        continue
                    # A pronoun-only local ref is not an identity anchor.
                    if self._third_person_signature(actant) is not None:
                        continue
                    grouped.setdefault(actant.entity_ref, []).append(actant)
        return {key: tuple(values) for key, values in grouped.items()}

    def _rewrite_quantified_actants(
        self, result: PerceptionResult
    ) -> tuple[PerceptionResult, dict[str, QuantifierCandidate]]:
        """Normalize explicit Perception binders and index their local handles.

        Quantifier recognition belongs to :class:`QuantifierFormalizer` before
        Integration.  This boundary deliberately has no words, regular expressions
        or semantic fallbacks: it consumes only typed ``QuantifierCandidate``
        metadata and fails closed when alternatives disagree.
        """

        try:
            rewritten = self.quantifier_formalizer.formalize(result)
        except QuantifierFormalizationError as exc:
            raise CandidateValidationError(str(exc)) from exc

        marks: dict[str, QuantifierCandidate] = {}
        for assertion in rewritten.assertions:
            for variant in (assertion, *assertion.alternatives):
                for actant in variant.actants:
                    quantifier = actant.quantifier
                    if quantifier is None:
                        continue
                    if actant.entity_ref is None:
                        raise CandidateValidationError(
                            f"Quantified actant in {assertion.local_id} has no local handle"
                        )
                    previous = marks.get(actant.entity_ref)
                    if previous is not None and (
                        previous.kind is not quantifier.kind
                        or previous.restriction_lemma != quantifier.restriction_lemma
                    ):
                        raise CandidateValidationError(
                            f"Quantifier handle {actant.entity_ref!r} has inconsistent metadata"
                        )
                    marks.setdefault(actant.entity_ref, quantifier)
        return rewritten, marks

    def _negative_existential_bindings(
        self,
        marks: Mapping[str, QuantifierCandidate],
        *,
        start_at: int,
    ) -> tuple[ExistentialBinding, ...]:
        found = [
            (handle, mark)
            for handle, mark in marks.items()
            if mark.kind is QuantifierKind.NOT_EXISTS
        ]
        return tuple(
            ExistentialBinding(
                entity_ref=handle,
                variable_id=start_at + index,
                negative=True,
                restriction_lemma=mark.restriction_lemma,
            )
            for index, (handle, mark) in enumerate(found)
        )

    def _universal_bindings(
        self,
        marks: Mapping[str, QuantifierCandidate],
        *,
        start_at: int,
    ) -> tuple[UniversalBinding, ...]:
        found = [
            (handle, mark)
            for handle, mark in marks.items()
            if mark.kind in {QuantifierKind.FORALL, QuantifierKind.NOT_FORALL}
        ]
        return tuple(
            UniversalBinding(
                entity_ref=handle,
                variable_id=start_at + index,
                restriction_lemma=mark.restriction_lemma or "",
                negate_quantifier=mark.kind is QuantifierKind.NOT_FORALL,
            )
            for index, (handle, mark) in enumerate(found)
        )

    def _existential_bindings(
        self,
        marks: Mapping[str, QuantifierCandidate],
        *,
        start_at: int = 0,
    ) -> tuple[ExistentialBinding, ...]:
        """Return typed positive existential variables in source traversal order."""

        found = [
            (handle, mark)
            for handle, mark in marks.items()
            if mark.kind is QuantifierKind.EXISTS
        ]
        return tuple(
            ExistentialBinding(
                entity_ref=handle,
                variable_id=start_at + index,
                restriction_lemma=mark.restriction_lemma,
            )
            for index, (handle, mark) in enumerate(found)
        )


    def _bind_cross_turn_existential_pronouns(
        self,
        result: PerceptionResult,
        context: InteractionContext | None,
    ) -> tuple[PerceptionResult, tuple[ExistentialBinding, ...]]:
        """Bind a nominative third-person pronoun to a prior existential scope.

        This is intentionally narrower than general cross-turn coreference.  The
        runtime InteractionContext may carry one-variable existential anchors for
        ``он/она/оно/они``.  Reusing such an anchor rewrites the current staging
        actant to a parser-local handle and carries the previous quantified member
        propositions forward so Integration can assert a *new combined EXISTS*
        scope.  No ``m_ОН`` or fake unknown entity is created.

        If a normal canonical pronoun ref is present, it wins; the two mechanisms
        are never silently merged.  Multi-variable existential continuation is not
        guessed in this slice.
        """

        if context is None or not context.existential_pronoun_anchors:
            return result, ()

        bindings: dict[str, ExistentialBinding] = {}

        def rewrite_actant(actant: ActantCandidate) -> ActantCandidate:
            if (
                actant.entity_ref is not None
                or actant.candidate_ref is not None
                or actant.composition is not None
                or actant.proposition is not None
            ):
                return actant
            if self._third_person_signature(actant) is None:
                return actant
            key = (actant.normalized_hint or actant.mention or "").strip().casefold()
            if not key or context.resolve_pronoun(key) is not None:
                return actant
            anchor = context.resolve_existential_pronoun(key)
            if anchor is None:
                return actant
            handle = f"CTXEX:{key}:{anchor.existential_ref.uid}:{anchor.variable_id}"
            bindings.setdefault(
                handle,
                ExistentialBinding(
                    entity_ref=handle,
                    variable_id=anchor.variable_id,
                    anchor_ref=anchor.existential_ref,
                    anchor_member_refs=anchor.member_refs,
                    restriction_lemma=anchor.restriction_lemma,
                ),
            )
            return replace(actant, entity_ref=handle)

        assertions: list[AssertionCandidate] = []
        for assertion in result.assertions:
            rewritten = replace(
                assertion,
                actants=tuple(rewrite_actant(item) for item in assertion.actants),
            )
            alternatives = tuple(
                replace(alt, actants=tuple(rewrite_actant(item) for item in alt.actants))
                for alt in assertion.alternatives
            )
            assertions.append(replace(rewritten, alternatives=alternatives))

        if not bindings:
            return result, ()
        return replace(result, assertions=tuple(assertions)), tuple(bindings.values())

    def _discourse_refs(
        self,
        result: PerceptionResult,
        context: InteractionContext | None,
    ) -> tuple[DiscourseRef, ...]:
        refs: list[DiscourseRef] = []
        seen: set[tuple[object, ...]] = set()
        anchors = self._entity_anchor_candidates(result)
        for assertion in result.assertions:
            roles = {actant.role for actant in assertion.actants}
            for role in roles:
                variants = self._actant_variants(assertion, role)
                if not variants:
                    continue
                entries = []
                for parent in variants:
                    entries.append((parent, None))
                    entries.extend(
                        (self._dependent_candidate(parent, index), index)
                        for index in range(len(parent.nominal_relations))
                    )
                for actant, relation_index in entries:
                    if actant.entity_ref is not None:
                        continue
                    signature = self._third_person_signature(actant)
                    if signature is None:
                        continue
                    # Existing dialogue anchors resolve at Integration through the
                    # ordinary DeixisResolver.  Do not report those as unresolved.
                    if context is not None:
                        if DeixisResolver().resolve(actant, context) is not None:
                            continue
                    evidence = actant.evidence
                    identity = (
                        assertion.local_id,
                        role.value,
                        relation_index,
                        None if evidence is None else evidence.start,
                        None if evidence is None else evidence.end,
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    compatible_refs = tuple(
                        entity_ref
                        for entity_ref, candidates in anchors.items()
                        if any(
                            self._signatures_compatible(
                                signature, self._referent_signature(candidate)
                            )
                            for candidate in candidates
                        )
                    )
                    refs.append(
                        DiscourseRef(
                            local_id=f"D:{assertion.local_id}:{role.value}:{len(refs)}",
                            mention=(actant.mention or actant.normalized_hint or "").strip(),
                            assertion_id=assertion.local_id,
                            role=role,
                            grammatical_number=signature[0],
                            grammatical_gender=signature[1],
                            source_start=None if evidence is None else evidence.start,
                            source_end=None if evidence is None else evidence.end,
                            candidate_entity_refs=compatible_refs,
                            nominal_relation_index=relation_index,
                        )
                    )
        return tuple(refs)

    def _temporalize(
        self,
        result: PerceptionResult,
        *,
        context: InteractionContext | None,
        source_timestamp: datetime | None,
        experience_timestamp: datetime | None,
    ) -> tuple[PerceptionResult, tuple[UnresolvedTemporalRef, ...]]:
        anchors = TemporalAnchorContext(
            source_timestamp=source_timestamp,
            experience_timestamp=experience_timestamp,
        )
        unresolved: list[UnresolvedTemporalRef] = []

        def rewrite_actant(assertion_id: str, actant: ActantCandidate) -> ActantCandidate:
            if actant.role is not ActantRole.TIME:
                return actant
            if actant.temporal is not None:
                candidate = actant.temporal
            elif actant.candidate_ref is not None or actant.entity_ref is not None or actant.composition is not None or actant.proposition is not None:
                return actant
            else:
                text = actant.lookup_text
                candidate = None if text is None else self.temporal.normalize(text, anchors)
            if candidate is None:
                return actant
            if not candidate.resolved:
                evidence = actant.evidence
                unresolved.append(
                    UnresolvedTemporalRef(
                        local_id=f"TIME:{assertion_id}:{len(unresolved)}",
                        assertion_id=assertion_id,
                        role=ActantRole.TIME,
                        mention=(actant.mention or actant.normalized_hint or "").strip(),
                        reason=candidate.unresolved_reason or "unresolved temporal reference",
                        source_start=None if evidence is None else evidence.start,
                        source_end=None if evidence is None else evidence.end,
                    )
                )
            return replace(actant, temporal=candidate)

        assertions: list[AssertionCandidate] = []
        for assertion in result.assertions:
            base = replace(
                assertion,
                actants=tuple(rewrite_actant(assertion.local_id, a) for a in assertion.actants),
            )
            alternatives = tuple(
                replace(
                    alt,
                    actants=tuple(rewrite_actant(assertion.local_id, a) for a in alt.actants),
                )
                for alt in assertion.alternatives
            )
            assertions.append(replace(base, alternatives=alternatives))
        return replace(result, assertions=tuple(assertions)), tuple(unresolved)

    def bind_discourse_ref(
        self,
        plan: MutationPlan,
        discourse_ref_id: str,
        entity_ref: str,
        *,
        context: InteractionContext | None = None,
    ) -> MutationPlan:
        """Apply an already-decided batch-local coreference binding.

        Selection is deliberately outside this method: deterministic discourse rules
        or a bounded semantic probe may choose one local candidate, then this method
        rewrites the staging graph and re-runs full scoping/validation.  Canonical AH
        is still untouched until ``IntegrationService.integrate_plan``.
        """

        target = next(
            (item for item in plan.candidate_ir.discourse_refs if item.local_id == discourse_ref_id),
            None,
        )
        if target is None:
            raise KeyError(discourse_ref_id)
        if not entity_ref.strip():
            raise ValueError("entity_ref must be non-empty")
        anchors = self._entity_anchor_candidates(plan.perception)
        if entity_ref not in anchors:
            raise ValueError(f"Unknown batch-local entity_ref: {entity_ref}")
        if entity_ref not in target.candidate_entity_refs:
            raise ValueError(
                f"entity_ref {entity_ref!r} violates grammatical constraints for {discourse_ref_id}"
            )

        def matches(actant: ActantCandidate) -> bool:
            if actant.role is not target.role or actant.entity_ref is not None:
                return False
            evidence = actant.evidence
            start = None if evidence is None else evidence.start
            end = None if evidence is None else evidence.end
            return (
                (actant.mention or actant.normalized_hint or "").strip() == target.mention
                and start == target.source_start
                and end == target.source_end
            )

        changed = False
        assertions: list[AssertionCandidate] = []
        for assertion in plan.perception.assertions:
            if assertion.local_id != target.assertion_id:
                assertions.append(assertion)
                continue

            def rewrite_variant(variant: AssertionCandidate) -> AssertionCandidate:
                nonlocal changed
                actants: list[ActantCandidate] = []
                for actant in variant.actants:
                    index = target.nominal_relation_index
                    if index is None and matches(actant):
                        actant = replace(actant, entity_ref=entity_ref)
                        changed = True
                    elif (index is not None and index < len(actant.nominal_relations)
                          and matches(self._dependent_candidate(actant, index))):
                        relations = list(actant.nominal_relations)
                        relations[index] = replace(relations[index], dependent_entity_ref=entity_ref)
                        actant = replace(actant, nominal_relations=tuple(relations))
                        changed = True
                    actants.append(actant)
                return replace(variant, actants=tuple(actants))

            rewritten = rewrite_variant(assertion)
            alternatives = tuple(rewrite_variant(item) for item in assertion.alternatives)
            assertions.append(replace(rewritten, alternatives=alternatives))

        if not changed:
            raise ValueError(f"DiscourseRef {discourse_ref_id} no longer matches staging actant")
        perception = replace(plan.perception, assertions=tuple(assertions))
        return self.prepare(
            perception,
            speaker_ref=plan.speaker_ref,
            forced_domain=plan.forced_domain,
            context=context,
            existing_experience_ref=plan.existing_experience_ref,
            batch_kind=plan.candidate_ir.batch_kind,
            source_ref=plan.candidate_ir.source_ref,
            source_timestamp=plan.candidate_ir.source_timestamp,
            experience_timestamp=plan.candidate_ir.experience_timestamp,
        )

    def prepare_batch(
        self,
        batch: FormalizationBatch,
        *,
        speaker_ref: Ref,
        forced_domain: Domain | None,
        context: InteractionContext | None = None,
        existing_experience_ref: Ref | None = None,
        experience_timestamp: datetime | None = None,
    ) -> MutationPlan:
        merged = merge_formalization_units(batch)
        return self.prepare(
            merged,
            speaker_ref=speaker_ref,
            forced_domain=forced_domain,
            context=context,
            existing_experience_ref=existing_experience_ref,
            batch_kind=batch.batch_kind,
            source_ref=batch.source_ref,
            source_timestamp=batch.source_timestamp,
            experience_timestamp=experience_timestamp,
        )

    def prepare(
        self,
        result: PerceptionResult,
        *,
        speaker_ref: Ref,
        forced_domain: Domain | None,
        context: InteractionContext | None = None,
        existing_experience_ref: Ref | None = None,
        batch_kind: BatchKind = BatchKind.MESSAGE,
        source_ref: str | None = None,
        source_timestamp: datetime | None = None,
        experience_timestamp: datetime | None = None,
    ) -> MutationPlan:
        scoped = apply_speech_act_scoping(result)
        scoped, cross_turn_existentials = self._bind_cross_turn_existential_pronouns(
            scoped, context
        )
        scoped, temporal_refs = self._temporalize(
            scoped, context=context, source_timestamp=source_timestamp,
            experience_timestamp=experience_timestamp,
        )
        scoped, quantifier_marks = self._rewrite_quantified_actants(scoped)
        self.validator.validate(scoped)
        ordered = self.validator.dependency_order(scoped)
        next_variable_id = max(
            (item.variable_id for item in cross_turn_existentials), default=-1
        ) + 1
        fresh_existentials = self._existential_bindings(
            quantifier_marks, start_at=next_variable_id
        )
        next_variable_id += len(fresh_existentials)
        negative_existentials = self._negative_existential_bindings(
            quantifier_marks, start_at=next_variable_id
        )
        next_variable_id += len(negative_existentials)
        universal_bindings = self._universal_bindings(
            quantifier_marks, start_at=next_variable_id
        )
        existential_bindings = cross_turn_existentials + fresh_existentials + negative_existentials
        ir = CandidateIR(
            source_text=scoped.source_text,
            perception=scoped,
            ordered_assertion_ids=tuple(item.local_id for item in ordered),
            discourse_refs=self._discourse_refs(scoped, context),
            existential_bindings=existential_bindings,
            universal_bindings=universal_bindings,
            temporal_refs=temporal_refs,
            batch_kind=batch_kind,
            source_ref=source_ref,
            source_timestamp=source_timestamp,
            experience_timestamp=experience_timestamp,
        )
        return MutationPlan(
            candidate_ir=ir,
            forced_domain=forced_domain,
            speaker_ref=speaker_ref,
            existing_experience_ref=existing_experience_ref,
        )
