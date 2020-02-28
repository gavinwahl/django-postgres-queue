import logging
import signal
import time
from typing import Any, Optional, Set
import os

from django.core.management.base import BaseCommand
from django.db import connection

from .exceptions import PgqException, PgqNoDefinedQueue
from .queue import Queue


class Worker(BaseCommand):
    # The queue to process. Subclass and set this.
    queue: Optional[Queue] = None
    logger = logging.getLogger(__name__)

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--delay",
            type=float,
            default=1,
            help="The number of seconds to wait to check for new tasks.",
        )
        parser.add_argument(
            "--listen",
            action="store_true",
            help="Use LISTEN/NOTIFY to wait for events.",
        )

    def handle_shutdown(self, sig: Any, frame: Any) -> None:
        if self._in_task:
            self.logger.info("Waiting for active tasks to finish...")
            self._shutdown = True
        else:
            raise InterruptedError

    def run_available_tasks(self) -> None:
        """
        Runs tasks continuously until there are no more available.
        """
        # Prevents tasks that failed from blocking others.
        failed_tasks: Set[int] = set()

        if self.queue is None:
            raise PgqNoDefinedQueue

        while True:
            job = None
            self._in_task = True
            try:
                job = self.queue.run_once(exclude_ids=failed_tasks)
            except PgqException as e:
                if e.job is not None:
                    # Make sure we do at least one more iteration of the loop
                    # with the failed task excluded.
                    job = e.job
                    self.logger.exception(
                        "Error in %r: %r.",
                        job,
                        e,
                        extra={"data": {"job": job.to_json()}},
                    )
                    failed_tasks.add(job.id)
                else:
                    raise
            self._in_task = False
            if self._shutdown:
                raise InterruptedError
            if not job:
                break

    def handle(self, **options: Any) -> None:  # type: ignore
        self._shutdown = False
        self._in_task = False

        self.delay: int = options["delay"]
        self.listen: bool = options["listen"]

        if self.queue is None:
            raise PgqNoDefinedQueue

        with connection.cursor() as cursor:
            cursor.execute("SET application_name TO %s", ["pgq#{}".format(os.getpid())])

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

    def wait(self) -> int:
        if self.listen and self.queue is not None:
            count = len(self.queue.wait(self.delay))
            self.logger.debug("Woke up with %s NOTIFYs.", count)
            return count
        else:
            time.sleep(self.delay)
            return 1
