class IntegrationError(ValueError):
    pass


class CandidateValidationError(IntegrationError):
    pass


class TemplateResolutionError(IntegrationError):
    pass


class EntityResolutionError(IntegrationError):
    pass


class UnresolvedDiscourseReferenceError(IntegrationError):
    """A staging DiscourseRef reached the canonical write boundary unresolved."""

    def __init__(self, refs) -> None:
        self.refs = tuple(refs)
        labels = ", ".join(
            f"{item.assertion_id}.{item.role.value}={item.mention!r}" for item in self.refs
        )
        super().__init__(
            "Unresolved discourse reference(s) must be clarified/resolved before canonical commit: "
            + labels
        )


class UnresolvedTemporalReferenceError(IntegrationError):
    """A relative TIME staging reference reached commit without an anchor."""

    def __init__(self, refs) -> None:
        self.refs = tuple(refs)
        labels = ", ".join(
            f"{item.assertion_id}.{item.role.value}={item.mention!r}" for item in self.refs
        )
        super().__init__(
            "Unresolved temporal reference(s) require an explicit/source/experience anchor before canonical commit: "
            + labels
        )
