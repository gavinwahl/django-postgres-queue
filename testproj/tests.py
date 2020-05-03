import datetime
from typing import Any, Iterable, Optional, Tuple

from django.contrib.auth.models import Group
from django.db.transaction import atomic
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from pgq.decorators import task, JobMeta
from pgq.models import Job, DEFAULT_QUEUE_NAME
from pgq.queue import AtLeastOnceQueue, AtMostOnceQueue, BaseQueue, Queue

from .models import AltJob


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

    def test_bulk_enqueue_tasks(self) -> None:
        NAME = "machine_a"
        queue = AtLeastOnceQueue(tasks={"demotask": demotask}, queue=NAME)

        self.assertEqual(Job.objects.count(), 0)

        day_from_now = timezone.now() + datetime.timedelta(days=1)
        task_name = "demotask"
        ret_jobs = queue.bulk_enqueue(
            task_name,
            [
                {"args": {"count": 5}},
                {"args": {"count": 7}, "priority": 10, "execute_at": day_from_now,},
            ],
        )
        jobs = Job.objects.all()
        self.assertEqual(len(ret_jobs), 2)
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            self.assertEqual(job.queue, NAME)
            self.assertEqual(job.task, task_name)

        self.assertEqual(jobs[0].args["count"], 5)
        self.assertEqual(jobs[0].priority, 0)

        self.assertEqual(jobs[1].args["count"], 7)
        self.assertEqual(jobs[1].priority, 10)
        self.assertEqual(jobs[1].execute_at, day_from_now)

    def test_queue_subclass_enqueue(self):
        """
        BaseQueue subclassed enqueue with different job_model uses its own table.
        """
        NAME = "machine_a"

        class AltQueue(BaseQueue[AltJob]):
            job_model = AltJob

            def run_once(
                self, exclude_ids: Optional[Iterable[int]] = None
            ) -> Optional[Tuple[AltJob, Any]]:
                return self._run_once(exclude_ids=exclude_ids)

        queue = AltQueue(tasks={"demotask": demotask}, queue=NAME)

        self.assertEqual(queue.job_model, AltJob)
        self.assertEqual(AltJob.objects.count(), 0)

        job = queue.enqueue("demotask", args={"count": 1})

        self.assertIsInstance(job, AltJob)
        self.assertEqual(AltJob.objects.count(), 1)

    def test_queue_subclass_bulk_enqueue(self):
        """
        BaseQueue subclassed bulk_enqueue with different job_model uses its own table.
        """
        NAME = "machine_a"

        class AltQueue(BaseQueue[AltJob]):
            job_model = AltJob

            def run_once(
                self, exclude_ids: Optional[Iterable[int]] = None
            ) -> Optional[Tuple[AltJob, Any]]:
                return self._run_once(exclude_ids=exclude_ids)

        queue = AltQueue(tasks={"demotask": demotask}, queue=NAME)

        self.assertEqual(queue.job_model, AltJob)
        self.assertEqual(AltJob.objects.count(), 0)

        jobs = queue.bulk_enqueue(
            "demotask", [{"args": {"count": 5}}, {"args": {"count": 7}},],
        )

        self.assertEqual(AltJob.objects.count(), 2)
        self.assertIsInstance(jobs[0], AltJob)

    def test_basejob_subclass_dequeue(self):
        NAME = "machine_a"

        class AltQueue(BaseQueue[AltJob]):
            job_model = AltJob

            def run_once(
                self, exclude_ids: Optional[Iterable[int]] = None
            ) -> Optional[Tuple[AltJob, Any]]:
                return self._run_once(exclude_ids=exclude_ids)

        queue = AltQueue(tasks={"demotask": demotask}, queue=NAME)

        self.assertEqual(queue.job_model, AltJob)
        self.assertEqual(AltJob.objects.count(), 0)

        job = queue.enqueue("demotask", args={"count": 1})

        self.assertEqual(AltJob.objects.count(), 1)

        db_job = AltJob.dequeue(queue=queue.queue)

        self.assertEqual(job, db_job)
        self.assertEqual(AltJob.objects.count(), 0)


class PgqNotifyTests(TransactionTestCase):
    def test_notify_and_listen(self) -> None:
        """
        After `listen()`, `enqueue()` makes a notification
        appear via `filter_notifies()`.
        """
        NAME = "machine_a"
        queue = AtLeastOnceQueue(
            tasks={"demotask": demotask}, notify_channel="queue_a", queue=NAME
        )

        queue.listen()
        queue.enqueue("demotask", {"count": 5})
        self.assertEqual(len(queue.filter_notifies()), 1)

        queue.enqueue("demotask", {"count": 5})
        queue.enqueue("demotask", {"count": 5})
        self.assertEqual(len(queue.filter_notifies()), 2)

    def test_notify_only_returns_one_notify_per_channel_per_txn(self) -> None:
        """
        Only one notification returned per channel per txn regardless of number
        enqueued tasks.

        By default, postgres will 'fold' notifications within a transaction
        that have the same channel and payload.
        """
        NAME = "machine_a"
        queue = AtLeastOnceQueue(
            tasks={"demotask": demotask}, notify_channel="queue_a", queue=NAME
        )
        queue.listen()

        NAME2 = "machine_b"
        queue2 = AtLeastOnceQueue(
            tasks={"demotask": demotask}, notify_channel="queue_b", queue=NAME2
        )
        queue2.listen()

        with atomic():
            queue.enqueue("demotask", {"count": 5})
            queue.enqueue("demotask", {"count": 5})

            queue2.enqueue("demotask", {"count": 5})
            queue2.enqueue("demotask", {"count": 5})

        self.assertEqual(len(queue.wait()), 1)
        self.assertEqual(len(queue2.wait()), 1)

    def test_bulk_create_notifies(self) -> None:
        NAME = "machine_a"
        queue = AtLeastOnceQueue(
            tasks={"demotask": demotask}, notify_channel="queue_a", queue=NAME
        )
        queue.listen()

        now = timezone.now()
        queue.bulk_enqueue(
            "demotask",
            [
                {"args": {"count": 5}},
                {"args": {"count": 7}, "priority": 10, "execute_at": now,},
            ],
        )

        self.assertEqual(len(queue.wait()), 1)

    def test_atmostonce_retry_during_database_failure(self) -> None:
        """
        As above. but for atmost once queue
        """

        queue = AtMostOnceQueue(tasks={})

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
