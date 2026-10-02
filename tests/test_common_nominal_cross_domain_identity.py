from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration.entity_resolver import EntityResolver, ExistingEntity
from ah.model import ActantRole, Domain, Property
from ah.perception import ActantCandidate
from ah.perception.morphology import MorphInfo


class _CommonNounMorphology:
    def analyze_all(self, word: str):
        return (
            MorphInfo(
                normal_form="ворона",
                pos="NOUN",
                case="accs",
                number="sing",
                gender="femn",
                grammemes=frozenset({"NOUN"}),
                score=1.0,
            ),
        )

    def analyze(self, word: str):
        return self.analyze_all(word)[0]


def _crow(core: AHCore, domain: Domain):
    return core.add_entity(
        domain,
        {"name": Property("name", "ворона", "str")},
        {"grammatical_number": "sing"},
    )


def test_common_noun_reuses_c_identity_inside_personalized_fact() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    c_crow = _crow(core, Domain.C)

    resolver = EntityResolver(core)
    resolver.morphology = _CommonNounMorphology()
    candidate = ActantCandidate(
        ActantRole.OBJECT,
        mention="ворону",
        normalized_hint="ворона",
        grammatical_number="sing",
    )

    resolved = resolver.resolve(
        candidate,
        InteractionContext(),
        preferred_domain=Domain.P,
    )

    assert isinstance(resolved, ExistingEntity)
    assert resolved.ref.uid == c_crow.uid


def test_common_noun_prefers_c_anchor_over_legacy_p_duplicate() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    c_crow = _crow(core, Domain.C)
    _crow(core, Domain.P)  # legacy duplicate produced by the old domain-locked path

    resolver = EntityResolver(core)
    resolver.morphology = _CommonNounMorphology()
    candidate = ActantCandidate(
        ActantRole.OBJECT,
        mention="ворону",
        normalized_hint="ворона",
        grammatical_number="sing",
    )

    # Association/query resolution often has no preferred semantic domain.  The
    # legacy C/P duplicate must not become a fake clarification for a common noun.
    resolved = resolver.resolve(candidate, InteractionContext())

    assert isinstance(resolved, ExistingEntity)
    assert resolved.ref.uid == c_crow.uid
