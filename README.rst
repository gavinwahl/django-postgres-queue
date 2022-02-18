django-pg-queue
=====================

django-pg-queue is a task queue system for Django backed by postgres.

It was forked from the wonderful and simpler django-postgres-queue (https://github.com/gavinwahl/django-postgres-queue/)
Written by Gavin Wahl.


Why postgres?
-------------

I thought you were never supposed to use an RDBMS as a queue? Well, postgres
has some features that make it not as bad as you might think, it has some
compelling advantages.

- Transactional behavior and reliability.

  Adding tasks is atomic with respect to other database work. There is no need
  to use ``transaction.on_commit`` hooks and there is no risk of a transaction
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
  available for another worker to pick up. You can even ``kill -9`` a worker
  and be sure your database and queue will be left in a consistent state.

- Priority queues

  Since ordering is specified explicitly when selecting the next task to work
  on, it's easy to ensure high-priority tasks are processed first.


- Queues

  Simply implemented by allowing filtering by a queue name in the query.



Disadvantages
-------------

- Lower throughput than a dedicated queue server.
- Harder to scale a relational database than a dedicated queue server.
- Thundering herd. Postgres will notify all workers who LISTEN for the same name.
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

django-pg-queue is able to claim, process, and remove a task in a single (simplified)
query.

.. code:: sql

    DELETE FROM pgq_job
    WHERE id = (
        SELECT id
        FROM pgq_job
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


Comparison to Celery
--------------------

django-pg-queue fills the same role as Celery. You must use postgres as the backend
and the library is small enough that you can read and understand all the code.


A note on the use of ``AtLeastOnceQueue`` and Django's ``transaction.on_commit()``
----------------------------------------------------------------------------------

A failure in an ``on_commit()`` callback will not cause that job to be retried
when using an ``AtLeastOnceQueue`` (usually a job in an ``AtLeastOnceQueue``
queue will remain in the queue if the job fails).  This is because
``on_commit()`` callbacks are executed after the transaction has been committed
and, for django-pg-queue, the job is removed from the queue when the transaction
commits.

If you require more certainty that the code in an ``on_commit()`` callback is
executed successfully, you may need to ensure it is idempotent and call it from
within the job rather than using ``on_commit()``.

Usage
=====

Requirements
------------

django-pg-queue requires Python 3, at least postgres 9.5 and at least
Django 2.1.


Installation
------------

Install with pip::

  pip install django-pg-queue

Then add ``'pgq'`` to your ``INSTALLED_APPS``. Run ``manage.py migrate`` to
create the jobs table.

Instantiate a queue object. This can go wherever you like and be named whatever
you like. For example, ``someapp/queue.py``:

.. code:: python

    from pgq.queue import AtLeastOnceQueue

    queue = AtLeastOnceQueue(
        tasks={
            # ...
        },
        queue='my-queue',
        notify_channel='my-queue',
    )


You will need to import this queue instance to queue or process tasks. Use
``AtLeastOnceQueue`` for at-least-once delivery, or ``AtMostOnceQueue`` for
at-most-once delivery.

django-pg-queue comes with a management command base class that you can
use to consume your tasks. It can be called whatever you like, for example in a
``someapp/managment/commands/worker.py``:

.. code:: python

    from pgq.commands import Worker

    from someapp.queue import queue

    class Command(Worker):
        queue = queue

Then you can run ``manage.py worker`` to start your worker.

A task function takes two arguments -- the queue instance in use, and the Job
instance for this task. The function can be defined anywhere and called
whatever you like. Here's an example:

.. code:: python

    from pgq.decorators import task

    from .queues import queue

    @task(queue)
    def debug_task(queue, job):
        print(job.args)

Instead of using the task decorator, you can manually register it as a task.
Add it to your queue instance when it is being created:

.. code:: python

    queue = AtLeastOnceQueue(tasks={
        'debug_task': debug_task,
    }, queue='my-queue')

The key is the task name, used to queue the task. It doesn't have to match the
function name.

To queue the task, if you used the task decorator you may:

.. code:: python

    debug_task.enqueue({'some_args': 0})


To manually queue the task, use the ``enqueue`` method on your queue instance:

.. code:: python

    queue.enqueue('debug_task', {'some_args': 0})

Assuming you have a worker running for this queue, the task will be run
immediately. The second argument must be a single json-serializeable value and
will be available to the task as ``job.args``.

Tasks registered using the ``@task`` decorator will only be available on the
queue if the file in which the task is defined has been imported. If your
worker doesn't import the file containing the ``@task`` decorators somewhere,
the tasks will not be available for dispatch. Importing files in the
``apps.py`` ``AppConfig.ready()`` method will ensure that the tasks are always
available on the queue without having to import them in your worker just for
the import side effects.

.. code:: python

   # Contents of someapp/apps.py
   from django.apps import AppConfig

   class SomeAppAppConfig(AppConfig):
       def ready(self):
           # Tasks registered with @task are defined in this import
           import someapp.tasks

Multiple Queues
---------------

You may run multiple queues and workers may each listen to a queue. You can have multiple workers
listening to the same queue too. A queue is implemented as a CharField in the database.
The queue would simply filter for jobs matching its queue name.

Bulk Enqueue
------------

Many jobs can be efficiently created using ``bulk_enqueue()`` which accepts one
task name for all the jobs being created and a list of dictionaries containing
``args`` for the task to execute with and, optionally, ``priority`` and
``execute_at`` for that particular job.

.. code:: python

    queue.bulk_enqueue(
        'debug_task',
        [
            {'args': {'some_args': 0}},
            {
                'args': {'some_args': 10}
                'priority': 10,
                'execute_at': timezone.now() + timedelta(days=1),
            },
        ]
    )


Monitoring
----------

Tasks are just database rows stored in the ``pgq_job`` table, so you can
monitor the system with SQL.

To get a count of current tasks:

.. code:: sql

    SELECT queue, count(*) FROM pgq_job WHERE execute_at <= now() GROUP BY queue


This will include both tasks ready to process and tasks currently being
processed. To see tasks currently being processed, we need visibility into
postgres row locks. This can be provided by the `pgrowlocks extension
<https://www.postgresql.org/docs/9.6/static/pgrowlocks.html>`_.  Once
installed, this query will count currently-running tasks:

.. code:: sql

    SELECT queue, count(*)
    FROM pgrowlocks('pgq_job')
    WHERE 'For Update' = ANY(modes)
    GROUP BY queue;

You could join the results of ``pgrowlocks`` with ``pgq_job`` to get the full
list of tasks in progress if you want.

Logging
-------

django-pg-queue logs through Python's logging framework, so can be
configured with the ``LOGGING`` dict in your Django settings. It will not log
anything under the default config, so be sure to configure some form of
logging. Everything is logged under the ``pgq`` namespace. Here is an example
configuration that will log INFO level messages to stdout:

.. code:: python

    LOGGING = {
        'version': 1,
        'root': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s',
            },
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'pgq': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
        }
    }

