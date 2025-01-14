import os
import psutil
import platform
import datetime
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import (
    MetricSnapshot,
    ServiceStatus,
    Alert,
    AlertRule,
    NetworkInterface,
    DiskPartition,
    Process,
    ServiceLog,
)
from .serializers import (
    MetricSnapshotSerializer,
    ServiceStatusSerializer,
    AlertSerializer,
    AlertRuleSerializer,
    NetworkInterfaceSerializer,
    DiskPartitionSerializer,
    ProcessSerializer,
    ServiceLogSerializer,
    SystemMetricsSerializer,
    ResourceUsageSerializer,
    SystemInfoSerializer,
    NetworkStatsSerializer,
    AlertRuleTestResultSerializer,
)
from .tasks import collect_metrics, check_alert_rules

class MonitoringViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def metrics(self, request):
        # Get current system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net_io = psutil.net_io_counters()
        
        data = {
            'cpu_usage': cpu_percent,
            'memory_usage': memory.percent,
            'disk_usage': disk.percent,
            'network_in': net_io.bytes_recv,
            'network_out': net_io.bytes_sent,
            'load_average': psutil.getloadavg(),
            'uptime': int(time.time() - psutil.boot_time()),
        }

        serializer = SystemMetricsSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def historical(self, request):
        time_range = request.query_params.get('time_range', '24h')
        
        # Convert time range to timedelta
        if time_range == '1h':
            delta = timezone.timedelta(hours=1)
        elif time_range == '7d':
            delta = timezone.timedelta(days=7)
        elif time_range == '30d':
            delta = timezone.timedelta(days=30)
        else:  # 24h default
            delta = timezone.timedelta(days=1)

        start_time = timezone.now() - delta
        snapshots = MetricSnapshot.objects.filter(timestamp__gte=start_time)
        
        data = []
        for snapshot in snapshots:
            data.append({
                'timestamp': snapshot.timestamp,
                'cpu': snapshot.cpu_usage,
                'memory': snapshot.memory_usage,
                'disk': snapshot.disk_usage,
                'network_in': snapshot.network_in,
                'network_out': snapshot.network_out,
            })

        serializer = ResourceUsageSerializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def services(self, request):
        services = ServiceStatus.objects.all()
        serializer = ServiceStatusSerializer(services, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def alerts(self, request):
        alerts = Alert.objects.all()
        serializer = AlertSerializer(alerts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def system_info(self, request):
        uname = platform.uname()
        data = {
            'hostname': uname.node,
            'os': f"{uname.system} {uname.release}",
            'platform': platform.platform(),
            'cpu_count': psutil.cpu_count(),
            'total_memory': psutil.virtual_memory().total,
            'total_disk': psutil.disk_usage('/').total,
            'python_version': platform.python_version(),
            'timezone': str(timezone.get_current_timezone()),
        }
        
        serializer = SystemInfoSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def disk_usage(self, request):
        partitions = DiskPartition.objects.all()
        serializer = DiskPartitionSerializer(partitions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def network_interfaces(self, request):
        interfaces = NetworkInterface.objects.all()
        serializer = NetworkInterfaceSerializer(interfaces, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def processes(self, request):
        processes = Process.objects.all().order_by('-cpu_percent')[:50]
        serializer = ProcessSerializer(processes, many=True)
        return Response(serializer.data)

class ServiceStatusViewSet(viewsets.ModelViewSet):
    queryset = ServiceStatus.objects.all()
    serializer_class = ServiceStatusSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        service = self.get_object()
        try:
            # Implement service restart logic
            os.system(f"systemctl restart {service.name}")
            service.status = 'running'
            service.save()
            ServiceLog.objects.create(
                service=service,
                level='info',
                message=f'Service {service.name} restarted'
            )
            return Response({'status': 'service restarted'})
        except Exception as e:
            ServiceLog.objects.create(
                service=service,
                level='error',
                message=f'Failed to restart service {service.name}: {str(e)}'
            )
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        service = self.get_object()
        try:
            os.system(f"systemctl stop {service.name}")
            service.status = 'stopped'
            service.save()
            ServiceLog.objects.create(
                service=service,
                level='info',
                message=f'Service {service.name} stopped'
            )
            return Response({'status': 'service stopped'})
        except Exception as e:
            ServiceLog.objects.create(
                service=service,
                level='error',
                message=f'Failed to stop service {service.name}: {str(e)}'
            )
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        service = self.get_object()
        try:
            os.system(f"systemctl start {service.name}")
            service.status = 'running'
            service.save()
            ServiceLog.objects.create(
                service=service,
                level='info',
                message=f'Service {service.name} started'
            )
            return Response({'status': 'service started'})
        except Exception as e:
            ServiceLog.objects.create(
                service=service,
                level='error',
                message=f'Failed to start service {service.name}: {str(e)}'
            )
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        service = self.get_object()
        logs = ServiceLog.objects.filter(service=service)
        serializer = ServiceLogSerializer(logs, many=True)
        return Response(serializer.data)

class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        if alert.status == 'active':
            alert.status = 'resolved'
            alert.resolved_at = timezone.now()
            alert.resolution_note = request.data.get('note', '')
            alert.save()
        return Response({'status': 'alert acknowledged'})

class AlertRuleViewSet(viewsets.ModelViewSet):
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        rule = self.get_object()
        
        # Get current value for the metric
        if rule.metric == 'cpu_usage':
            current_value = psutil.cpu_percent(interval=1)
        elif rule.metric == 'memory_usage':
            current_value = psutil.virtual_memory().percent
        elif rule.metric == 'disk_usage':
            current_value = psutil.disk_usage('/').percent
        else:
            current_value = 0

        # Test if rule would trigger
        triggered = False
        if rule.condition == 'gt' and current_value > rule.threshold:
            triggered = True
        elif rule.condition == 'lt' and current_value < rule.threshold:
            triggered = True
        elif rule.condition == 'eq' and current_value == rule.threshold:
            triggered = True
        elif rule.condition == 'ne' and current_value != rule.threshold:
            triggered = True

        data = {
            'triggered': triggered,
            'current_value': current_value,
            'threshold': rule.threshold,
            'message': f"Alert would{' ' if triggered else ' not '}trigger",
            'would_notify': rule.notification_channels if triggered else [],
        }

        serializer = AlertRuleTestResultSerializer(data)
        return Response(serializer.data)

class NetworkInterfaceViewSet(viewsets.ModelViewSet):
    queryset = NetworkInterface.objects.all()
    serializer_class = NetworkInterfaceSerializer
    permission_classes = [IsAuthenticated]

class DiskPartitionViewSet(viewsets.ModelViewSet):
    queryset = DiskPartition.objects.all()
    serializer_class = DiskPartitionSerializer
    permission_classes = [IsAuthenticated]

class ProcessViewSet(viewsets.ModelViewSet):
    queryset = Process.objects.all()
    serializer_class = ProcessSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Process.objects.all()
        sort_by = self.request.query_params.get('sort', '-cpu_percent')
        search = self.request.query_params.get('search', '')
        
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(username__icontains=search)
            )
        
        return queryset.order_by(sort_by)[:50] 