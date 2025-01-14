import os
import re
import gzip
import bz2
import lzma
import shutil
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count
from celery import shared_task
from core.models import Notification
from .models import LogFile, LogEntry, LogAlert, LogRotationPolicy

@shared_task
def monitor_log_files():
    """Monitor log files for changes and update entries"""
    for log_file in LogFile.objects.filter(is_active=True):
        try:
            if not os.path.exists(log_file.path):
                continue

            # Get file modification time
            mtime = os.path.getmtime(log_file.path)
            last_entry = LogEntry.objects.filter(log_file=log_file).order_by('-timestamp').first()

            if not last_entry or mtime > last_entry.timestamp.timestamp():
                with open(log_file.path, 'r') as f:
                    # Read only new lines
                    if last_entry:
                        f.seek(0, 2)  # Seek to end
                        file_size = f.tell()
                        f.seek(0)  # Seek to start
                        
                    lines = f.readlines()
                    for line in lines:
                        parse_log_line.delay(log_file.id, line)

        except Exception as e:
            print(f"Error monitoring log file {log_file.path}: {str(e)}")

@shared_task
def parse_log_line(log_file_id, line):
    """Parse a log line and create a LogEntry"""
    try:
        log_file = LogFile.objects.get(id=log_file_id)
        
        # Basic parsing - can be extended based on log format
        timestamp_pattern = r'\[(.*?)\]'
        severity_pattern = r'(DEBUG|INFO|WARNING|ERROR|CRITICAL)'
        source_pattern = r'\[(.*?)\]'
        
        timestamp_match = re.search(timestamp_pattern, line)
        severity_match = re.search(severity_pattern, line)
        source_match = re.search(source_pattern, line)
        
        timestamp = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S') if timestamp_match else timezone.now()
        severity = severity_match.group(1).lower() if severity_match else 'info'
        source = source_match.group(1) if source_match else 'unknown'
        
        entry = LogEntry.objects.create(
            log_file=log_file,
            timestamp=timestamp,
            severity=severity,
            source=source,
            message=line.strip(),
            raw_data=line
        )
        
        # Process alerts for this entry
        process_log_alerts.delay(entry.id)
        
    except Exception as e:
        print(f"Error parsing log line: {str(e)}")

@shared_task
def process_log_alerts(entry_id=None, test_mode=False):
    """Process log alerts for new entries"""
    try:
        alerts = LogAlert.objects.filter(is_active=True)
        if not test_mode:
            entry = LogEntry.objects.get(id=entry_id)
            
            for alert in alerts:
                if alert.log_file == entry.log_file:
                    should_notify = False
                    
                    if alert.alert_type == 'pattern' and alert.pattern:
                        if re.search(alert.pattern, entry.message):
                            should_notify = True
                            
                    elif alert.alert_type == 'severity' and alert.severity_threshold:
                        severity_levels = {'debug': 0, 'info': 1, 'warning': 2, 'error': 3, 'critical': 4}
                        if severity_levels.get(entry.severity, 0) >= severity_levels.get(alert.severity_threshold, 0):
                            should_notify = True
                            
                    elif alert.alert_type == 'frequency':
                        if alert.frequency_threshold:
                            count = LogEntry.objects.filter(
                                log_file=entry.log_file,
                                timestamp__gte=timezone.now() - timedelta(minutes=1)
                            ).count()
                            if count >= alert.frequency_threshold:
                                should_notify = True
                    
                    if should_notify:
                        for user in alert.notify_users.all():
                            Notification.objects.create(
                                user=user,
                                title=f"Log Alert: {alert.name}",
                                message=f"Alert triggered for log file {alert.log_file.name}\n{entry.message}",
                                severity='warning',
                                source='logs'
                            )
        else:
            # Test mode - create test notification
            alert = LogAlert.objects.get(id=entry_id)
            for user in alert.notify_users.all():
                Notification.objects.create(
                    user=user,
                    title=f"Test Alert: {alert.name}",
                    message=f"This is a test notification for alert {alert.name}",
                    severity='info',
                    source='logs'
                )
                
    except Exception as e:
        print(f"Error processing log alerts: {str(e)}")

