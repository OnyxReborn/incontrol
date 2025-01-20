from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from .models import (
    SSLCertificate, ResourceUsage, BandwidthUsage, VirtualHost, 
    AccessLog, ErrorLog, BackupJob, BackupConfig
)
import os
import subprocess
import tarfile
import tempfile
import shutil
import psutil
import re
from collections import defaultdict
from datetime import datetime
from django.conf import settings

# Configure logger
logger = logging.getLogger(__name__)

@shared_task
def check_ssl_certificates():
    """Check SSL certificates for expiration."""
    certificates = SSLCertificate.objects.all()
    warning_threshold = timezone.now() + timedelta(days=30)
    critical_threshold = timezone.now() + timedelta(days=7)

    for cert in certificates:
        try:
            # Critical warning for certificates expiring within 7 days
            if cert.expiry_date <= critical_threshold:
                Notification.objects.create(
                    title=f"SSL Certificate Critical: {cert.name}",
                    message=f"SSL Certificate for {cert.domains} will expire in "
                           f"{(cert.expiry_date - timezone.now()).days} days!",
                    level='CRITICAL'
                )
            # Warning for certificates expiring within 30 days
            elif cert.expiry_date <= warning_threshold:
                Notification.objects.create(
                    title=f"SSL Certificate Warning: {cert.name}",
                    message=f"SSL Certificate for {cert.domains} will expire in "
                           f"{(cert.expiry_date - timezone.now()).days} days.",
                    level='WARNING'
                )

            # Auto-renew Let's Encrypt certificates
            if cert.certificate_type == 'lets_encrypt' and cert.auto_renew:
                if cert.expiry_date <= warning_threshold:
                    renew_lets_encrypt_certificate.delay(cert.id)

        except Exception as e:
            Notification.objects.create(
                title=f"SSL Certificate Check Error: {cert.name}",
                message=f"Error checking certificate: {str(e)}",
                level='ERROR'
            )

@shared_task
def renew_lets_encrypt_certificate(cert_id):
    """Renew a Let's Encrypt certificate."""
    from subprocess import run, CalledProcessError
    
    try:
        cert = SSLCertificate.objects.get(id=cert_id)
        if cert.certificate_type != 'lets_encrypt':
            raise ValueError("Not a Let's Encrypt certificate")

        # Run certbot renew for specific domains
        domains = cert.domains_list
        cmd = ['certbot', 'renew', '--non-interactive', '--cert-name', domains[0]]
        
        result = run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)

        # Update certificate record
        cert.issued_date = timezone.now()
        cert.expiry_date = timezone.now() + timedelta(days=90)
        cert.save()

        Notification.objects.create(
            title=f"SSL Certificate Renewed: {cert.name}",
            message=f"Successfully renewed Let's Encrypt certificate for {cert.domains}",
            level='INFO'
        )

    except Exception as e:
        Notification.objects.create(
            title=f"SSL Certificate Renewal Error",
            message=f"Failed to renew certificate: {str(e)}",
            level='ERROR'
        ) 

@shared_task
def create_backup(backup_job_id):
    backup_job = None
    try:
        backup_job = BackupJob.objects.get(id=backup_job_id)
        backup_job.status = 'running'
        backup_job.save()
        
        # Get backup config
        config = backup_job.config
        
        # Create temp directory for backup
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create tar file
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'backup_{timestamp}.tar.gz'
            backup_path = os.path.join(config.backup_directory, backup_filename)
            
            with tarfile.open(backup_path, 'w:gz') as tar:
                # Backup nginx config
                nginx_conf_dir = '/etc/nginx'
                if os.path.exists(nginx_conf_dir):
                    tar.add(nginx_conf_dir, arcname='nginx')
                
                # Backup SSL certificates
                ssl_certs_dir = '/etc/ssl'
                if os.path.exists(ssl_certs_dir):
                    tar.add(ssl_certs_dir, arcname='ssl')
                
                # Backup database
                db_backup_path = os.path.join(temp_dir, 'database.sql')
                with open(db_backup_path, 'w') as f:
                    subprocess.run(['pg_dump', settings.DATABASES['default']['NAME']], 
                                stdout=f, check=True)
                tar.add(db_backup_path, arcname='database.sql')
            
            # Update backup job
            backup_job.file_path = backup_path
            backup_job.status = 'completed'
            backup_job.completed_at = timezone.now()
            backup_job.save()
            
            # Cleanup old backups
            cleanup_old_backups(config)
            
    except Exception as e:
        logger.error(f'Backup failed: {str(e)}')
        if backup_job:
            backup_job.status = 'failed'
            backup_job.error_message = str(e)
            backup_job.save()
        raise

