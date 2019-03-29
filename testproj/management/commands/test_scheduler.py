import datetime

from dpq_scheduler.commands import Scheduler
from dpq_scheduler.schedules import repeater

from testproj.queue import queue


class Command(Scheduler):
    queue = queue
    tasks = {
        'foo': repeater(datetime.timedelta(seconds=5)),
        'long_task': repeater(datetime.timedelta(seconds=7)),
    }
