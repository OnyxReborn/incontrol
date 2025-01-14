import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from .models import Backup, BackupSchedule, BackupLog

BACKUP_DIR = getattr(settings, 'BACKUP_DIR', os.path.join(settings.BASE_DIR, 'backups'))
os.makedirs(BACKUP_DIR, exist_ok=True)

def create_backup_log(backup, message, level='info'):
    BackupLog.objects.create(
        backup=backup,
        message=message,
        level=level
    )

@shared_task
def create_backup(backup_id):
    backup = Backup.objects.get(id=backup_id)
    try:
        backup.status = 'in_progress'
        backup.save()
        create_backup_log(backup, "Starting backup process")

        # Create temporary directory for backup
        temp_dir = tempfile.mkdtemp()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{backup.name}_{timestamp}.tar.gz"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)

        try:
            # Backup system files
            system_dirs = [
                '/etc',
                '/var/www',
                '/var/log',
                # Add more directories as needed
            ]

            create_backup_log(backup, "Creating archive of system files")
            with tarfile.open(backup_path, 'w:gz') as tar:
                for dir_path in system_dirs:
                    if os.path.exists(dir_path):
                        tar.add(dir_path, arcname=os.path.basename(dir_path))
                        create_backup_log(backup, f"Added {dir_path} to backup")

            # Get backup size
            backup.size = os.path.getsize(backup_path)
            backup.path = backup_path
            backup.status = 'completed'
            backup.completed_at = timezone.now()
            backup.save()

            create_backup_log(backup, f"Backup completed successfully. Size: {backup.size} bytes")

        except Exception as e:
            create_backup_log(backup, f"Error during backup: {str(e)}", 'error')
            raise

        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        backup.status = 'failed'
        backup.error_message = str(e)
        backup.save()
        create_backup_log(backup, f"Backup failed: {str(e)}", 'error')
        raise

@shared_task
def restore_backup(backup_id):
    backup = Backup.objects.get(id=backup_id)
    try:
        create_backup_log(backup, "Starting restore process")

        if not os.path.exists(backup.path):
            raise FileNotFoundError("Backup file not found")

        # Create temporary directory for restoration
        temp_dir = tempfile.mkdtemp()

        try:
            # Extract backup
            create_backup_log(backup, "Extracting backup archive")
            with tarfile.open(backup.path, 'r:gz') as tar:
                tar.extractall(temp_dir)

            # Restore files
            create_backup_log(backup, "Restoring system files")
            for item in os.listdir(temp_dir):
                src_path = os.path.join(temp_dir, item)
                if item == 'etc':
                    dst_path = '/etc'
                elif item == 'www':
                    dst_path = '/var/www'
                elif item == 'log':
                    dst_path = '/var/log'
                else:
                    continue

                if os.path.exists(dst_path):
                    shutil.rmtree(dst_path)
                shutil.copytree(src_path, dst_path)
                create_backup_log(backup, f"Restored {dst_path}")

            create_backup_log(backup, "Restore completed successfully")

        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        create_backup_log(backup, f"Restore failed: {str(e)}", 'error')
        raise

@shared_task
def process_backup_schedules():
    now = timezone.now()
    schedules = BackupSchedule.objects.filter(enabled=True, next_run__lte=now)

    for schedule in schedules:
        try:
            # Create backup
            backup = Backup.objects.create(
                name=f"{schedule.name} (Scheduled)",
                type=schedule.type,
                status='pending'
            )
            create_backup.delay(backup.id)

            # Update schedule
            schedule.last_run = now
            schedule.next_run = schedule.calculate_next_run()
            schedule.save()

        except Exception as e:
            print(f"Error processing schedule {schedule.name}: {str(e)}")

@shared_task
def cleanup_old_backups():
    schedules = BackupSchedule.objects.all()
    for schedule in schedules:
        retention_date = timezone.now() - timezone.timedelta(days=schedule.retention_days)
        old_backups = Backup.objects.filter(
            created_at__lt=retention_date,
            status='completed',
            type=schedule.type
        )

        for backup in old_backups:
            try:
                if os.path.exists(backup.path):
                    os.remove(backup.path)
                backup.delete()
            except Exception as e:
                print(f"Error cleaning up backup {backup.id}: {str(e)}") 