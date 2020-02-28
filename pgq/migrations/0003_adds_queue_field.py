from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dpq", "0002_auto_20190419_2057"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="queue",
            field=models.CharField(
                max_length=32,
                default="default",
                help_text="Use a unique name to represent each queue.",
            ),
        ),
        migrations.AddIndex(
            model_name="job",
            index=models.Index(fields=["queue"], name="dpq_job_queue_aa4927_idx"),
        ),
    ]
