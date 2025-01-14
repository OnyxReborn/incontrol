import psutil
import time
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from .models import (
    MetricSnapshot,
    ServiceStatus,
    Alert,
    AlertRule,
    NetworkInterface,
    DiskPartition,
    Process,
    ServiceLog
)

@shared_task
def collect_metrics():
    """Collect system metrics and store them."""
    try:
        # Get system metrics
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load = psutil.getloadavg()
        net_io = psutil.net_io_counters()

        # Create metrics snapshot
        metrics = MetricSnapshot.objects.create(
            cpu_usage=cpu,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            network_in=net_io.bytes_recv,
            network_out=net_io.bytes_sent,
            load_average_1m=load[0],
            load_average_5m=load[1],
            load_average_15m=load[2]
        )

        # Send update via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'monitoring_resource_monitoring',
            {
                'type': 'resource_update',
            }
        )

        return True
    except Exception as e:
        print(f"Error collecting metrics: {str(e)}")
        return False

@shared_task
def check_alert_rules():
    """Check alert rules against current metrics."""
    try:
        metrics = MetricSnapshot.objects.first()
        if not metrics:
            return False

        rules = AlertRule.objects.filter(is_active=True)
        for rule in rules:
            # Skip if in cooldown period
            if rule.last_triggered and (timezone.now() - rule.last_triggered).total_seconds() < rule.cooldown_period * 60:
                continue

            value = getattr(metrics, rule.metric, None)
            if value is None:
                continue

            triggered = False
            if rule.condition == 'gt' and value > rule.threshold:
                triggered = True
            elif rule.condition == 'lt' and value < rule.threshold:
                triggered = True
            elif rule.condition == 'eq' and value == rule.threshold:
                triggered = True
            elif rule.condition == 'ne' and value != rule.threshold:
                triggered = True

            if triggered:
                Alert.objects.create(
                    type=f"{rule.metric}_alert",
                    severity=rule.severity,
                    message=f"{rule.metric} is {rule.condition} {rule.threshold} (current value: {value})"
                )
                rule.last_triggered = timezone.now()
                rule.save()

        return True
    except Exception as e:
        print(f"Error checking alert rules: {str(e)}")
        return False

@shared_task
def cleanup_old_metrics():
    """Clean up old metric records."""
    try:
        # Keep only last 24 hours of metrics
        cutoff = timezone.now() - timezone.timedelta(hours=24)
        MetricSnapshot.objects.filter(timestamp__lt=cutoff).delete()
        return True
    except Exception as e:
        print(f"Error cleaning up old metrics: {str(e)}")
        return False

@shared_task
def update_service_uptimes():
    """Update service uptimes."""
    try:
        services = ServiceStatus.objects.filter(status='running')
        for service in services:
            service.uptime += 60  # Add one minute
            service.save()

        # Send update via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'monitoring_service_monitoring',
            {
                'type': 'service_update',
            }
        )

        return True
    except Exception as e:
        print(f"Error updating service uptimes: {str(e)}")
        return False

@shared_task
def monitor_system_health():
    """Monitor overall system health."""
    try:
        # Update process information
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status', 'create_time', 'cmdline']):
            try:
                pinfo = proc.info
                Process.objects.update_or_create(
                    pid=pinfo['pid'],
                    defaults={
                        'name': pinfo['name'],
                        'username': pinfo['username'],
                        'cpu_percent': pinfo['cpu_percent'],
                        'memory_percent': pinfo['memory_percent'],
                        'status': pinfo['status'],
                        'created_time': timezone.datetime.fromtimestamp(pinfo['create_time']),
                        'command': ' '.join(pinfo['cmdline'] or [])
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Clean up old process entries
        Process.objects.filter(
            last_updated__lt=timezone.now() - timezone.timedelta(minutes=5)
        ).delete()

        # Send update via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'monitoring_process_monitoring',
            {
                'type': 'process_update',
            }
        )

        return True
    except Exception as e:
        print(f"Error monitoring system health: {str(e)}")
        return False 