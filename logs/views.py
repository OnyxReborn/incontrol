import os
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Sum
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import LogFile, LogEntry, LogAlert, LogRotationPolicy
from .serializers import (
    LogFileSerializer, LogEntrySerializer, LogAlertSerializer,
    LogRotationPolicySerializer, LogStatisticsSerializer
)

class LogFileViewSet(viewsets.ModelViewSet):
    queryset = LogFile.objects.all()
    serializer_class = LogFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LogFile.objects.all()
        log_type = self.request.query_params.get('type', None)
        if log_type:
            queryset = queryset.filter(log_type=log_type)
        return queryset

    @action(detail=True, methods=['get'])
    def tail(self, request, pk=None):
        """Get the last N lines of the log file"""
        log_file = self.get_object()
        lines = int(request.query_params.get('lines', 100))
        
        try:
            with open(log_file.path, 'r') as f:
                content = f.readlines()
                return Response(content[-lines:])
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def clear(self, request, pk=None):
        """Clear the log file contents"""
        log_file = self.get_object()
        try:
            open(log_file.path, 'w').close()
            return Response({'status': 'log file cleared'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class LogEntryViewSet(viewsets.ModelViewSet):
    queryset = LogEntry.objects.all()
    serializer_class = LogEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LogEntry.objects.all()
        
        # Filter by log file
        log_file = self.request.query_params.get('log_file', None)
        if log_file:
            queryset = queryset.filter(log_file_id=log_file)
        
        # Filter by severity
        severity = self.request.query_params.get('severity', None)
        if severity:
            queryset = queryset.filter(severity=severity)
        
        # Filter by source
        source = self.request.query_params.get('source', None)
        if source:
            queryset = queryset.filter(source=source)
        
        # Filter by time range
        hours = self.request.query_params.get('hours', None)
        if hours:
            since = timezone.now() - timedelta(hours=int(hours))
            queryset = queryset.filter(timestamp__gte=since)
        
        return queryset

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search log entries by keyword"""
        keyword = request.query_params.get('keyword', '')
        queryset = self.get_queryset().filter(message__icontains=keyword)
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class LogAlertViewSet(viewsets.ModelViewSet):
    queryset = LogAlert.objects.all()
    serializer_class = LogAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LogAlert.objects.all()
        is_active = self.request.query_params.get('active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle alert active status"""
        alert = self.get_object()
        alert.is_active = not alert.is_active
        alert.save()
        return Response({'status': 'alert status updated'})

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """Test alert configuration"""
        alert = self.get_object()
        from .tasks import process_log_alert
        process_log_alert.delay(alert.id, test_mode=True)
        return Response({'status': 'alert test initiated'})

class LogRotationPolicyViewSet(viewsets.ModelViewSet):
    queryset = LogRotationPolicy.objects.all()
    serializer_class = LogRotationPolicySerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def rotate_now(self, request, pk=None):
        """Force log rotation"""
        policy = self.get_object()
        from .tasks import rotate_log_file
        rotate_log_file.delay(policy.id, force=True)
        return Response({'status': 'log rotation initiated'})

    @action(detail=False, methods=['get'])
    def pending_rotations(self, request):
        """Get list of logs pending rotation"""
        policies = self.get_queryset()
        pending = []
        
        for policy in policies:
            if policy.is_active:
                if policy.rotation_unit == 'size':
                    try:
                        current_size = os.path.getsize(policy.log_file.path)
                        if current_size > policy.max_size:
                            pending.append(policy)
                    except:
                        continue
                else:
                    if policy.last_rotation:
                        if policy.rotation_unit == 'daily' and \
                           policy.last_rotation < timezone.now() - timedelta(days=1):
                            pending.append(policy)
                        elif policy.rotation_unit == 'weekly' and \
                             policy.last_rotation < timezone.now() - timedelta(weeks=1):
                            pending.append(policy)
                        elif policy.rotation_unit == 'monthly' and \
                             policy.last_rotation < timezone.now() - timedelta(days=30):
                            pending.append(policy)
        
        serializer = self.get_serializer(pending, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get log management statistics"""
        now = timezone.now()
        stats = {
            'total_logs': LogFile.objects.count(),
            'total_entries': LogEntry.objects.count(),
            'entries_by_severity': dict(
                LogEntry.objects.values('severity')
                .annotate(count=Count('id'))
                .values_list('severity', 'count')
            ),
            'entries_by_source': dict(
                LogEntry.objects.values('source')
                .annotate(count=Count('id'))
                .values_list('source', 'count')
            ),
            'entries_last_24h': LogEntry.objects.filter(
                timestamp__gte=now - timedelta(hours=24)
            ).count(),
            'active_alerts': LogAlert.objects.filter(is_active=True).count(),
            'total_size': sum(
                os.path.getsize(log.path)
                for log in LogFile.objects.all()
                if os.path.exists(log.path)
            ),
            'rotation_pending': len(self.pending_rotations(request).data)
        }
        
        serializer = LogStatisticsSerializer(stats)
        return Response(serializer.data)
