from typing import Any

from django.contrib.auth.models import Group
from django.test import TestCase

from pgq.decorators import task, JobMeta
from pgq.models import Job
from pgq.queue import AtLeastOnceQueue, AtMostOnceQueue, Queue


class PgqDecoratorsTests(TestCase):
    def test_using_task_decorator_to_add_to_queue(self) -> None:
        """
        The task decorator makes a celery-like task object
        which can be used for adding tasks to the queue and registering
        the task to the queue.
        """
        queue = AtLeastOnceQueue(tasks={})

        @task(queue)
        def demotask(queue: Queue, job: Job, args: Any, meta: JobMeta) -> int:
            return job.id

        demotask.enqueue({"count": 5})
        self.assertIn("demotask", queue.tasks)
        queue.run_once()

    def test_atleastonce_retry_during_database_failure(self) -> None:
        """
        Force a database error in the task. Check that it was retried.
        """

        queue = AtLeastOnceQueue(tasks={})

        @task(queue, max_retries=2)
        def failuretask(queue: Queue, job: Job, args: Any, meta: JobMeta) -> None:
            # group has max 150 chars for its name.
            Group.objects.create(name="!" * 151)
            return None

        failuretask.enqueue({})
        originaljob = Job.objects.all()[0]

        queue.run_once()

        retryjob = Job.objects.all()[0]
        self.assertNotEqual(originaljob.id, retryjob.id)
        self.assertEqual(retryjob.args["meta"]["retries"], 1)
