import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'network_management.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.contrib import admin
from django_celery_beat.models import PeriodicTask

# Create superuser if needed
user, _ = User.objects.get_or_create(username='admin', is_superuser=True, is_staff=True)

# Get the admin instance
model_admin = admin.site._registry[PeriodicTask]
factory = RequestFactory()
request = factory.get('/')
request.user = user

# Get changelist
cl = model_admin.get_changelist_instance(request)

# Get first row HTML
for res in cl.result_list[:1]:
    row = []
    from django.contrib.admin.utils import display_for_value, lookup_field
    for field in model_admin.get_list_display(request):
        f, attr, value = lookup_field(field, res, model_admin)
        boolean = getattr(attr, 'boolean', False)
        # or getattr(f, 'flatchoices') depending on django version
        if getattr(f, 'choices', False) or isinstance(value, bool):
            html = display_for_value(value, '', True)
            print(f"BOOL FIELD {field} -> {html}")

