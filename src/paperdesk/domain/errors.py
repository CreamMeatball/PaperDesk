class ReaderError(Exception):
    """Base error. `status` and `code` let the web layer map errors without knowing each type."""

    status = 400
    code = "bad_request"


class InvalidInput(ReaderError):
    status = 400
    code = "invalid_input"


class NotFound(ReaderError):
    status = 404
    code = "not_found"


class ProviderUnavailable(ReaderError):
    status = 503
    code = "provider_unavailable"


class ProviderFailed(ReaderError):
    status = 502
    code = "provider_failed"
