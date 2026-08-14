class IntegrationError(ValueError):
    pass


class CandidateValidationError(IntegrationError):
    pass


class TemplateResolutionError(IntegrationError):
    pass


class EntityResolutionError(IntegrationError):
    pass
