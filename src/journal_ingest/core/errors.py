"""Custom exceptions for journal ingestion."""


class ParserConfidenceError(RuntimeError):
    """Raised when no parser reports sufficient confidence."""


class ValidationError(ValueError):
    """Raised when validation checks fail."""