@shared_task
def rotate_log_file(policy_id, force=False):
    """Rotate a log file based on policy"""
    try:
        policy = LogRotationPolicy.objects.get(id=policy_id)
        if not policy.is_active and not force:
            return
            
        log_file = policy.log_file
        if not os.path.exists(log_file.path):
            return
            
        should_rotate = force
        if not should_rotate:
            if policy.rotation_unit == 'size':
                current_size = os.path.getsize(log_file.path)
                should_rotate = current_size > policy.max_size
            else:
                if policy.last_rotation:
                    if policy.rotation_unit == 'daily':
                        should_rotate = policy.last_rotation < timezone.now() - timedelta(days=1)
                    elif policy.rotation_unit == 'weekly':
                        should_rotate = policy.last_rotation < timezone.now() - timedelta(weeks=1)
                    elif policy.rotation_unit == 'monthly':
                        should_rotate = policy.last_rotation < timezone.now() - timedelta(days=30)
                else:
                    should_rotate = True
                    
        if should_rotate:
            # Create backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{log_file.path}.{timestamp}"
            
            # Rotate the file
            shutil.copy2(log_file.path, backup_path)
            open(log_file.path, 'w').close()
            
            # Compress if needed
            if policy.compression != 'none':
                if policy.compression == 'gzip':
                    with open(backup_path, 'rb') as f_in:
                        with gzip.open(f"{backup_path}.gz", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(backup_path)
                    backup_path = f"{backup_path}.gz"
                elif policy.compression == 'bzip2':
                    with open(backup_path, 'rb') as f_in:
                        with bz2.open(f"{backup_path}.bz2", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(backup_path)
                    backup_path = f"{backup_path}.bz2"
                elif policy.compression == 'xz':
                    with open(backup_path, 'rb') as f_in:
                        with lzma.open(f"{backup_path}.xz", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(backup_path)
                    backup_path = f"{backup_path}.xz"
            
            # Clean up old backups
            backup_dir = os.path.dirname(log_file.path)
            base_name = os.path.basename(log_file.path)
            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith(base_name + '.')
            ])
            
            while len(backups) > policy.keep_count:
                os.remove(os.path.join(backup_dir, backups.pop(0)))
            
            # Update last rotation time
            policy.last_rotation = timezone.now()
            policy.save()
            
    except Exception as e:
        print(f"Error rotating log file: {str(e)}")

@shared_task
def cleanup_old_entries():
    """Clean up old log entries based on retention policy"""
    try:
        for log_file in LogFile.objects.all():
            threshold = timezone.now() - timedelta(days=log_file.retention_days)
            LogEntry.objects.filter(
                log_file=log_file,
                timestamp__lt=threshold
            ).delete()
    except Exception as e:
        print(f"Error cleaning up old entries: {str(e)}")

@shared_task
def analyze_log_patterns():
    """Analyze log patterns for anomaly detection"""
    try:
        now = timezone.now()
        window = now - timedelta(hours=1)
        
        # Analyze frequency patterns
        for log_file in LogFile.objects.filter(is_active=True):
            baseline = LogEntry.objects.filter(
                log_file=log_file,
                timestamp__lt=window,
                timestamp__gte=window - timedelta(hours=23)
            ).count() / 23  # Average entries per hour
            
            current = LogEntry.objects.filter(
                log_file=log_file,
                timestamp__gte=window
            ).count()
            
            # Alert if current frequency is 3x the baseline
            if current > baseline * 3 and baseline > 0:
                alert = LogAlert.objects.create(
                    name=f"High Log Frequency - {log_file.name}",
                    log_file=log_file,
                    alert_type='frequency',
                    frequency_threshold=int(baseline),
                    is_active=True
                )
                
                # Notify admin users
                from django.contrib.auth.models import User
                admin_users = User.objects.filter(is_staff=True)
                alert.notify_users.set(admin_users)
                
    except Exception as e:
        print(f"Error analyzing log patterns: {str(e)}") 