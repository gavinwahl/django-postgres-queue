import logging
import signal
import time
import os

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import autoreload
from django.utils.autoreload import raise_last_exception


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
        parser.add_argument(
            '--reload',
            action='store_true',
            dest='use_reloader',
            help="Use the auto-reloader.",
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
            self._in_task = True
            result = self.queue.run_once(exclude_ids=failed_tasks)
            job, retval, exc = result or (None, None, None)
            if exc:
                if job:
                    self.logger.exception('Error in %r: %r.', job, exc, extra={
                        'data': {
                            'job': job.to_json(),
                        },
                    })
                    failed_tasks.add(job.id)
                else:
                    # This is an exception before a task could even be
                    # retrieved, so it's probably fatal
                    raise exc
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

        # Handle the signals for warm shutdown.
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        self.run(**options)

    def inner_run(self, **options):
        # If an exception was silenced in ManagementUtility.execute in order
        # to be raised in the child process, raise it now.
        raise_last_exception()

        with connection.cursor() as cursor:
            cursor.execute("SET application_name TO %s", ['dpq#{}'.format(os.getpid())])

        if self.listen:
            self.logger.info('Listening for queued tasks', extra={
                'channel': self.queue.notify_channel,
            })
            self.queue.listen()
        try:

            while True:
                self.run_available_tasks()
                self.wait()
        except InterruptedError:
            # got shutdown signal
            pass

    def run(self, **options):
        """Run the worker, using the autoreloader if needed."""
        if options['use_reloader']:
            autoreload.run_with_reloader(self.inner_run, **options)
        else:
            self.inner_run(**options)

    def wait(self):
        if self.listen:
            count = len(self.queue.wait(self.delay))
            self.logger.debug('Woke up with %s NOTIFYs.', count)
            return count
        else:
            time.sleep(self.delay)
            return 1
