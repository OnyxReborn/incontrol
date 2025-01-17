from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import ResourceUsage, BandwidthUsage, ErrorLog, AccessLog

class Command(BaseCommand):
    help = 'Cleans up old statistics based on retention periods'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Resource usage: keep 7 days
        resource_cutoff = now - timedelta(days=7)
        resource_deleted = ResourceUsage.objects.filter(
            timestamp__lt=resource_cutoff
        ).delete()[0]
        
        # Bandwidth usage: keep 30 days
        bandwidth_cutoff = now - timedelta(days=30)
        bandwidth_deleted = BandwidthUsage.objects.filter(
            timestamp__lt=bandwidth_cutoff
        ).delete()[0]
        
        # Access logs: keep 30 days
        access_cutoff = now - timedelta(days=30)
        access_deleted = AccessLog.objects.filter(
            timestamp__lt=access_cutoff
        ).delete()[0]
        
        # Error logs: keep 90 days
        error_cutoff = now - timedelta(days=90)
        error_deleted = ErrorLog.objects.filter(
            timestamp__lt=error_cutoff
        ).delete()[0]

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully cleaned up old statistics:\n'
                f'- Resource usage entries deleted: {resource_deleted}\n'
                f'- Bandwidth usage entries deleted: {bandwidth_deleted}\n'
                f'- Access log entries deleted: {access_deleted}\n'
                f'- Error log entries deleted: {error_deleted}'
            )
        ) 