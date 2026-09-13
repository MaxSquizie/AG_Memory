from __future__ import annotations

from dataclasses import dataclass

from .contracts import ActantCandidate, AssertionCandidate


@dataclass(frozen=True, slots=True)
class NamingAssertionCandidate(AssertionCandidate):
    """Runtime assertion that assigns a conventional name to an entity.

    The ordinary nominal-predication shell is retained for source evidence only;
    Integration consumes this typed assertion as identity metadata instead of
    materializing the shell as a world proposition such as ``Илья(STATE=имя)``.
    ``owner`` is a source-grounded deictic/referential candidate and ``name_value``
    is the already parsed nominal predicate surface. No canonical UID is exposed.
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
