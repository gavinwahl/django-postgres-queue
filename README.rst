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
