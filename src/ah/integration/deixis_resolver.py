from __future__ import annotations

from ah.agent import InteractionContext
import re
from ah.model import ActantRole, Ref
from ah.perception import ActantCandidate


class DeixisResolver:
    _SELF = {
        "я", "мне", "меня", "мной",
        "мой", "моя", "моё", "мое", "мои", "моего", "моей", "моему",
        "моим", "моими", "моих", "мою",
    }
    _USER = {
        "ты", "тебе", "тебя", "тобой",
        "твой", "твоя", "твоё", "твое", "твои", "твоего", "твоей", "твоему",
        "твоим", "твоими", "твоих", "твою",
    }
    _TODAY = {"сегодня"}
    _HERE = {"здесь", "тут", "там"}

    # Russian third-person oblique/possessive forms are a closed grammatical
    # paradigm. InteractionContext intentionally stores only nominative anchors;
    # this table projects an oblique surface back to the compatible nominatives.
    # A resolution is accepted only when the available anchors collapse to one
    # canonical Ref, so syncretic forms such as ``его``/``им`` never force gender.
    _OBLIQUE_TO_NOMINATIVE = {
        "его": ("он", "оно"),
        "него": ("он", "оно"),
        "ему": ("он", "оно"),
        "нему": ("он", "оно"),
        "им": ("он", "оно", "они"),
        "ним": ("он", "оно", "они"),
        "нем": ("он", "оно"),
        "нём": ("он", "оно"),
        "ее": ("она",),
        "её": ("она",),
        "нее": ("она",),
        "неё": ("она",),
        "ей": ("она",),
        "ней": ("она",),
        "ею": ("она",),
        "нею": ("она",),
        "их": ("они",),
        "них": ("они",),
        "ими": ("они",),
        "ними": ("они",),
    }

    def resolve(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        *,
        first_person_ref: Ref | None = None,
        second_person_ref: Ref | None = None,
    ) -> Ref | None:
        text = candidate.lookup_text
        if not text:
            return None
        key = text.casefold()

        first = first_person_ref if first_person_ref is not None else context.user_ref
        second = second_person_ref if second_person_ref is not None else context.self_ref
        if key in self._SELF and first is not None:
            return first
        if key in self._USER and second is not None:
            return second
        if candidate.role is ActantRole.TIME and key in self._TODAY:
            return context.now_ref
        if candidate.role is ActantRole.LOCATION and key in self._HERE:
            return context.active_location_ref

        direct = context.resolve_pronoun(key)
        if direct is not None:
            return direct

        # Actant mentions can retain a governing preposition (``у него``). Use the
        # final lexical word only for this closed pronoun paradigm; ordinary noun
        # resolution remains the responsibility of EntityResolver.
        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", key)
        pronoun_key = words[-1].replace("ё", "е") if words else key.replace("ё", "е")
        candidates = self._OBLIQUE_TO_NOMINATIVE.get(pronoun_key)
        if candidates is None:
            return None
        refs = {
            ref for nominative in candidates
            if (ref := context.resolve_pronoun(nominative)) is not None
        }
        return next(iter(refs)) if len(refs) == 1 else None
