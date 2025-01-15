import psutil
import json
from datetime import datetime, timedelta
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from .models import MetricSnapshot, ServiceStatus, Alert, AlertRule
from .serializers import MetricSnapshotSerializer, ServiceStatusSerializer, AlertSerializer

channel_layer = get_channel_layer()

@shared_task
def collect_metrics():
    try:
        # Collect system metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        load = psutil.getloadavg()

        # Create metrics snapshot
        metrics = MetricSnapshot.objects.create(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            disk_percent=disk.percent,
            network_rx_bytes=network.bytes_recv,
            network_tx_bytes=network.bytes_sent,
            load_1=load[0],
            load_5=load[1],
            load_15=load[2]
        )

        # Serialize and send update via WebSocket
        serialized_metrics = MetricSnapshotSerializer(metrics).data
        async_to_sync(channel_layer.group_send)(
            'resource_monitoring',
            {
                'type': 'metric_update',
                'metrics': serialized_metrics
            }
        )

        # Check alert rules
        check_alert_rules(metrics)

        # Cleanup old metrics
        cleanup_old_metrics()

        return True
    except Exception as e:
        print(f"Error collecting metrics: {e}")
        return False

@shared_task
def update_service_uptimes():
    try:
        services = ServiceStatus.objects.all()
        for service in services:
            try:
                # Update service status and uptime
                service_info = psutil.Process(service.pid) if service.pid else None
                if service_info and service_info.is_running():
                    service.status = 'running'
                    service.uptime = timezone.now() - timezone.make_aware(
                        datetime.fromtimestamp(service_info.create_time())
                    )
                else:
                    service.status = 'stopped'
                    service.uptime = timedelta(0)
                service.save()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                service.status = 'error'
                service.uptime = timedelta(0)
                service.save()

        # Send update via WebSocket
        serialized_services = ServiceStatusSerializer(services, many=True).data
        async_to_sync(channel_layer.group_send)(
            'service_monitoring',
            {
                'type': 'service_update',
                'services': serialized_services
            }
        )

        return True
    except Exception as e:
        print(f"Error updating service uptimes: {e}")
        return False

@shared_task
def monitor_system_health():
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status']):
            try:
                pinfo = proc.as_dict()
                processes.append({
                    'pid': pinfo['pid'],
                    'name': pinfo['name'],
                    'user': pinfo['username'],
                    'cpu_percent': pinfo['cpu_percent'],
                    'memory_percent': pinfo['memory_percent'],
                    'status': pinfo['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Send update via WebSocket
        async_to_sync(channel_layer.group_send)(
            'process_monitoring',
            {
                'type': 'process_update',
                'processes': processes
            }
        )

        return True
    except Exception as e:
        print(f"Error monitoring system health: {e}")
        return False

def check_alert_rules(metrics):
    try:
        rules = AlertRule.objects.filter(enabled=True)
        for rule in rules:
            threshold_exceeded = False
            metric_value = None

            if rule.metric_type == 'cpu':
                metric_value = metrics.cpu_percent
            elif rule.metric_type == 'memory':
                metric_value = metrics.memory_percent
            elif rule.metric_type == 'disk':
                metric_value = metrics.disk_percent
            elif rule.metric_type == 'load':
                metric_value = metrics.load_1

            if metric_value is not None:
                if rule.condition == 'above' and metric_value > rule.threshold:
                    threshold_exceeded = True
                elif rule.condition == 'below' and metric_value < rule.threshold:
                    threshold_exceeded = True

            if threshold_exceeded:
                alert = Alert.objects.create(
                    rule=rule,
                    message=f"{rule.metric_type.upper()} usage is {metric_value}% ({rule.condition} threshold of {rule.threshold}%)",
                    severity=rule.severity
                )

                # Send alert via WebSocket
                serialized_alert = AlertSerializer(alert).data
                async_to_sync(channel_layer.group_send)(
                    'alert_monitoring',
                    {
                        'type': 'alert_update',
                        'alerts': [serialized_alert]
                    }
                )

    except Exception as e:
        print(f"Error checking alert rules: {e}")

def cleanup_old_metrics():
    try:
        # Keep only the last 24 hours of metrics
        cutoff = timezone.now() - timedelta(hours=24)
        MetricSnapshot.objects.filter(timestamp__lt=cutoff).delete()
    except Exception as e:
        print(f"Error cleaning up old metrics: {e}") 