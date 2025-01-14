import os
import shutil
import hashlib
import mimetypes
import tarfile
from datetime import datetime
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from core.models import Notification
from .models import Directory, File, FileOperation, FileBackup

@shared_task
def process_file_operation(operation_id):
    """Process a file operation"""
    operation = FileOperation.objects.get(pk=operation_id)
    try:
        operation.status = 'in_progress'
        operation.save()

        if operation.operation == 'create':
            os.makedirs(operation.source_path, exist_ok=True)
        elif operation.operation == 'delete':
            if os.path.isfile(operation.source_path):
                os.remove(operation.source_path)
            else:
                shutil.rmtree(operation.source_path)
        elif operation.operation in ['move', 'copy']:
            if os.path.isfile(operation.source_path):
                if operation.operation == 'move':
                    shutil.move(operation.source_path, operation.destination_path)
                else:
                    shutil.copy2(operation.source_path, operation.destination_path)
            else:
                if operation.operation == 'move':
                    shutil.move(operation.source_path, operation.destination_path)
                else:
                    shutil.copytree(operation.source_path, operation.destination_path)
        elif operation.operation == 'chmod':
            os.chmod(operation.source_path, int(operation.destination_path, 8))
        elif operation.operation == 'chown':
            uid, gid = map(int, operation.destination_path.split(':'))
            os.chown(operation.source_path, uid, gid)

        operation.status = 'completed'
        operation.completed_at = timezone.now()
        operation.save()

        # Update file/directory records
        update_filesystem_records.delay(operation.source_path)
        if operation.destination_path:
            update_filesystem_records.delay(operation.destination_path)

    except Exception as e:
        operation.status = 'failed'
        operation.error_message = str(e)
        operation.save()
        
        Notification.objects.create(
            title=f"File Operation Failed: {operation.operation}",
            message=f"Failed to {operation.operation} {operation.source_path}: {str(e)}",
            level='ERROR'
        )

@shared_task
def update_filesystem_records(path):
    """Update database records for files and directories"""
    try:
        if os.path.isfile(path):
            update_file_record(path)
        else:
            update_directory_record(path)
    except Exception as e:
        print(f"Failed to update filesystem records for {path}: {str(e)}")

def update_file_record(path):
    """Update or create file record"""
    try:
        name = os.path.basename(path)
        directory_path = os.path.dirname(path)
        
        stat = os.stat(path)
        mime_type, _ = mimetypes.guess_type(path)
        
        directory, _ = Directory.objects.get_or_create(
            path=directory_path,
            defaults={'name': os.path.basename(directory_path)}
        )

        file, created = File.objects.get_or_create(
            path=directory_path,
            name=name,
            defaults={
                'directory': directory,
                'size': stat.st_size,
                'mime_type': mime_type or 'application/octet-stream',
                'is_symlink': os.path.islink(path),
                'symlink_target': os.readlink(path) if os.path.islink(path) else ''
            }
        )

        if not created:
            file.size = stat.st_size
            file.mime_type = mime_type or 'application/octet-stream'
            file.is_symlink = os.path.islink(path)
            file.symlink_target = os.readlink(path) if os.path.islink(path) else ''
            file.save()

    except Exception as e:
        print(f"Failed to update file record for {path}: {str(e)}")

def update_directory_record(path):
    """Update or create directory record"""
    try:
        name = os.path.basename(path)
        total_size = 0
        files_count = 0
        dirs_count = 0

        for root, dirs, files in os.walk(path):
            dirs_count += len(dirs)
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    total_size += os.path.getsize(file_path)
                    files_count += 1
                except OSError:
                    continue

        directory, _ = Directory.objects.update_or_create(
            path=path,
            defaults={
                'name': name,
                'size': total_size,
                'files_count': files_count,
                'dirs_count': dirs_count,
                'last_scanned': timezone.now()
            }
        )

    except Exception as e:
        print(f"Failed to update directory record for {path}: {str(e)}")

@shared_task
def create_directory_backup(backup_id):
    """Create a backup of a directory"""
    backup = FileBackup.objects.get(pk=backup_id)
    try:
        backup.status = 'in_progress'
        backup.started_at = timezone.now()
        backup.save()

        # Create backup directory if it doesn't exist
        os.makedirs(os.path.dirname(backup.backup_path), exist_ok=True)

        # Create tar archive
        with tarfile.open(backup.backup_path, 'w:gz') as tar:
            tar.add(backup.directory.path, arcname=os.path.basename(backup.directory.path))

        # Update backup record
        backup.size = os.path.getsize(backup.backup_path)
        backup.files_count = backup.directory.files_count
        backup.status = 'completed'
        backup.completed_at = timezone.now()
        backup.save()

    except Exception as e:
        backup.status = 'failed'
        backup.error_message = str(e)
        backup.save()

        Notification.objects.create(
            title=f"Backup Failed: {backup.directory.path}",
            message=f"Failed to create backup: {str(e)}",
            level='ERROR'
        )

@shared_task
def cleanup_old_backups():
    """Clean up old backups"""
    threshold = timezone.now() - timezone.timedelta(days=30)
    old_backups = FileBackup.objects.filter(
        created_at__lt=threshold,
        status='completed'
    )

    for backup in old_backups:
        try:
            if os.path.exists(backup.backup_path):
                os.remove(backup.backup_path)
            backup.delete()
        except Exception as e:
            print(f"Failed to clean up backup {backup.backup_path}: {str(e)}")

@shared_task
def scan_filesystem():
    """Scan filesystem for changes"""
    for directory in Directory.objects.filter(is_active=True):
        try:
            update_filesystem_records.delay(directory.path)
        except Exception as e:
            print(f"Failed to scan directory {directory.path}: {str(e)}")

@shared_task
def monitor_storage_usage():
    """Monitor storage usage and send notifications"""
    try:
        stat = os.statvfs('/')
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bfree * stat.f_frsize
        used = total - free
        usage_percent = (used / total) * 100

        if usage_percent > 90:
            Notification.objects.create(
                title="High Storage Usage",
                message=f"Storage usage is at {usage_percent:.1f}%",
                level='WARNING'
            )
        elif usage_percent > 95:
            Notification.objects.create(
                title="Critical Storage Usage",
                message=f"Storage usage is at {usage_percent:.1f}%",
                level='CRITICAL'
            )
    except Exception as e:
        print(f"Failed to monitor storage usage: {str(e)}") 