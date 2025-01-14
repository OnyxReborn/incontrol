import psutil
import subprocess
from datetime import datetime
from celery import shared_task
from django.utils import timezone
from core.models import Notification
from .models import Process, Service, ResourceUsage, ProcessLimit, ProcessAlert

@shared_task
def update_process_list():
    """Update the list of running processes"""
    try:
        # Get current processes
        current_pids = set()
        for proc in psutil.process_iter(['pid', 'name', 'status', 'username', 'cpu_percent', 'memory_percent', 'cmdline']):
            try:
                info = proc.info
                current_pids.add(info['pid'])
                
                Process.objects.update_or_create(
                    pid=info['pid'],
                    defaults={
                        'name': info['name'],
                        'status': info['status'],
                        'user': info['username'],
                        'cpu_percent': info['cpu_percent'] or 0.0,
                        'memory_percent': info['memory_percent'] or 0.0,
                        'command': ' '.join(info['cmdline'] or [])
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Remove processes that no longer exist
        Process.objects.exclude(pid__in=current_pids).delete()

    except Exception as e:
        print(f"Failed to update process list: {str(e)}")

@shared_task
def update_service_status():
    """Update the status of system services"""
    try:
        # Get list of services
        result = subprocess.run(['systemctl', 'list-units', '--type=service', '--all', '--no-pager', '--plain'],
                             capture_output=True, text=True)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 4:
                    name = parts[0].replace('.service', '')
                    load_state = parts[1]
                    active_state = parts[2]
                    sub_state = parts[3]
                    
                    # Get unit file state
                    unit_result = subprocess.run(['systemctl', 'is-enabled', name],
                                              capture_output=True, text=True)
                    unit_file_state = unit_result.stdout.strip()
                    
                    status = 'active' if active_state == 'active' else \
                            'failed' if active_state == 'failed' else \
                            'inactive'
                    
                    service, created = Service.objects.update_or_create(
                        name=name,
                        defaults={
                            'status': status,
                            'is_enabled': unit_file_state == 'enabled',
                            'load_state': load_state,
                            'active_state': active_state,
                            'sub_state': sub_state,
                            'unit_file_state': unit_file_state
                        }
                    )
                    
                    # Create alert for failed services
                    if status == 'failed' and (created or service.status != 'failed'):
                        ProcessAlert.objects.create(
                            service=service,
                            title=f"Service Failed: {name}",
                            message=f"Service {name} has failed",
                            severity='critical',
                            resource_type='service',
                            value=0,
                            threshold=0
                        )

    except Exception as e:
        print(f"Failed to update service status: {str(e)}")

@shared_task
def collect_resource_usage():
    """Collect system resource usage metrics"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk_io = psutil.disk_io_counters()
        net_io = psutil.net_io_counters()
        load_avg = psutil.getloadavg()

        ResourceUsage.objects.create(
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

        # Check resource thresholds
        if cpu_percent > 90:
            ProcessAlert.objects.create(
                title="High CPU Usage",
                message=f"CPU usage is at {cpu_percent}%",
                severity='critical',
                resource_type='cpu',
                value=cpu_percent,
                threshold=90
            )

        if memory.percent > 90:
            ProcessAlert.objects.create(
                title="High Memory Usage",
                message=f"Memory usage is at {memory.percent}%",
                severity='critical',
                resource_type='memory',
                value=memory.percent,
                threshold=90
            )

        if swap.percent > 80:
            ProcessAlert.objects.create(
                title="High Swap Usage",
                message=f"Swap usage is at {swap.percent}%",
                severity='warning',
                resource_type='swap',
                value=swap.percent,
                threshold=80
            )

    except Exception as e:
        print(f"Failed to collect resource usage: {str(e)}")

@shared_task
def monitor_process_limits():
    """Monitor processes against defined limits"""
    try:
        limits = ProcessLimit.objects.filter(is_active=True)
        
        for limit in limits:
            if limit.resource == 'cpu':
                processes = Process.objects.filter(cpu_percent__gt=limit.limit_value)
                for process in processes:
                    ProcessAlert.objects.create(
                        process=process,
                        title=f"High CPU Usage: {process.name}",
                        message=f"Process {process.name} (PID {process.pid}) CPU usage is at {process.cpu_percent}%",
                        severity='warning',
                        resource_type='cpu',
                        value=process.cpu_percent,
                        threshold=limit.limit_value
                    )
                    
                    if limit.action == 'kill':
                        try:
                            psutil.Process(process.pid).kill()
                        except:
                            pass

            elif limit.resource == 'memory':
                processes = Process.objects.filter(memory_percent__gt=limit.limit_value)
                for process in processes:
                    ProcessAlert.objects.create(
                        process=process,
                        title=f"High Memory Usage: {process.name}",
                        message=f"Process {process.name} (PID {process.pid}) memory usage is at {process.memory_percent}%",
                        severity='warning',
                        resource_type='memory',
                        value=process.memory_percent,
                        threshold=limit.limit_value
                    )
                    
                    if limit.action == 'kill':
                        try:
                            psutil.Process(process.pid).kill()
                        except:
                            pass

    except Exception as e:
        print(f"Failed to monitor process limits: {str(e)}")

@shared_task
def cleanup_old_resource_data():
    """Clean up old resource usage data"""
    try:
        threshold = timezone.now() - timezone.timedelta(days=7)
        ResourceUsage.objects.filter(timestamp__lt=threshold).delete()
    except Exception as e:
        print(f"Failed to clean up old resource data: {str(e)}")

@shared_task
def monitor_zombie_processes():
    """Monitor and report zombie processes"""
    try:
        zombie_count = Process.objects.filter(status='zombie').count()
        if zombie_count > 10:
            ProcessAlert.objects.create(
                title="High Number of Zombie Processes",
                message=f"There are {zombie_count} zombie processes in the system",
                severity='warning',
                resource_type='process',
                value=zombie_count,
                threshold=10
            )
    except Exception as e:
        print(f"Failed to monitor zombie processes: {str(e)}")

@shared_task
def check_service_health():
    """Check health of critical services"""
    critical_services = [
        'sshd', 'nginx', 'apache2', 'mysql', 'postgresql',
        'redis', 'memcached', 'docker', 'cron'
    ]
    
    try:
        for service_name in critical_services:
            result = subprocess.run(['systemctl', 'is-active', service_name],
                                 capture_output=True, text=True)
            
            if result.stdout.strip() != 'active':
                service = Service.objects.filter(name=service_name).first()
                if service:
                    ProcessAlert.objects.create(
                        service=service,
                        title=f"Critical Service Down: {service_name}",
                        message=f"Critical service {service_name} is not running",
                        severity='critical',
                        resource_type='service',
                        value=0,
                        threshold=0
                    )
    except Exception as e:
        print(f"Failed to check service health: {str(e)}") 