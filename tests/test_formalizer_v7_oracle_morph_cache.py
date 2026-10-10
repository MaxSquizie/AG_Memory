"""Only pure dictionary work is shared between isolated oracle cases."""
from dataclasses import FrozenInstanceError

import pytest

from ah.formalizer.state import MorphVariant
from tools import formalizer_v7_native_binding as native


@pytest.fixture
def pure_factory(monkeypatch):
    class Provider:
        instances = []

        def __init__(self):
            self.calls = []
            self.instances.append(self)

        def analyze(self, token):
            self.calls.append(token)
            return (
                MorphVariant(token, "NOUN", frozenset({"nom"}), score=0.3),
                MorphVariant(token, "NOUN", frozenset({"acc"}), score=0.7),
            )

    monkeypatch.setattr(native, "_oracle_morph_scope", None)
    monkeypatch.setattr(native, "MorphProvider", Provider)
    monkeypatch.setattr(native, "_DEFAULT_MORPH_PROVIDER", Provider)
    return Provider


def test_preserves_every_linked_variant_and_exact_token_key(pure_factory):
    config = {"provider": "recorded"}
    morph = native._oracle_morph(config)
    first = morph.analyze("Иван")
    assert morph.analyze("Иван") is first
    assert [v.cases for v in first] == [frozenset({"nom"}), frozenset({"acc"})]
    assert [v.score for v in first] == [0.3, 0.7]
    assert morph.analyze("иван") != first
    assert pure_factory.instances[0].calls == ["Иван", "иван"]
    with pytest.raises(FrozenInstanceError):
        first[0].lemma = "changed"


def test_same_run_reuses_dictionary_but_new_config_invalidates(pure_factory):
    config = {"provider": "recorded"}
    first = native._oracle_morph(config)
    first.analyze("книга")
    assert native._oracle_morph(config) is first
    other_run = native._oracle_morph(dict(config))
    assert other_run is not first
    other_run.analyze("книга")
    assert len(pure_factory.instances) == 2
    assert [p.calls for p in pure_factory.instances] == [["книга"], ["книга"]]


def test_cache_is_bounded_and_eviction_never_drops_variants(pure_factory):
    morph = native._oracle_morph({})
    first = morph.analyze("0")
    for i in range(1, 4097):
        morph.analyze(str(i))
    assert morph.analyze.cache_info().currsize == 4096
    assert morph.analyze("0") == first
    assert pure_factory.instances[0].calls.count("0") == 2


def test_patched_provider_keeps_per_call_construction_and_purity_contract(pure_factory, monkeypatch):
    config = {}
    old = native._oracle_morph(config)

    class Stateful:
        pass

    monkeypatch.setattr(native, "MorphProvider", Stateful)
    assert native._oracle_morph(config) is not native._oracle_morph(config)
    assert native._oracle_morph_scope is None
    monkeypatch.setattr(native, "MorphProvider", pure_factory)
    assert native._oracle_morph(config) is not old


def test_shared_morphology_does_not_share_case_ah(pure_factory, tmp_path):
    from tools.formalizer_v7_extended_binding import Session
    from ah.formalizer.graph_ops import ensure_entity

    config = {}
    a = Session([], tmp_path / "a.log")
    b = Session([], tmp_path / "b.log")
    assert a.core.store is not b.core.store
    ensure_entity(a.core, {"uid": "only-case-a", "name": "entity"})
    assert a.core.store.has_uid("only-case-a")
    assert not b.core.store.has_uid("only-case-a")
    assert native._oracle_morph(config) is native._oracle_morph(config)


def test_real_default_cache_matches_whole_dictionary_parses(monkeypatch):
    monkeypatch.setattr(native, "_oracle_morph_scope", None)
    direct = native.MorphProvider()
    cached = native._oracle_morph({})
    for token in ("Иван", "Ивана", "стали", "вороны", "почтой", "неизвестноеслово", "."):
        assert cached.analyze(token) == direct.analyze(token)
