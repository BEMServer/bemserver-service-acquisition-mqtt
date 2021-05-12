"""Service exceptions"""


class ServiceError(Exception):
    """Service error."""


class PayloadDecoderError(Exception):
    """Payload decoder error."""


class PayloadDecoderRegistrationError(PayloadDecoderError):
    """Payload decoder error while registration (saving to database)."""


class PayloadDecoderNotFoundError(PayloadDecoderError):
    """Payload decoder class does not exist."""
