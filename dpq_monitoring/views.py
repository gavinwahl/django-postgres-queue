from django.http import JsonResponse
from django.db import connection
from django.shortcuts import render

from dpq.models import Job


def index(request):
    return render(
        request,
        template_name='dpq_monitoring/index.html',
    )


def stats(request):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              now() AS timestamp,
              n_tup_ins AS queued,
              n_tup_del AS processed,
              COUNT(pg_extension.*) = 1 AS pgrowlocks_enabled
            FROM pg_stat_all_tables
            LEFT JOIN pg_extension ON extname = 'pgrowlocks'
            WHERE relname = 'dpq_job'
            GROUP BY 2, 3
            """,
            [Job._meta.db_table],
        )
        timestamp, queued, processed, pgrowlocks_enabled = cursor.fetchone()

    info = {
        'timestamp': timestamp,
        'pgrowlocks_enabled': pgrowlocks_enabled,
        'total_queued': queued,
        'total_processed': processed,
        'enqueued': Job.objects.enqueued().count(),
        'scheduled': Job.objects.scheduled().count(),
    }
    return JsonResponse(info)


def jobs(request):
    query = Job.objects.all()

    if 'scheduled' in request.GET:
        query = query.scheduled()
    elif 'enqueued' in request.GET:
        query = query.enqueued()

    return JsonResponse([job.to_json() for job in query], safe=False)


def workers(request):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              pg_stat_activity.application_name,
              pg_stat_activity.pid AS pg_pid,
              pg_stat_activity.backend_start AS started_at,
              row_to_json(dpq_job.*) AS job_details
            FROM pg_stat_activity
            LEFT JOIN pgrowlocks('dpq_job') AS locks
                   ON pg_stat_activity.pid = ANY(locks.pids)
            LEFT JOIN dpq_job ON dpq_job.ctid = locks.locked_row
            WHERE application_name LIKE 'dpq#%'
            """
        )
        workers = [
            {
                'ospid': int(row[0].partition('#')[2]),
                'pgpid': row[1],
                'started_at': row[2],
                'current_job': row[3] and Job(**row[3])
            }
            for row in cursor.fetchall()
        ]
    return JsonResponse(workers, safe=False)
