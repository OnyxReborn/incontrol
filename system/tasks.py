import subprocess
from celery import shared_task
from django.utils import timezone
from .models import Service, Package
from core.models import SystemMetrics, Notification

@shared_task
def monitor_services():
    """Monitor all active services and update their status."""
    services = Service.objects.filter(is_monitored=True)
    for service in services:
        try:
            result = subprocess.run(['systemctl', 'is-active', service.name],
                                 capture_output=True, text=True)
            old_status = service.status
            service.status = 'running' if result.returncode == 0 else 'stopped'
            service.last_check = timezone.now()
            service.save()

            # Create notification if service status changed
            if old_status != service.status:
                Notification.objects.create(
                    title=f"Service Status Change: {service.name}",
                    message=f"Service {service.name} changed from {old_status} to {service.status}",
                    level='WARNING' if service.status == 'stopped' else 'INFO'
                )
        except Exception as e:
            service.status = 'error'
            service.save()
            Notification.objects.create(
                title=f"Service Error: {service.name}",
                message=f"Error monitoring service {service.name}: {str(e)}",
                level='ERROR'
            )

@shared_task
def check_system_updates():
    """Check for available system updates."""
    try:
        # Update package lists
        update_result = subprocess.run(['apt-get', 'update'],
                                    capture_output=True, text=True)
        if update_result.returncode != 0:
            raise Exception(update_result.stderr)

        # Check for upgradeable packages
        upgrade_result = subprocess.run(['apt-get', '-s', 'upgrade'],
                                     capture_output=True, text=True)
        if upgrade_result.returncode != 0:
            raise Exception(upgrade_result.stderr)

        # Parse output to count upgradeable packages
        upgradeable = len([line for line in upgrade_result.stdout.split('\n')
                          if line.startswith('Inst ')])

        if upgradeable > 0:
            Notification.objects.create(
                title="System Updates Available",
                message=f"{upgradeable} package(s) can be upgraded.",
                level='INFO'
            )

    except Exception as e:
        Notification.objects.create(
            title="Update Check Failed",
            message=f"Failed to check for system updates: {str(e)}",
            level='ERROR'
        )

@shared_task
def collect_system_metrics():
    """Collect and store system metrics."""
    try:
        # Get CPU usage
        cpu_result = subprocess.run(['top', '-bn1'],
                                 capture_output=True, text=True)
        cpu_lines = cpu_result.stdout.split('\n')
        cpu_usage = float(cpu_lines[2].split()[1])

        # Get memory info
        with open('/proc/meminfo', 'r') as f:
            mem_lines = f.readlines()
        total = int(mem_lines[0].split()[1])
        free = int(mem_lines[1].split()[1])
        memory_usage = ((total - free) / total) * 100

        # Get disk usage
        disk_result = subprocess.run(['df', '/'],
                                  capture_output=True, text=True)
        disk_lines = disk_result.stdout.split('\n')
        disk_usage = float(disk_lines[1].split()[4].strip('%'))

        # Create metrics record
        SystemMetrics.objects.create(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage
        )

        # Check thresholds and create notifications
        if cpu_usage > 90:
            Notification.objects.create(
                title="High CPU Usage",
                message=f"CPU usage is at {cpu_usage}%",
                level='WARNING'
            )
        if memory_usage > 90:
            Notification.objects.create(
                title="High Memory Usage",
                message=f"Memory usage is at {memory_usage}%",
                level='WARNING'
            )
        if disk_usage > 90:
            Notification.objects.create(
                title="High Disk Usage",
                message=f"Disk usage is at {disk_usage}%",
                level='WARNING'
            )

    except Exception as e:
        Notification.objects.create(
            title="Metrics Collection Failed",
            message=f"Failed to collect system metrics: {str(e)}",
            level='ERROR'
        ) 