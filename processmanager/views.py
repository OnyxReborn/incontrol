import psutil
import subprocess
from django.utils import timezone
from django.db.models import Count
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Process, Service, ResourceUsage, ProcessLimit, ProcessAlert
from .serializers import (
    ProcessSerializer, ServiceSerializer, ResourceUsageSerializer,
    ProcessLimitSerializer, ProcessAlertSerializer, ProcessStatisticsSerializer
)
from .tasks import monitor_process_limits

class ProcessViewSet(viewsets.ModelViewSet):
    queryset = Process.objects.all()
    serializer_class = ProcessSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Process.objects.all()
        status = self.request.query_params.get('status', None)
        user = self.request.query_params.get('user', None)
        
        if status:
            queryset = queryset.filter(status=status)
        if user:
            queryset = queryset.filter(user=user)
            
        return queryset

    @action(detail=True, methods=['post'])
    def kill(self, request, pk=None):
        """Kill a process"""
        process = self.get_object()
        try:
            psutil.Process(process.pid).kill()
            process.status = 'dead'
            process.save()
            return Response({'status': 'process killed'})
        except psutil.NoSuchProcess:
            return Response(
                {'error': 'Process no longer exists'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        """Suspend a process"""
        process = self.get_object()
        try:
            psutil.Process(process.pid).suspend()
            process.status = 'stopped'
            process.save()
            return Response({'status': 'process suspended'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume a suspended process"""
        process = self.get_object()
        try:
            psutil.Process(process.pid).resume()
            process.status = 'running'
            process.save()
            return Response({'status': 'process resumed'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Service.objects.all()
        status = self.request.query_params.get('status', None)
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a service"""
        service = self.get_object()
        try:
            result = subprocess.run(['systemctl', 'start', service.name],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                service.status = 'active'
                service.save()
                return Response({'status': 'service started'})
            return Response(
                {'error': result.stderr},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop a service"""
        service = self.get_object()
        try:
            result = subprocess.run(['systemctl', 'stop', service.name],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                service.status = 'inactive'
                service.save()
                return Response({'status': 'service stopped'})
            return Response(
                {'error': result.stderr},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """Restart a service"""
        service = self.get_object()
        try:
            result = subprocess.run(['systemctl', 'restart', service.name],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                service.status = 'active'
                service.restart_count += 1
                service.last_restart = timezone.now()
                service.save()
                return Response({'status': 'service restarted'})
            return Response(
                {'error': result.stderr},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ResourceUsageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ResourceUsage.objects.all()
    serializer_class = ResourceUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ResourceUsage.objects.all()
        hours = self.request.query_params.get('hours', 24)
        since = timezone.now() - timezone.timedelta(hours=int(hours))
        return queryset.filter(timestamp__gte=since)

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk_io = psutil.disk_io_counters()
            net_io = psutil.net_io_counters()
            load_avg = psutil.getloadavg()

            usage = ResourceUsage.objects.create(
                timestamp=timezone.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                swap_percent=swap.percent,
                disk_io_read=disk_io.read_bytes,
                disk_io_write=disk_io.write_bytes,
                network_io_receive=net_io.bytes_recv,
                network_io_send=net_io.bytes_sent,
                load_1m=load_avg[0],
                load_5m=load_avg[1],
                load_15m=load_avg[2],
                process_count=len(psutil.pids()),
                thread_count=sum(p.num_threads() for p in psutil.process_iter())
            )

            return Response(ResourceUsageSerializer(usage).data)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ProcessLimitViewSet(viewsets.ModelViewSet):
    queryset = ProcessLimit.objects.all()
    serializer_class = ProcessLimitSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        limit = serializer.save(created_by=self.request.user)
        monitor_process_limits.delay()

class ProcessAlertViewSet(viewsets.ModelViewSet):
    queryset = ProcessAlert.objects.all()
    serializer_class = ProcessAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ProcessAlert.objects.all()
        severity = self.request.query_params.get('severity', None)
        resolved = self.request.query_params.get('resolved', None)
        
        if severity:
            queryset = queryset.filter(severity=severity)
        if resolved is not None:
            queryset = queryset.filter(is_resolved=resolved.lower() == 'true')
            
        return queryset

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark an alert as resolved"""
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()
        return Response({'status': 'alert resolved'})

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get process statistics"""
        now = timezone.now()
        
        stats = {
            'total_processes': Process.objects.count(),
            'running_processes': Process.objects.filter(status='running').count(),
            'sleeping_processes': Process.objects.filter(status='sleeping').count(),
            'stopped_processes': Process.objects.filter(status='stopped').count(),
            'zombie_processes': Process.objects.filter(status='zombie').count(),
            'total_threads': sum(p.num_threads() for p in psutil.process_iter()),
            'cpu_usage': psutil.cpu_percent(interval=1),
            'memory_usage': psutil.virtual_memory().percent,
            'swap_usage': psutil.swap_memory().percent,
            'load_averages': {
                '1m': psutil.getloadavg()[0],
                '5m': psutil.getloadavg()[1],
                '15m': psutil.getloadavg()[2]
            },
            'top_cpu_processes': list(
                Process.objects.order_by('-cpu_percent')[:5].values('name', 'cpu_percent')
            ),
            'top_memory_processes': list(
                Process.objects.order_by('-memory_percent')[:5].values('name', 'memory_percent')
            ),
            'active_services': Service.objects.filter(status='active').count(),
            'failed_services': Service.objects.filter(status='failed').count(),
            'recent_alerts': ProcessAlert.objects.filter(
                created_at__gte=now - timezone.timedelta(hours=24)
            ).count(),
            'unresolved_alerts': ProcessAlert.objects.filter(is_resolved=False).count()
        }

        serializer = ProcessStatisticsSerializer(stats)
        return Response(serializer.data) 