@shared_task
def restore_backup(backup_job_id):
    backup_job = None
    try:
        backup_job = BackupJob.objects.get(id=backup_job_id)
        backup_job.status = 'restoring'
        backup_job.save()
        
        if not os.path.exists(backup_job.file_path):
            raise FileNotFoundError(f'Backup file not found: {backup_job.file_path}')
        
        # Create temp directory for restore
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract backup
            with tarfile.open(backup_job.file_path, 'r:gz') as tar:
                tar.extractall(temp_dir)
            
            # Restore nginx config
            nginx_backup = os.path.join(temp_dir, 'nginx')
            if os.path.exists(nginx_backup):
                subprocess.run(['rm', '-rf', '/etc/nginx'], check=True)
                subprocess.run(['cp', '-r', nginx_backup, '/etc/nginx'], check=True)
                subprocess.run(['nginx', '-t'], check=True)  # Test config
                subprocess.run(['nginx', '-s', 'reload'], check=True)
            
            # Restore SSL certificates
            ssl_backup = os.path.join(temp_dir, 'ssl')
            if os.path.exists(ssl_backup):
                subprocess.run(['rm', '-rf', '/etc/ssl'], check=True)
                subprocess.run(['cp', '-r', ssl_backup, '/etc/ssl'], check=True)
            
            # Restore database
            db_backup = os.path.join(temp_dir, 'database.sql')
            if os.path.exists(db_backup):
                subprocess.run(['psql', settings.DATABASES['default']['NAME'], 
                             '-f', db_backup], check=True)
        
        backup_job.status = 'restored'
        backup_job.completed_at = timezone.now()
        backup_job.save()
        
    except Exception as e:
        logger.error(f'Restore failed: {str(e)}')
        if backup_job:
            backup_job.status = 'failed'
            backup_job.error_message = str(e)
            backup_job.save()
        raise

def cleanup_old_backups(config):
    """Delete backups older than retention_days"""
    retention_date = timezone.now() - timedelta(days=config.retention_days)
    old_backups = BackupJob.objects.filter(
        config=config,
        status='completed',
        completed_at__lt=retention_date
    )
    
    for backup in old_backups:
        try:
            os.remove(backup.file_path)
            backup.delete()
        except OSError:
            logger.warning(f"Could not delete backup file: {backup.file_path}") 

@shared_task
def collect_resource_usage():
    """Collect system resource usage statistics"""
    # Get CPU usage
    cpu_usage = psutil.cpu_percent(interval=1)
    
    # Get memory usage
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    
    # Get disk usage
    disk = psutil.disk_usage('/')
    disk_usage = disk.percent
    
    # Get disk I/O
    disk_io = psutil.disk_io_counters()
    disk_read = disk_io.read_bytes
    disk_write = disk_io.write_bytes
    
    # Get network I/O
    net_io = psutil.net_io_counters()
    network_rx = net_io.bytes_recv
    network_tx = net_io.bytes_sent
    
    # Get load average
    load_avg = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
    
    ResourceUsage.objects.create(
        cpu_usage=cpu_usage,
        memory_usage=memory_usage,
        disk_usage=disk_usage,
        disk_read=disk_read,
        disk_write=disk_write,
        network_rx=network_rx,
        network_tx=network_tx,
        load_average=','.join(map(str, load_avg))
    )

@shared_task
def collect_bandwidth_usage():
    """Collect bandwidth usage statistics from Nginx logs"""
    # Initialize counters for each domain
    domain_stats = defaultdict(lambda: {'bytes_in': 0, 'bytes_out': 0, 'requests': 0})

    # Parse Nginx access logs
    nginx_pattern = r'(\d+\.\d+\.\d+\.\d+) .+ \[(.+)\] "(\w+) (.+) HTTP/\d\.\d" (\d+) (\d+) "([^"]*)" "([^"]*)" (\d+\.\d+)'
    with open('/var/log/nginx/access.log', 'r') as f:
        for line in f:
            match = re.match(nginx_pattern, line)
            if match:
                path = match.group(4)
                response_size = int(match.group(6))

                # Find matching domain
                for vh in VirtualHost.objects.all():
                    if any(domain in path for domain in vh.domains.split('\n')):
                        domain_stats[vh.id]['bytes_out'] += response_size
                        domain_stats[vh.id]['requests'] += 1
                        # Estimate bytes in based on request method and path length
                        domain_stats[vh.id]['bytes_in'] += len(path) + 100  # rough estimate
                        break

    # Save statistics
    for domain_id, stats in domain_stats.items():
        try:
            domain = VirtualHost.objects.get(id=domain_id)
            BandwidthUsage.objects.create(
                domain=domain,
                bytes_in=stats['bytes_in'],
                bytes_out=stats['bytes_out'],
                requests=stats['requests']
            )
        except VirtualHost.DoesNotExist:
            continue

@shared_task
def cleanup_old_statistics():
    """Clean up old statistics data"""
    # Keep resource usage data for 7 days
    cutoff_date = timezone.now() - timedelta(days=7)
    ResourceUsage.objects.filter(timestamp__lt=cutoff_date).delete()

    # Keep bandwidth usage data for 30 days
    cutoff_date = timezone.now() - timedelta(days=30)
    BandwidthUsage.objects.filter(timestamp__lt=cutoff_date).delete()

    # Keep access logs for 30 days
    AccessLog.objects.filter(timestamp__lt=cutoff_date).delete()

    # Keep error logs for 90 days
    cutoff_date = timezone.now() - timedelta(days=90)
    ErrorLog.objects.filter(timestamp__lt=cutoff_date).delete() 