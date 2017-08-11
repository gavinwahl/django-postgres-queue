import logging
import time

from django.core.management.base import BaseCommand


class Worker(BaseCommand):
    # The queue to process. Subclass and set this.
    queue = None
    logger = logging.getLogger(__name__)

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

        # Prevents tasks that failed from blocking others.
        failed_tasks = set()
        while True:
            while True:
                try:
                    job = self.queue.run_once(exclude_ids=failed_tasks)
                    if not job:
                        break
                except Exception as e:
                    self.logger.exception('Error in %r: %r.', e.job, e, extra={
                        'data': {
                            'job': e.job.to_json(),
                        },
                    })
                    failed_tasks.add(e.job.id)
            self.wait()
            # We've run out of tasks, it's safe to put the failed ones back
            # into consideration.
            failed_tasks = set()

    def wait(self):
        if self.listen:
            count = len(self.queue.wait(self.delay))
            self.logger.debug('Woke up with %s NOTIFYs.', count)
            return count
        else:
            time.sleep(self.delay)
            return 1
