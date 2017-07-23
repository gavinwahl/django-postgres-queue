def repeat(delay):
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
