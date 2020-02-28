from django.test import TestCase

from .models import Job, DEFAULT_QUEUE_NAME
from .queue import AtLeastOnceQueue, Queue


def demotask(queue: Queue, job: Job) -> int:
    return job.id


class PgqQueueTests(TestCase):
    def test_create_job_on_queue(self) -> None:
        """
        Creates a basic queue with a name, and puts the job onto the queue.
        """
        NAME = "machine_a"
        queue = AtLeastOnceQueue(tasks={"demotask": demotask}, queue=NAME)

        queue.enqueue("demotask", {"count": 5})
        job = Job.dequeue(queue=queue.queue)
        if job is None:
            self.fail()
        self.assertEqual(job.args["count"], 5)
        self.assertEqual(job.queue, NAME)

    def test_job_contained_to_queue(self) -> None:
        """
        Test that a job added to one queue won't be visible on another queue.
        """
        NAME = "machine_a"
        queue = AtLeastOnceQueue(tasks={"demotask": demotask}, queue=NAME)

        NAME2 = "machine_b"
        queue2 = AtLeastOnceQueue(tasks={"demotask": demotask}, queue=NAME2)

        queue.enqueue("demotask", {"count": 5})
        job = Job.dequeue(queue=queue2.queue)
        self.assertEqual(job, None)

        job = Job.dequeue(queue=queue.queue)
        self.assertNotEqual(job, None)

    def test_job_legacy_queues(self) -> None:
        """
        Test jobs can be added without a queue name defined.
        """
        queue = AtLeastOnceQueue(tasks={"demotask": demotask})

        queue.enqueue("demotask", {"count": 5})
        job = Job.dequeue(queue=queue.queue)
        if job is None:
            self.fail()
        self.assertEqual(job.args["count"], 5)
        self.assertEqual(job.queue, DEFAULT_QUEUE_NAME)

    def test_same_name_queues_can_fetch_tasks(self) -> None:
        NAME = "machine_a"
        queue = AtLeastOnceQueue(tasks={"demotask": demotask}, queue=NAME)

        queue2 = AtLeastOnceQueue(tasks={"demotask": demotask}, queue=NAME)

        queue.enqueue("demotask", {"count": 5})
        job = Job.dequeue(queue=queue2.queue)
        # job is dequeued..
        self.assertNotEqual(job, None)

        # now the job should be gone...
        job = Job.dequeue(queue=queue.queue)
        self.assertEqual(job, None)
