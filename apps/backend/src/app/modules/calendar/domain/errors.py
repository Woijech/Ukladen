class InvalidEventInput(ValueError):
    """Supplied event data violates personal calendar event rules."""


class EventNotFound(Exception):
    """The requested event does not exist or is owned by another user."""
