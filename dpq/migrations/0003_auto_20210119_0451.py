# Generated by Django 3.1.5 on 2021-01-19 04:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dpq', '0002_auto_20190419_2057'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='args',
            field=models.JSONField(),
        ),
    ]