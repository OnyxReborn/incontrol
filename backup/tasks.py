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

            # Update backup record
            backup.status = 'completed'
            backup.path = backup_path
            backup.size = os.path.getsize(backup_path)
            backup.completed_at = timezone.now()
            backup.save()
            create_backup_log(backup, "Backup completed successfully")

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

        # Create temporary directory for restore
        temp_dir = tempfile.mkdtemp()

        try:
            # Extract backup archive
            create_backup_log(backup, "Extracting backup archive")
            with tarfile.open(backup.path, 'r:gz') as tar:
                tar.extractall(temp_dir)

            # Restore system files
            create_backup_log(backup, "Restoring system files")
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                if os.path.isdir(item_path):
                    # Restore directory
                    dest_path = os.path.join('/', item)
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)
                    shutil.copytree(item_path, dest_path)
                    create_backup_log(backup, f"Restored directory: {dest_path}")
                else:
                    # Restore file
                    dest_path = os.path.join('/', item)
                    shutil.copy2(item_path, dest_path)
                    create_backup_log(backup, f"Restored file: {dest_path}")

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
    """Remove old backups based on retention policy."""
    try:
        # Get all backup schedules
        schedules = BackupSchedule.objects.filter(enabled=True)
        
        for schedule in schedules:
            # Calculate cutoff date based on retention days
            cutoff_date = timezone.now() - timezone.timedelta(days=schedule.retention_days)
            
            # Get old backups for this schedule
            old_backups = Backup.objects.filter(
                created_at__lt=cutoff_date,
                type=schedule.type,
                status='completed'
            )
            
            # Delete old backups
            for backup in old_backups:
                try:
                    # Delete backup file
                    if os.path.exists(backup.path):
                        os.remove(backup.path)
                    
                    # Delete backup record
                    backup.delete()
                    
                except Exception as e:
                    print(f"Error deleting backup {backup.id}: {e}")
                    continue
        
        return True
    except Exception as e:
        print(f"Error cleaning up old backups: {e}")
        return False 