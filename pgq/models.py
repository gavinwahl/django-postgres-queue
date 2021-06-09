from typing import Any, Dict, Iterable, Optional, Sequence, Type, TypeVar

from django.db import models
from django.db import connection
from django.contrib.postgres.functions import TransactionNow

try:
    from django.db.models import JSONField
except ImportError:
    from django.contrib.postgres.fields import JSONField  # type: ignore[misc]

DEFAULT_QUEUE_NAME = "default"


_Self = TypeVar("_Self", bound="BaseJob")


class BaseJob(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(default=TransactionNow)
    execute_at = models.DateTimeField(default=TransactionNow)
    priority = models.IntegerField(
        default=0, help_text="Jobs with higher priority will be processed first."
    )
    task = models.CharField(max_length=255)
    args = JSONField()
    queue = models.CharField(
        max_length=32,
        default=DEFAULT_QUEUE_NAME,
        help_text="Use a unique name to represent each queue.",
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["-priority", "created_at"]),
            models.Index(fields=["queue"]),
        ]

    def __str__(self) -> str:
        return "%s: %s" % (self.id, self.task)

    @classmethod
    def dequeue(
        cls: Type[_Self],
        exclude_ids: Optional[Iterable[int]] = None,
        tasks: Optional[Sequence[str]] = None,
        queue: str = DEFAULT_QUEUE_NAME,
    ) -> Optional[_Self]:
        """
        Claims the first available task and returns it. If there are no
        tasks available, returns None.

        exclude_ids: Iterable[int] - excludes jobs with these ids
        tasks: Optional[Sequence[str]] - filters by jobs with these tasks.

        For at-most-once delivery, commit the transaction before
        processing the task. For at-least-once delivery, dequeue and
        finish processing the task in the same transaction.

        To put a job back in the queue, you can just call
        .save(force_insert=True) on the returned object.
        """

        WHERE = "WHERE execute_at <= now() AND NOT id = ANY(%s) AND queue = %s"
        args = [[] if exclude_ids is None else list(exclude_ids), queue]
        if tasks is not None:
            WHERE += " AND TASK = ANY(%s)"
            args.append(tasks)

        jobs = list(
            cls.objects.raw(
                """
            DELETE FROM {db_table}
            WHERE id = (
                SELECT id
                FROM {db_table}
                {WHERE}
                ORDER BY priority DESC, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING *;
            """.format(
                    db_table=connection.ops.quote_name(cls._meta.db_table), WHERE=WHERE
                ),
                args,
            )
        )
        assert len(jobs) <= 1
        if jobs:
            return jobs[0]
        else:
            return None

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "execute_at": self.execute_at,
            "priority": self.priority,
            "queue": self.queue,
            "task": self.task,
            "args": self.args,
        }


class Job(BaseJob):
    """pgq builtin Job model"""
