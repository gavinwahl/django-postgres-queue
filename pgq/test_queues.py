from django.test import TestCase

from .models import Job
from .queue import AtLeastOnceQueue, Queue


def demotask(queue: Queue, job: Job) -> int:
    return job.id


class PgqMultipleQueueTests(TestCase):
    def test_multiple_queues_mutually_exclusive_tasks(self) -> None:
        """
        Test for a bug where defining multiple queues
        with exclusive tasks raises KeyError when a worker for one queue
        gets a job meant for a different queue
        """

        queue1 = AtLeastOnceQueue(tasks={"task1": demotask, "task3": demotask})
        queue2 = AtLeastOnceQueue(tasks={"task2": demotask, "task4": demotask})

        queue1.enqueue("task1", {"count": 5})

        queue2.run_once()

    def test_dequeue_without_tasks(self) -> None:
        """
        Check that a job can dequeue without any tasks given.
        """
        Job.dequeue()
