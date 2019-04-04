import time
import pytz
import logging
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection

from dpq_scheduler.models import LastScheduledFor


class Scheduler(BaseCommand):
    # The set of tasks to schedule. dict of task name -> schedule func. A
    # schedule func takes a datetime and returns the soonest datetime in the
    # schedule that is strictly after the argument.
    tasks = None
    # The queue to schedule in.
    queue = None

    logger = logging.getLogger(__name__)

    def handle(self, **options):
        self.validate_tasks()

        while True:
            delay = self.one_round()
            self.logger.debug('Sleeping %s.', delay)
            time.sleep(min(delay.total_seconds(), 2 ** 30))

    @transaction.atomic
    def one_round(self):
        self.logger.debug('Beginning a scheduling round.')
        with connection.cursor() as cursor:
            cursor.execute("LOCK TABLE %s IN EXCLUSIVE MODE" % LastScheduledFor._meta.db_table)
            cursor.execute("SELECT now()")
            now, = cursor.fetchone()

        last_scheduleds = LastScheduledFor.objects.in_bulk()

        next_wakeup = datetime.datetime.max.replace(tzinfo=pytz.UTC)

        for task_name, schedule in self.tasks.items():
            try:
                last_scheduled = last_scheduleds[task_name]
            except KeyError:
                # This isn't actually marking that the task has been scheduled,
                # we just need to create the row for the first time somehow,
                # and this will let the next iteration actually schedule the
                # task.
                LastScheduledFor.objects.create(task=task_name, execute_at=now)
                next_time = schedule(now)
            else:
                next_time = schedule(last_scheduled.execute_at)
                if next_time <= now:
                    task = self.queue.enqueue(task_name, execute_at=next_time)
                    self.logger.info('Scheduled %r for %s.', task, next_time)
                    last_scheduled.execute_at = next_time
                    last_scheduled.save()
                    next_time = schedule(next_time)
            next_wakeup = min(next_wakeup, next_time)

        # these tasks have been removed from the config
        LastScheduledFor.objects.filter(
            task__in=set(last_scheduleds) - set(self.tasks)
        ).delete()

        return max(next_wakeup - now, datetime.timedelta(seconds=0))

    def validate_tasks(self):
        missing_tasks = set(self.tasks.keys()) - set(self.queue.tasks.keys())
        if missing_tasks:
            raise CommandError("Tasks in schedule but missing from queue: %r" % missing_tasks)
