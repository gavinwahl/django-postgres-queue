from dpq.commands import Worker

from testproj.queue import queue


class Command(Worker):
    queue = queue
