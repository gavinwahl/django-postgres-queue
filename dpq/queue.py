import select
import abc

from .models import Job
from django.db import connection, transaction


class Queue(object, metaclass=abc.ABCMeta):
    at_most_once = False
    tasks = None
    job_model = Job
    notify_channel = None

    @abc.abstractmethod
    def run_once(self):
        raise NotImplementedError

    def run_job(self, job):
        task = self.tasks[job.task]
        return task(self, job)

    def enqueue(self, task, args={}, execute_at=None, priority=None):
        assert task in self.tasks
        kwargs = {
            'task': task,
            'args': args,
        }
        if execute_at is not None:
            kwargs['execute_at'] = execute_at
        if priority is not None:
            kwargs['priority'] = priority

        job = self.job_model.objects.create(**kwargs)
        if self.notify_channel:
            self.notify(job)
        return job

    def listen(self):
        with connection.cursor() as cur:
            cur.execute('LISTEN "{}";'.format(self.notify_channel))

    def wait(self, timeout=30):
        connection.connection.poll()
        notifies = self.filter_notifies()
        if notifies:
            return notifies

        select.select([connection.connection], [], [], timeout)
        connection.connection.poll()
        return self.filter_notifies()

    def filter_notifies(self):
        notifies = [
            i for i in connection.connection.notifies
            if i.channel == self.notify_channel
        ]
        connection.connection.notifies = [
            i for i in connection.connection.notifies
            if i.channel != self.notify_channel
        ]
        return notifies

    def notify(self, job):
        with connection.cursor() as cur:
            cur.execute('NOTIFY "{}", %s;'.format(self.notify_channel), [str(job.pk)])


class AtMostOnceQueue(Queue):
    def run_once(self):
        assert not connection.in_atomic_block
        job = self.job_model.dequeue()
        if job:
            return job, self.run_job(job)
        else:
            return None


class AtLeastOnceQueue(Queue):
    @transaction.atomic
    def run_once(self):
        job = self.job_model.dequeue()
        if job:
            return job, self.run_job(job)
        else:
            return None
