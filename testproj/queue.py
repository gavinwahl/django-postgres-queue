import time
from datetime import timedelta

from pgq.queue import AtLeastOnceQueue, Queue
from pgq.decorators import repeat
from pgq.models import Job


def foo(queue: Queue, job: Job):
    print("foo {}".format(job.args))


def timer(queue: Queue, job: Job):
    print(time.time() - job.args["time"])


def n_times(queue: Queue, job: Job):
    print("n_times", job.args["count"])
    if job.args["count"] > 1:
        queue.enqueue(job.task, {"count": job.args["count"] - 1})


@repeat(timedelta(seconds=1))
def repeater(queue, job):
    print("repeat {}; eta {}".format(job, job.execute_at))


def long_task(queue, job):
    print("job started: {}".format(job.id))
    time.sleep(10)
    print("job finished: {}".format(job.id))


queue = AtLeastOnceQueue(
    notify_channel="channel",
    tasks={
        "foo": foo,
        "timer": timer,
        "repeater": repeater,
        "n_times": n_times,
        "long_task": long_task,
    },
)
