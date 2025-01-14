import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'incontrol.settings')

app = Celery('incontrol')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()

# Configure periodic tasks
app.conf.beat_schedule = {
    'collect-metrics': {
        'task': 'monitoring.tasks.collect_metrics',
        'schedule': 60.0,  # every minute
    },
    'check-alert-rules': {
        'task': 'monitoring.tasks.check_alert_rules',
        'schedule': 60.0,  # every minute
    },
    'cleanup-old-metrics': {
        'task': 'monitoring.tasks.cleanup_old_metrics',
        'schedule': crontab(hour=0, minute=0),  # daily at midnight
    },
    'update-service-uptimes': {
        'task': 'monitoring.tasks.update_service_uptimes',
        'schedule': 60.0,  # every minute
    },
    'monitor-system-health': {
        'task': 'monitoring.tasks.monitor_system_health',
        'schedule': 300.0,  # every 5 minutes
    },
    'process-backup-schedules': {
        'task': 'backup.tasks.process_backup_schedules',
        'schedule': 300.0,  # every 5 minutes
    },
    'cleanup-old-backups': {
        'task': 'backup.tasks.cleanup_old_backups',
        'schedule': crontab(hour=1, minute=0),  # daily at 1 AM
    },
} 

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 