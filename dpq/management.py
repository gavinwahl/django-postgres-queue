import time

from django.core.management.base import BaseCommand


class Worker(BaseCommand):
    # The queue to process. Subclass and set this.
    queue = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--delay',
            type=float,
            default=1,
            help="The number of seconds to wait to check for new tasks.",
        )
        parser.add_argument(
            '--listen',
            action='store_true',
            help="Use LISTEN/NOTIFY to wait for events."
        )

    def handle(self, **options):
        self.delay = options['delay']
        self.listen = options['listen']
        if self.listen:
            self.queue.listen()

        count = 1
        while True:
            for i in range(count):
                job = self.queue.run_once()
                if not job:
                    break
            if not job or self.listen:
                count = self.wait()
                if not count:
                    # timeout, try for a task anway
                    count = 1

    def wait(self):
        if self.listen:
            return len(self.queue.wait(self.delay))
        else:
            time.sleep(self.delay)
            return 1
