from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Job
else:
    Job = None


class DpqException(Exception):
    """Base exception for dpq"""

    job: Optional[Job] = None

    def __init__(self, job: Optional[Job] = None):
        self.job = job


class DpqIncorrectQueue(DpqException):
    """Job placed on incorrect queue."""


class DpqNoDefinedQueue(DpqException):
    """There is no queue to work."""
