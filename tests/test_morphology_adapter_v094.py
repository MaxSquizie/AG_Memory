from types import SimpleNamespace

from ah.integration.entity_resolver import EntityResolver
from ah.perception.contracts import ActantCandidate
from ah.model import ActantRole
from ah.perception.morphology import Pymorphy3Morphology


class ExplosiveGrammeme(str):
    """Mimic pymorphy grammeme scalars that are not harmless plain strings."""

    _allowed = {"NOUN", "nomn", "sing", "masc", "indc", "anim"}

    def __eq__(self, other):
        if isinstance(other, str) and other not in self._allowed:
            raise ValueError(f"{other!r} is not a valid grammeme")
        return super().__eq__(other)

    __hash__ = str.__hash__


class FakeAnalyzer:
    def parse(self, word):
        tag = SimpleNamespace(
            POS=ExplosiveGrammeme("NOUN"),
            case=ExplosiveGrammeme("nomn"),
            number=ExplosiveGrammeme("sing"),
            gender=ExplosiveGrammeme("masc"),
            mood=ExplosiveGrammeme("indc"),
            animacy=ExplosiveGrammeme("anim"),
            grammemes={ExplosiveGrammeme("NOUN"), ExplosiveGrammeme("sing")},
        )
        return [SimpleNamespace(tag=tag, normal_form="матрос", score=1.0)]


def test_pymorphy_adapter_quarantines_tag_scalar_types():
    morph = object.__new__(Pymorphy3Morphology)
    morph._analyzer = FakeAnalyzer()
    info = morph.analyze_all("матрос")[0]

    for value in (info.pos, info.case, info.number, info.gender, info.mood, info.animacy):
        assert type(value) is str
    assert info.number == "sing"
    assert all(type(value) is str for value in info.grammemes)


def test_actant_candidate_normalizes_non_plain_grammatical_number():
    candidate = ActantCandidate(
        role=ActantRole.SUBJECT,
        mention="матрос",
        grammatical_number=ExplosiveGrammeme("sing"),
    )
    assert candidate.grammatical_number == "sing"
    assert type(candidate.grammatical_number) is str


def test_entity_number_filter_is_safe_for_legacy_grammeme_scalars():
    sing = SimpleNamespace(meta={"grammatical_number": ExplosiveGrammeme("sing")})
    plur = SimpleNamespace(meta={"grammatical_number": "plur"})

    selected = EntityResolver._filter_by_grammatical_number(
        [sing, plur], ExplosiveGrammeme("sing")
    )
    assert selected == [sing]
