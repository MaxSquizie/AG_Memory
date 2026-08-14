from __future__ import annotations

from ah.agent import InteractionContext
from ah.model import ActantRole, Ref
from ah.perception import ActantCandidate


class DeixisResolver:
    _SELF = {"я", "мне", "меня", "мной", "мой", "моя", "моё", "мои"}
    _USER = {"ты", "тебе", "тебя", "тобой", "твой", "твоя", "твоё", "твои"}
    _TODAY = {"сегодня"}
    _HERE = {"здесь", "тут", "там"}

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
        return context.resolve_pronoun(key)
