from typing import Any

from django.test import TestCase

from pgq.decorators import task, JobMeta
from pgq.models import Job
from pgq.queue import AtLeastOnceQueue, Queue


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
