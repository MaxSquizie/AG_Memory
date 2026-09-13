from __future__ import annotations

from dataclasses import dataclass

from .contracts import ActantCandidate, AssertionCandidate


@dataclass(frozen=True, slots=True)
class NamingAssertionCandidate(AssertionCandidate):
    """Runtime assertion that assigns a conventional name to an entity.

    The ordinary source shell is retained for evidence only. It may originate from
    nominal predication (``Моё имя — Илья``) or a finite verbal construction
    (``Меня зовут Илья``); Integration consumes this typed assertion as identity
    metadata instead of materializing the surface shell as an ordinary world fact.

    ``owner`` and ``name_value`` are source-grounded perception results. They expose
    no canonical UID: Integration remains the only layer that may resolve the owner
    to USER/SELF/another existing entity and update canonical identity metadata.
    """

    owner: ActantCandidate | None = None
    name_value: str = ""
    name_normalized_hint: str | None = None

    def __post_init__(self) -> None:
        AssertionCandidate.__post_init__(self)
        if self.owner is None:
            raise ValueError("NamingAssertionCandidate.owner is required")
        if not self.name_value.strip():
            raise ValueError("NamingAssertionCandidate.name_value must be non-empty")