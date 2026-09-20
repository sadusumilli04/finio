class FinioError(Exception):
    """Base class for errors the API maps to HTTP responses."""


class NotFoundError(FinioError):
    pass


class ForbiddenError(FinioError):
    pass


class ConflictError(FinioError):
    pass


class ValidationFailed(FinioError):
    pass
