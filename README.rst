django-postgres-queue
=====================

django-postgres-queue is a task queue system for Django backed by postgres.


Why postgres?
-------------

I thought you were never supposed to use an RDBMS as a queue? Well, postgres
has some features that make it not as bad as you might think, it has some
compelling advantages.

- Transactional behavior and reliability.

  Adding tasks is atomic with respect to other database work. There is no need
  to use `transaction.on_commit` hooks and there is no risk of a transaction
  being committed but the tasks it queued being lost.

  Processing tasks is atomic with respect to other database work. Database work
  done by a task will either be committed, or the task will not be marked as
  processed, no exceptions. If the task only does database work, you achieve
  true exactly-once message processing.

- Operational simplicity

  By reusing the durable, transactional storage that we're already using
  anyway, there's no need to configure, monitor, and backup another stateful
  service. For small teams and light workloads, this is the right trade-off.

- Easy introspection

  Since tasks are stored in a database table, it's easy to query and monitor
  the state of the queue.

- Safety

  By using postgres transactions, there is no possibility of jobs being left in
  a locked or ambiguous state if a worker dies. Tasks immediately become
  available for another worker to pick up.

- Priority queues

  Since ordering is specified explicitly when selecting the next task to work
  on, it's easy to ensure high-priority tasks are processed first.


Disadvantages
-------------

- Lower throughput than a dedicated queue server.
- Harder to scale a relational database than a dedicated queue server.
- Thundering herd. Postgres has no way to notify a single worker to wake up, so
  we can either wake every single worker up when a task is queued with
  LISTEN/NOTIFY, or workers have to short-poll.
- With at-least-once delivery, a postgres transaction has to be held open for
  the duration of the task. For long running tasks, this can cause table bloat
  and performance problems.
- When a task crashes or raises an exception under at-least-once delivery, it
  immediately becomes eligible to be retried. If you want to implement a retry
  delay, you must catch exceptions and requeue the task with a delay. If your
  task crashes without throwing an exception (eg SIGKILL), you could end up in
  an endless retry loop that prevents other tasks from being processed.


How it works
------------

django-postgres-queue is able to claim, process, and remove a task in a single
query.

.. code:: sql

    DELETE FROM dpq_job
    WHERE id = (
        SELECT id
        FROM dpq_job
        WHERE execute_at <= now()
        ORDER BY priority DESC, created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;

As soon as this query runs, the task is unable to be claimed by other workers.
When the transaction commits, the task will be deleted. If the transaction
rolls back or the worker crashes, the task will immediately become available
for another worker.

To achieve at-least-once delivery, we begin a transaction, process the task,
then commit the transaction. For at-most-once, we claim the task and
immediately commit the transaction, then process the task. For tasks that don't
have any external effects and only do database work, the at-least-once behavior
is actually exactly-once (because both the claiming of the job and the database
work will commit or rollback together).


Usage
=====

Requirements
------------

django-postgres-queue requires python 3, at least postgres 9.6 and at least
Django 1.11.


Installation
------------

Install with pip::

  pip install django-postgres-queue

Then add `'dpq'` to your `INSTALLED_APPS`. Run `manage.py migrate` to create
the jobs table.

Define a Queue subclass. This can go wherever you like and be named whatever
you like. For example, `someapp/queue.py`:

.. code:: python

    from dpq.queue import AtLeastOnceQueue

    class MyQueue(AtLeastOnceQueue):
        notify_channel = 'my-queue'
        tasks = {
            # ...
        }

    queue = MyQueue()

You will need to import this queue instance to queue or process tasks.

django-postgres-queue comes with a management command base class that you can
use to consume your tasks. It can be called whatever you like, for example in a
`someapp/managment/commands/worker.py`:

.. code:: python

    from dpq.management import Worker

    from someapp.queue import queue

    class Command(Worker):
        queue = queue

Then you can run `manage.py worker` to start your worker.

A task function takes two arguments -- the queue instance in use, and the Job
instance for this task. The function can be defined anywhere and called
whatever you like. Here's an example:

.. code:: python

    def debug_task(queue, job):
        print(job.args)

To register it as a task, add it to your `Queue` subclass:

.. code:: python

    tasks = {
      'debug_task': debug_task
    }

The key is the task name, used to queue the task. It doesn't have to match the
function name.

To queue the task, use `enqueue` method on your queue instance:

.. code:: python

    queue.enqueue('debug_task', {'some_args': 0})

Assuming you have a worker running for this queue, the task will be run
immediately.
