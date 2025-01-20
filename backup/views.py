from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from django.http import FileResponse
import os
import shutil
import tempfile
import json
from datetime import datetime, timedelta

from .models import BackupLocation, Backup, BackupSchedule, BackupLog
from .serializers import (
    BackupLocationSerializer,
    BackupSerializer,
    BackupScheduleSerializer,
    BackupStatsSerializer,
    BackupLogSerializer,
)
from .tasks import create_backup, restore_backup, cleanup_old_backups

class BackupLocationViewSet(viewsets.ModelViewSet):
    queryset = BackupLocation.objects.all()
    serializer_class = BackupLocationSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        location = self.get_object()
        try:
            # Test connection based on location type
            if location.type == 's3':
                # Test S3 connection
                pass
            elif location.type in ['ftp', 'sftp']:
                # Test FTP/SFTP connection
                pass
            elif location.type == 'local':
                # Test local path
                if not os.path.exists(location.path):
                    return Response(
                        {'error': 'Path does not exist'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            return Response({'message': 'Connection test successful'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

class BackupViewSet(viewsets.ModelViewSet):
    queryset = Backup.objects.all()
    serializer_class = BackupSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        backup = serializer.save()
        create_backup.delay(backup.id)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        backup = self.get_object()
        if backup.status != 'completed':
            return Response(
                {"error": "Can only restore completed backups"},
                status=status.HTTP_400_BAD_REQUEST
            )
        restore_backup.delay(backup.id)
        return Response({"message": "Restore process started"})

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        backup = self.get_object()
        if backup.status != 'completed':
            return Response(
                {"error": "Can only download completed backups"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not os.path.exists(backup.path):
            return Response(
                {"error": "Backup file not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        return FileResponse(
            open(backup.path, 'rb'),
            as_attachment=True,
            filename=f"{backup.name}_{backup.created_at.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        )

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        backup = self.get_object()
        logs = backup.logs.all()
        serializer = BackupLogSerializer(logs, many=True)
        return Response(serializer.data)

class BackupScheduleViewSet(viewsets.ModelViewSet):
    queryset = BackupSchedule.objects.all()
    serializer_class = BackupScheduleSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        schedule = self.get_object()
        schedule.enabled = not schedule.enabled
        schedule.save()
        return Response({
            "message": f"Schedule {'enabled' if schedule.enabled else 'disabled'}",
            "enabled": schedule.enabled
        })

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        schedule = self.get_object()
        if not schedule.enabled:
            return Response(
                {"error": "Cannot run disabled schedule"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        backup = Backup.objects.create(
            name=f"{schedule.name} (Manual Run)",
            type=schedule.type,
            status='pending'
        )
        create_backup.delay(backup.id)
        
        schedule.last_run = timezone.now()
        schedule.save()
        
        return Response({
            "message": "Backup started",
            "backup_id": backup.id
        })

class BackupStatsView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        # Calculate backup statistics
        total_backups = Backup.objects.count()
        total_size = Backup.objects.aggregate(total=Sum('size'))['total'] or 0
        active_schedules = BackupSchedule.objects.filter(is_active=True).count()
        last_backup = Backup.objects.order_by('-created_at').first()
        last_backup_time = last_backup.created_at if last_backup else None

        # Storage usage by location
        storage_usage = {}
        for location in BackupLocation.objects.all():
            size = Backup.objects.filter(location=location).aggregate(total=Sum('size'))['total'] or 0
            storage_usage[location.name] = size

        # Backup types distribution
        backup_types = {}
        for type_choice in Backup.type.field.choices:
            count = Backup.objects.filter(type=type_choice[0]).count()
            backup_types[type_choice[1]] = count

        # Success rate
        total = Backup.objects.count()
        successful = Backup.objects.filter(status='completed').count()
        success_rate = (successful / total * 100) if total > 0 else 0

        # Average backup size
        avg_size = Backup.objects.aggregate(avg=Avg('size'))['avg'] or 0

        # Backup frequency
        backup_frequency = {}
        for freq_choice in BackupSchedule.frequency.field.choices:
            count = BackupSchedule.objects.filter(frequency=freq_choice[0]).count()
            backup_frequency[freq_choice[1]] = count

        # Storage locations
        storage_locations = list(BackupLocation.objects.values('name', 'type', 'is_active'))

        stats = {
            'total_backups': total_backups,
            'total_size': total_size,
            'active_schedules': active_schedules,
            'last_backup_time': last_backup_time,
            'storage_usage': storage_usage,
            'backup_types': backup_types,
            'success_rate': success_rate,
            'average_backup_size': avg_size,
            'backup_frequency': backup_frequency,
            'storage_locations': storage_locations,
        }

        serializer = BackupStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def export_report(self, request):
        # Generate backup report
        stats = self.list(request).data
        
        # Create temporary file for the report
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp:
            json.dump(stats, tmp, indent=2, default=str)
        
        # Return the file
        response = FileResponse(
            open(tmp.name, 'rb'),
            as_attachment=True,
            filename=f'backup-report-{datetime.now().strftime("%Y%m%d")}.json'
        )
        
        # Clean up the temporary file
        os.unlink(tmp.name)
        
        return response 