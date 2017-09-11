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
