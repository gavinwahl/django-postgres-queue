from django.test import TestCase

from .models import Job
from .queue import AtLeastOnceQueue


class DpqQueueTests(TestCase):
    def demotask(queue, job):
        return job.id

    def test_create_job_on_queue(self):
        """
        Creates a basic queue with a name, and puts the job onto the queue.
        """
        NAME = "machine_a"
        queue = AtLeastOnceQueue(tasks=["demotask"], queue=NAME)

        queue.enqueue("demotask", {"count": 5})
        job = Job.dequeue(queue=queue.queue)
        self.assertEqual(job.args["count"], 5)
        self.assertEqual(job.queue, NAME)
