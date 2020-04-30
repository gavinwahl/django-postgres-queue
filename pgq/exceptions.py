from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import BaseJob
else:
    BaseJob = None


class PgqException(Exception):
    """Base exception for pgq"""

    job: Optional[BaseJob] = None

    def __init__(self, job: Optional[BaseJob] = None):
        self.job = job


class PgqIncorrectQueue(PgqException):
    """Job placed on incorrect queue."""


class PgqNoDefinedQueue(PgqException):
    """There is no queue to work."""
