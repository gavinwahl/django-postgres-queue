from django.db import models
from django.db import connection
from django.contrib.postgres.functions import TransactionNow
try:
    from django.db.models import JSONField
except ImportError:
    # django < 3.1
    from django.contrib.postgres.fields import JSONField


class BaseJob(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(default=TransactionNow)
    execute_at = models.DateTimeField(default=TransactionNow)
    priority = models.IntegerField(
        default=0,
        help_text="Jobs with higher priority will be processed first."
    )
    task = models.CharField(max_length=255)
    args = JSONField()
    failed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['-priority', 'created_at']),
        ]
        abstract = True

    def __str__(self):
        return '%s: %s' % (self.id, self.task)

    @classmethod
    def dequeue(cls):
        """
        Claims the first available task and returns it. If there are no
        tasks available, returns None.

        For at-most-once delivery, commit the transaction before
        processing the task. For at-least-once delivery, dequeue and
        finish processing the task in the same transaction.

        To put a job back in the queue, you can just call
        .save(force_insert=True) on the returned object.
        """

        tasks = list(cls.objects.raw(
            """
            DELETE FROM {db_table}
            WHERE id = (
                SELECT id
                FROM {db_table}
                WHERE execute_at <= now()
                  AND failed = false
                ORDER BY priority DESC, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING *;
            """.format(
                db_table=connection.ops.quote_name(cls._meta.db_table),
            ),
        ))
        assert len(tasks) <= 1
        if tasks:
            return tasks[0]
        else:
            return None

    def to_json(self):
        return {
            'id': self.id,
            'created_at': self.created_at,
            'execute_at': self.execute_at,
            'priority': self.priority,
            'task': self.task,
            'args': self.args,
            'failed': self.failed,
        }

class Job(BaseJob):
    pass
