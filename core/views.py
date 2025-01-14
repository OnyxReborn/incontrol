import psutil
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import SystemMetrics, Setting, AuditLog, Notification
from .serializers import (
    SystemMetricsSerializer,
    SettingSerializer,
    AuditLogSerializer,
    NotificationSerializer
)

class SystemMetricsViewSet(viewsets.ModelViewSet):
    queryset = SystemMetrics.objects.all()
    serializer_class = SystemMetricsSerializer
    permission_classes = [permissions.IsAdminUser]
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current system metrics."""
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net_io = psutil.net_io_counters()
        
        metrics = SystemMetrics.objects.create(
            cpu_usage=cpu,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            network_in=net_io.bytes_recv,
            network_out=net_io.bytes_sent
        )
        
        serializer = self.get_serializer(metrics)
        return Response(serializer.data)

class SettingViewSet(viewsets.ModelViewSet):
    queryset = Setting.objects.all()
    serializer_class = SettingSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = Setting.objects.all()
        key = self.request.query_params.get('key', None)
        if key is not None:
            queryset = queryset.filter(key=key)
        return queryset

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        queryset = AuditLog.objects.all()
        user_id = self.request.query_params.get('user_id', None)
        action = self.request.query_params.get('action', None)
        resource_type = self.request.query_params.get('resource_type', None)
        
        if user_id is not None:
            queryset = queryset.filter(user_id=user_id)
        if action is not None:
            queryset = queryset.filter(action=action)
        if resource_type is not None:
            queryset = queryset.filter(resource_type=resource_type)
            
        return queryset

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        notification.read = True
        notification.save()
        return Response({'status': 'notification marked as read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read."""
        self.get_queryset().update(read=True)
        return Response({'status': 'all notifications marked as read'})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = self.get_queryset().filter(read=False).count()
        return Response({'unread_count': count})
