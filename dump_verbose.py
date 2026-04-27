import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'network_management.settings')
django.setup()

from django_celery_beat.models import PeriodicTask

print("name:", PeriodicTask._meta.get_field('name').verbose_name)
print("task:", PeriodicTask._meta.get_field('task').verbose_name)
print("enabled:", PeriodicTask._meta.get_field('enabled').verbose_name)
print("last_run_at:", PeriodicTask._meta.get_field('last_run_at').verbose_name)
print("one_off:", PeriodicTask._meta.get_field('one_off').verbose_name)