It would also be sensible to log WARNING and higher messages to something like
Sentry:

.. code:: python

    LOGGING = {
        'version': 1,
        'root': {
            'level': 'INFO',
            'handlers': ['sentry', 'console'],
        },
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s',
            },
        },
        'handlers': {
            'console': {
                'level': 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'sentry': {
                'level': 'WARNING',
                'class': 'raven.contrib.django.handlers.SentryHandler',
            },
        },
        'loggers': {
            'pgq': {
                'level': 'INFO',
                'handlers': ['console', 'sentry'],
                'propagate': False,
            },
        },
    }

You could also log to a file by using the built-in ``logging.FileHandler``.

Useful Recipes
==============
These recipes aren't officially supported features of `django-pg-queue`. We provide them so that you can mimick some of the common features in other task queues.

`CELERY_ALWAYS_EAGER`
---------------------
Celery uses the `CELERY_ALWAYS_EAGER` setting to run a task immediately, without queueing it for a worker. It could be used during tests, and while debugging in a development environment with any workers turned off.

.. code:: python

    class EagerAtLeastOnceQueue(AtLeastOnceQueue):
        def enqueue(self, *args, **kwargs):
            job = super().enqueue(*args, **kwargs)
            if settings.QUEUE_ALWAYS_EAGER:
                self.run_job(job)
            return job
