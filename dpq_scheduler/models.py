from django.db import models


class LastScheduledFor(models.Model):
    task = models.CharField(max_length=255, primary_key=True)
    execute_at = models.DateTimeField()

    def __str__(self):
        return '{}: {}'.format(self.task, self.execute_at)
