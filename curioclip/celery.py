import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'curioclip.settings')

app = Celery('curioclip')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()