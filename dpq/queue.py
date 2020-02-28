import abc
import datetime
import logging
import select
import time
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from django.db import connection, transaction

from .exceptions import DpqException
from .models import Job, DEFAULT_QUEUE_NAME


class Queue(metaclass=abc.ABCMeta):
    job_model = Job
    logger = logging.getLogger(__name__)

    def __init__(
        self,
        tasks: Dict[str, Callable[["Queue", Job], Any]],
        notify_channel: Optional[str] = None,
        queue: str = DEFAULT_QUEUE_NAME,
    ) -> None:
        self.tasks = tasks
        self.notify_channel = notify_channel
        self.queue = queue

    @abc.abstractmethod
    def run_once(self) -> Optional[Tuple[Job, Any]]:
        raise NotImplementedError

    def run_job(self, job: Job) -> Any:
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
        self,
        task: str,
        args: Optional[Dict[str, Any]] = None,
        execute_at: Optional[datetime.datetime] = None,
        priority: Optional[int] = None,
    ) -> Job:
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
            self.notify(job)
        return job

    def listen(self) -> None:
        assert self.notify_channel, "You must set a notify channel in order to listen."
        with connection.cursor() as cur:
            cur.execute('LISTEN "{}";'.format(self.notify_channel))

    def wait(self, timeout: int = 30) -> Sequence[str]:
        connection.connection.poll()
        notifies = self.filter_notifies()
        if notifies:
            return notifies

        select.select([connection.connection], [], [], timeout)
        connection.connection.poll()
        return self.filter_notifies()

    def filter_notifies(self) -> Sequence[str]:
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

    def notify(self, job: Job) -> None:
        with connection.cursor() as cur:
            cur.execute('NOTIFY "{}", %s;'.format(self.notify_channel), [str(job.pk)])

    def _run_once(
        self, exclude_ids: Optional[Sequence[int]] = None
    ) -> Optional[Tuple[Job, Any]]:
        job = self.job_model.dequeue(
            exclude_ids=exclude_ids, queue=self.queue, tasks=list(self.tasks)
        )
        if job:
            self.logger.debug(
                "Claimed %r.", job, extra={"data": {"job": job.to_json(),}}
            )
            try:
                return job, self.run_job(job)
            except Exception as e:
                # Add job info to exception to be accessible for logging.
                raise DpqException(job=job) from e
        else:
            return None


class AtMostOnceQueue(Queue):
    def run_once(
        self, exclude_ids: Optional[Sequence[int]] = None
    ) -> Optional[Tuple[Job, Any]]:
        assert not connection.in_atomic_block
        return self._run_once(exclude_ids=exclude_ids)


class AtLeastOnceQueue(Queue):
    @transaction.atomic
    def run_once(
        self, exclude_ids: Optional[Sequence[int]] = None
    ) -> Optional[Tuple[Job, Any]]:
        return self._run_once(exclude_ids=exclude_ids)
