from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Job
else:
    Job = None


class PgqException(Exception):
    """Base exception for pgq"""

    job: Optional[Job] = None

    def __init__(self, job: Optional[Job] = None):
        self.job = job


class PgqIncorrectQueue(PgqException):
    """Job placed on incorrect queue."""


class PgqNoDefinedQueue(PgqException):
    """There is no queue to work."""
