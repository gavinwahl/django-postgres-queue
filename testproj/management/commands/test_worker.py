import time
from datetime import timedelta

from dpq.queue import AtLeastOnceQueue
from dpq.decorators import repeat
from dpq.management import Worker


def foo(queue, job):
    print('foo {}'.format(job.args))


def timer(queue, job):
    print(time.time() - job.args['time'])


def n_times(queue, job):
    print('n_times', job.args['count'])
    if job.args['count'] > 1:
        queue.enqueue(job.task, {'count': job.args['count'] - 1})


@repeat(timedelta(seconds=1))
def repeater(queue, job):
    print('repeat {}; eta {}'.format(job, job.execute_at))


queue = AtLeastOnceQueue(
    notify_channel='channel',
    tasks={
        'foo': foo,
        'timer': timer,
        'repeater': repeater,
        'n_times': n_times,
    },
)


class Command(Worker):
    queue = queue
