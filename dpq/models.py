from django.db import models
from django.contrib.postgres.functions import TransactionNow
from django.contrib.postgres.fields import JSONField


class Job(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(default=TransactionNow)
    execute_at = models.DateTimeField(default=TransactionNow)
    priority = models.IntegerField(
        default=0,
        help_text="Jobs with higher priority will be processed first."
    )
    task = models.CharField(max_length=255)
    args = JSONField()

    class Meta:
        indexes = [
            models.Index(fields=['-priority', 'created_at']),
        ]

    def __str__(self):
        return '%s: %s' % (self.id, self.task)

    @classmethod
    def dequeue(cls, exclude_ids=[]):
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
            DELETE FROM dpq_job
            WHERE id = (
                SELECT id
                FROM dpq_job
                WHERE execute_at <= now()
                  AND NOT id = ANY(%s)
                ORDER BY priority DESC, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING *;
            """,
            [list(exclude_ids)]
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
        }
