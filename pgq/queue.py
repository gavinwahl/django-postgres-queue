import abc
import contextlib
import datetime
import logging
import select
import time
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Generic,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    TYPE_CHECKING,
)

from django.db import connection, transaction

from .exceptions import PgqException
from .models import BaseJob, Job, DEFAULT_QUEUE_NAME


_Job = TypeVar("_Job", bound=BaseJob)
# mypy doesn't support binding to BaseQueue[_Job] and may never do so...
if TYPE_CHECKING:
    _Self = TypeVar("_Self", bound="BaseQueue"[Any])
else:
    _Self = None


@contextlib.contextmanager
def maybe_atomic(is_atomic: bool):
    if is_atomic:
        with transaction.atomic():
            yield
    else:
        yield


class BaseQueue(Generic[_Job], metaclass=abc.ABCMeta):
    job_model: Type[_Job]
    logger = logging.getLogger(__name__)

    def __init__(
        self: _Self,
        tasks: Dict[str, Callable[[_Self, _Job], Any]],
        notify_channel: Optional[str] = None,
        queue: str = DEFAULT_QUEUE_NAME,
    ) -> None:
        self.tasks = tasks
        self.notify_channel = notify_channel
        self.queue = queue

    @abc.abstractmethod
    def run_once(
        self, exclude_ids: Optional[Iterable[int]] = None
    ) -> Optional[Tuple[_Job, Any]]:
        """Get a job from the queue and run it.

        Returns:
            - if a job was run: the Job obj run (now removed from the db) and
              it's returned values.
            - If there was no job, return None.

        If a job fails, ``PgqException`` is raised with the job object that
        failed stored in it.
        """
        raise NotImplementedError

    def run_job(self: _Self, job: _Job) -> Any:
        """Execute job, return the output of job."""
        task = self.tasks[job.task]
        start_time = time.time()
        retval = task(self, job)
        self.logger.info(
            "Processing %r took %0.4f seconds. Task returned %r.",
            job,
            time.time() - start_time,
            retval,
            extra={"data": {"job": job.to_json(), "retval": retval,}},
        )
        return retval

    def enqueue(
        self: _Self,
        task: str,
        args: Optional[Dict[str, Any]] = None,
        execute_at: Optional[datetime.datetime] = None,
        priority: Optional[int] = None,
    ) -> _Job:
        assert task in self.tasks
        if args is None:
            args = {}

        kwargs: Dict[str, Any] = {"task": task, "args": args, "queue": self.queue}
        if execute_at is not None:
            kwargs["execute_at"] = execute_at
        if priority is not None:
            kwargs["priority"] = priority

        job = self.job_model.objects.create(**kwargs)
        if self.notify_channel:
            self.notify()
        return job

    def bulk_enqueue(
        self: _Self,
        task: str,
        kwargs_list: Sequence[Dict[str, Any]],
        batch_size: Optional[int] = None,
    ) -> List[_Job]:

        assert task in self.tasks

        jobs = self.job_model.objects.bulk_create(
            [
                self.job_model(task=task, queue=self.queue, **kwargs)
                for kwargs in kwargs_list
            ],
            batch_size=batch_size,
        )

        if self.notify_channel:
            self.notify()
        return jobs

    def listen(self) -> None:
        assert self.notify_channel, "You must set a notify channel in order to listen."
        with connection.cursor() as cur:
            cur.execute('LISTEN "{}";'.format(self.notify_channel))

    def wait(self: _Self, timeout: int = 30) -> Sequence[str]:
        connection.connection.poll()
        notifies = self.filter_notifies()
        if notifies:
            return notifies

        select.select([connection.connection], [], [], timeout)
        connection.connection.poll()
        return self.filter_notifies()

    def filter_notifies(self: _Self) -> Sequence[str]:
        notifies = [
            i
            for i in connection.connection.notifies
            if i.channel == self.notify_channel
        ]
        connection.connection.notifies = [
            i
            for i in connection.connection.notifies
            if i.channel != self.notify_channel
        ]
        return notifies

    def notify(self: _Self) -> None:
        with connection.cursor() as cur:
            cur.execute('NOTIFY "%s";' % self.notify_channel)

    def _run_once(
        self: _Self, exclude_ids: Optional[Iterable[int]] = None, is_atomic: bool = True
    ) -> Optional[Tuple[_Job, Any]]:
        """Get a job from the queue and run it.

        Implements the same function signature as ``run_once()``

        Returns:
            - if a job was run: the Job obj run (now removed from the db) and
              it's returned values.
            - If there was no job, return None.

        If a job fails, ``PgqException`` is raised with the job object that
        failed stored in it.
        """
        job = None
        try:
            with maybe_atomic(is_atomic):
                job = self.job_model.dequeue(
                    exclude_ids=exclude_ids, queue=self.queue, tasks=list(self.tasks)
                )
                if job:
                    self.logger.debug(
                        "Claimed %r.", job, extra={"data": {"job": job.to_json(),}}
                    )
                    return job, self.run_job(job)
                else:
                    return None
        except Exception as e:
            # Add job info to exception to be accessible for logging.
            raise PgqException(job=job) from e


class Queue(BaseQueue[Job]):
    job_model = Job


class AtMostOnceQueue(Queue):
    def run_once(
        self, exclude_ids: Optional[Iterable[int]] = None
    ) -> Optional[Tuple[Job, Any]]:
        assert not connection.in_atomic_block
        return self._run_once(exclude_ids=exclude_ids, is_atomic=False)


class AtLeastOnceQueue(Queue):
    def run_once(
        self, exclude_ids: Optional[Iterable[int]] = None
    ) -> Optional[Tuple[Job, Any]]:
        return self._run_once(exclude_ids=exclude_ids, is_atomic=True)
