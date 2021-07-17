import copy
import datetime
from dataclasses import dataclass
import functools
import logging
import random
from typing import Any, Callable, Dict, Optional, Type, TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from .queue import Queue
    from .models import BaseJob

    DelayFnType = Callable[[int], datetime.timedelta]
    TaskFnType = Callable[[Queue, BaseJob], Any]
else:
    Queue = None
    BaseJob = None
    DelayFnType = None
    TaskFnType = None


def repeat(delay: datetime.timedelta) -> Callable[..., Any]:
    """
    Endlessly repeats a task, every `delay` (a timedelta).

    Under at-least-once delivery, the tasks can not overlap. The next scheduled
    task only becomes visible once the previous one commits.

        @repeat(datetime.timedelta(minutes=5)
        def task(queue, job):
            pass

    This will run `task` every 5 minutes. It's up to you to kick off the first
    task, though.
    """

    def decorator(fn: TaskFnType) -> TaskFnType:
        def inner(queue: Queue, job: BaseJob) -> Any:
            queue.enqueue(
                job.task,
                job.args,
                execute_at=job.execute_at + delay,
                priority=job.priority,
            )
            return fn(queue, job)

        return inner

    return decorator


def exponential_with_jitter(offset: int = 6) -> DelayFnType:
    def delayfn(retries: int) -> datetime.timedelta:
        jitter = random.randrange(-15, 15)
        return datetime.timedelta(seconds=2 ** (retries + offset) + jitter)

    return delayfn


def retry(
    max_retries: int = 0,
    delay_offset_seconds: int = 5,
    delayfn: Optional[DelayFnType] = None,
    Exc: Type[Exception] = Exception,
    on_failure: Optional[
        Callable[[Queue, BaseJob, Any, "JobMeta", Exception], Any]
    ] = None,
    on_success: Optional[Callable[[BaseJob, Any], Any]] = None,
    JobMetaType: Optional[Type["JobMeta"]] = None,
):
    if delayfn is None:
        delayfn = exponential_with_jitter(delay_offset_seconds)
    if JobMetaType is None:
        JobMetaType = JobMeta

    def decorator(fn):
        logger = logging.getLogger(__name__)

        @functools.wraps(fn)
        def inner(queue, job):
            original_job_id = job.args["meta"].setdefault("job_id", job.id)

            try:
                args = copy.deepcopy(job.args)
                with transaction.atomic():
                    result = fn(
                        queue, job, args["func_args"], JobMetaType(**args["meta"])
                    )
            except Exc as e:
                retries = job.args["meta"].get("retries", 0)
                if retries < max_retries:
                    job.args["meta"].update(
                        {"retries": retries + 1, "job_id": original_job_id}
                    )
                    delay = delayfn(retries)
                    job.execute_at += delay
                    job.id = None
                    job.save(force_insert=True)
                    logger.warning(
                        "Task %r failed: %s. Retrying in %s.",
                        job,
                        e,
                        delay,
                        exc_info=True,
                    )
                else:
                    if on_failure:
                        args = copy.deepcopy(job.args)
                        return on_failure(
                            queue,
                            job,
                            args["func_args"],
                            JobMetaType(**args["meta"]),
                            error=e,
                        )
                    logger.exception(
                        "Task %r exceeded its retry limit: %s.", job, e, exc_info=True
                    )
            else:
                if on_success is not None:
                    on_success(job, result)
                return result

        return inner

    return decorator


class AsyncTask:
    """
    A useful standin for celery async tasks.

    Represents an async task, can be used like so:

    @task
    def increment_followers(...): ...

    increment_followers.enqueue(...)
    """

    def __init__(self, queue: Queue, name: str):
        self.queue = queue
        self.name = name

    def enqueue(
        self, args: Dict[str, Any], meta: Optional[Dict[str, Any]] = None
    ) -> BaseJob:
        wrapped_args = {"func_args": args, "meta": meta if meta is not None else {}}
        return self.queue.enqueue(self.name, wrapped_args)

    def __str__(self) -> str:
        return f"AsyncTask({self.queue.notify_channel}, {self.name})"


def task(
    queue: Queue,
    max_retries: int = 0,
    delay_offset_seconds: int = 5,
    on_failure: Optional[Callable[..., Any]] = None,
    JobMetaType: Optional[Type["JobMeta"]] = None,
) -> Callable[..., Any]:
    """
    Decorator to register the task to the queue.

    @task(queuename, max_retries=5)

    delay_offset_seconds:
        5th retry will take half hour at 5; delay (seconds) = 2 ** (retry + offset)
    """
    if JobMetaType is None:
        JobMetaType = JobMeta

    def register(fn: Callable[..., Any]) -> AsyncTask:
        name = fn.__name__
        assert name not in queue.tasks
        queue.tasks[name] = retry(
            max_retries=max_retries,
            delay_offset_seconds=delay_offset_seconds,
            on_failure=on_failure,
            JobMetaType=JobMetaType,
        )(fn)
        return AsyncTask(queue, name)

    return register


@dataclass
class JobMeta:
    job_id: int
    retries: int = 0
