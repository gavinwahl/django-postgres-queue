from django.test import TestCase

from .queue import AtLeastOnceQueue


def demotask(queue, job):
    return job.id


class DpqMultipleQueueTests(TestCase):
    def test_multiple_queues_mutually_exclusive_tasks(self):
        """
        Test for a bug where defining multiple queues
        with exclusive tasks raises KeyError when a worker for one queue
        gets a job meant for a different queue
        """

        queue1 = AtLeastOnceQueue(tasks={"task1": demotask})
        queue2 = AtLeastOnceQueue(tasks={"task2": demotask})

        queue1.enqueue("task1", {"count": 5})

        queue2.run_once()
