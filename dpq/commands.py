import logging
import signal
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

    def handle_shutdown(self, sig, frame):
        if self._in_task:
            self.logger.info('Waiting for active tasks to finish...')
            self._shutdown = True
        else:
            raise InterruptedError

    def run_available_tasks(self):
        """
        Runs tasks continuously until there are no more available.
        """
        # Prevents tasks that failed from blocking others.
        failed_tasks = set()
        while True:
            job = None
            self._in_task = True
            try:
                job = self.queue.run_once(exclude_ids=failed_tasks)
            except Exception as e:
                if hasattr(e, 'job'):
                    self.logger.exception('Error in %r: %r.', e.job, e, extra={
                        'data': {
                            'job': e.job.to_json(),
                        },
                    })
                    failed_tasks.add(e.job.id)
                else:
                    raise
            self._in_task = False
            if self._shutdown:
                raise InterruptedError
            if not job:
                break

    def handle(self, **options):
        self._shutdown = False
        self._in_task = False

        self.delay = options['delay']
        self.listen = options['listen']
        if self.listen:
            self.queue.listen()
        try:
            # Handle the signals for warm shutdown.
            signal.signal(signal.SIGINT, self.handle_shutdown)
            signal.signal(signal.SIGTERM, self.handle_shutdown)

            while True:
                self.run_available_tasks()
                self.wait()
        except InterruptedError:
            # got shutdown signal
            pass

    def wait(self):
        if self.listen:
            count = len(self.queue.wait(self.delay))
            self.logger.debug('Woke up with %s NOTIFYs.', count)
            return count
        else:
            time.sleep(self.delay)
            return 1
