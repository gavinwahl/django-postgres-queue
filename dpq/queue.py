import time
import logging
import select
import abc

from .models import Job
from django.db import connection, transaction


class Queue(object, metaclass=abc.ABCMeta):
    job_model = Job
    logger = logging.getLogger(__name__)

    def __init__(self, tasks, notify_channel=None):
        self.tasks = tasks
        self.notify_channel = notify_channel

    @abc.abstractmethod
    def run_once(self):
        raise NotImplementedError

    def run_job(self, job):
        task = self.tasks[job.task]
        start_time = time.time()
        retval = task(self, job)
        self.logger.info(
            'Processing %r took %0.4f seconds. Task returned %r.',
            job, time.time() - start_time, retval,
            extra={
                'data': {
                    'job': job.to_json(),
                    'retval': retval,
                }
            }
        )
        return retval

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
        assert self.notify_channel, "You must set a notify channel in order to listen."
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

    def _run_once(self, exclude_ids=[]):
        job = self.job_model.dequeue(exclude_ids=exclude_ids)
        if job:
            self.logger.debug('Claimed %r.', job, extra={
                'data': {
                    'job': job.to_json(),
                }
            })
            try:
                return job, self.run_job(job)
            except Exception as e:
                # Add job info to exception to be accessible for logging.
                e.job = job
                raise
        else:
            return None


class AtMostOnceQueue(Queue):
    def run_once(self, exclude_ids=[]):
        assert not connection.in_atomic_block
        return self._run_once(exclude_ids=exclude_ids)


class AtLeastOnceQueue(Queue):
    @transaction.atomic
    def run_once(self, exclude_ids=[]):
        return self._run_once(exclude_ids=exclude_ids)
