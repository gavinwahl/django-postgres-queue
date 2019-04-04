import datetime
import logging
import random


def repeat(delay):
    """
    Endlessly repeats a task, every `delay` (a timedelta).

    Under at-least-once delivery, the tasks can not overlap. The next scheduled
    task only becomes visible once the previous one commits.

        @repeat(datetime.timedelta(minutes=5)
        def task(queue, job):
            pass

    This will run `task` every 5 minutes. It's up to you to kick off the first
    task, though.
    """
    def decorator(fn):
        def inner(queue, job):
            queue.enqueue(
                job.task,
                job.args,
                execute_at=job.execute_at + delay,
                priority=job.priority,
            )
            return fn(queue, job)

        return inner
    return decorator


def exponential_with_jitter(offset=6):
    def delayfn(retries):
        jitter = random.randrange(-15, 15)
        return datetime.timedelta(seconds=2 ** (retries + offset) + jitter)
    return delayfn


def retry(max_retries, delayfn=exponential_with_jitter(), Exc=Exception):
    def decorator(fn):
        logger = logging.getLogger(__name__)

        def inner(queue, job):
            try:
                return fn(queue, job)
            except Exc as e:
                retries = job.args.get('retries', 0)
                if retries < max_retries:
                    job.args['retries'] = retries + 1
                    delay = delayfn(retries)
                    job.execute_at += delay
                    job.save(force_insert=True)
                    logger.warning(
                        'Task %r failed: %s. Retrying in %s.', job, e, delay, exc_info=True,
                    )
                else:
                    logger.exception(
                        'Task %r exceeded its retry limit: %s.', job, e, exc_info=True,
                    )
        return inner
    return decorator
