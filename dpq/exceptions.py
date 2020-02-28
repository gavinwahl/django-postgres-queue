class DpqException(Exception):
    """Base exception for dpq"""


class DpqIncorrectQueue(DpqException):
    """Job placed on incorrect queue."""
