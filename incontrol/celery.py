import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'incontrol.settings')

app = Celery('incontrol')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Configure periodic tasks
app.conf.beat_schedule = {
    'collect-metrics': {
        'task': 'monitoring.tasks.collect_metrics',
        'schedule': 30.0,  # Every 30 seconds
    },
    'update-service-uptimes': {
        'task': 'monitoring.tasks.update_service_uptimes',
        'schedule': 60.0,  # Every minute
    },
    'monitor-system-health': {
        'task': 'monitoring.tasks.monitor_system_health',
        'schedule': 10.0,  # Every 10 seconds
    },
}

app.conf.timezone = 'UTC'

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 