from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ah.agent import InteractionContext
from ah.perception import PerceptionResult
from ah.perception.query_semantics import EntityIdentityQueryCandidate

from .contracts import IntegrationCommit
from .identity_naming_service import CanonicalNamingIntegrationService


class IdentityQueryIntegrationService(CanonicalNamingIntegrationService):
    """Keep entity-identity questions runtime-only until deterministic inference.

    An identity question may be surfaced by a copular shell, but asking it is not
    evidence for a world proposition and must not create/expand a canonical T for
    that shell.  Perception has already typed the question as an
    ``EntityIdentityQueryCandidate``.  This adapter detaches it before ordinary
    Integration, preserves the raw H QUERY occurrence, and returns it through the
    existing ``unresolved_queries`` runtime channel for GoalCompiler.
    """

    @staticmethod
    def _identity_queries(result: PerceptionResult) -> tuple[EntityIdentityQueryCandidate, ...]:
        return tuple(
            item
            for item in result.queries
            if isinstance(item, EntityIdentityQueryCandidate)
        )

    def template_requests(self, result: PerceptionResult):
        filtered = replace(
            result,
            queries=tuple(
                item
                for item in result.queries
                if not isinstance(item, EntityIdentityQueryCandidate)
            ),
        )
        return super().template_requests(filtered)

    def integrate_external(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        source_timestamp: datetime | None = None,
    ) -> IntegrationCommit:
        identity_queries = self._identity_queries(result)
        if not identity_queries:
            return super().integrate_external(
                result,
                context,
                source_timestamp=source_timestamp,
            )

        detached_ids = {
            item.local_id
            for item in identity_queries
            if item.local_id is not None
        }
        self._assert_detachable(result, detached_ids)
        ordinary = replace(
            result,
            queries=tuple(
                item
                for item in result.queries
                if not isinstance(item, EntityIdentityQueryCandidate)
            ),
        )
        commit = super().integrate_external(
            ordinary,
            context,
            source_timestamp=source_timestamp,
        )

        # The parent saw the detached version and therefore cannot know this H turn
        # was a QUERY.  Restore pragmatic source kinds from the original perception
        # without creating a semantic proposition for the copular shell.
        with self.core.transaction() as tx:
            self._restore_experience_kinds(tx, commit, result)

        return replace(
            commit,
            unresolved_queries=commit.unresolved_queries + identity_queries,
        )
