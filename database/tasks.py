import os
import subprocess
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings
import MySQLdb
from core.models import Notification
from .models import Database, DatabaseBackup

@shared_task
def update_database_sizes():
    """Update sizes for all databases."""
    try:
        conn = MySQLdb.connect(
            host='localhost',
            user=settings.DATABASES['default']['USER'],
            passwd=settings.DATABASES['default']['PASSWORD']
        )
        cursor = conn.cursor()

        for db in Database.objects.all():
            try:
                cursor.execute(f"""
                    SELECT SUM(data_length + index_length) 
                    FROM information_schema.TABLES 
                    WHERE table_schema = '{db.name}'
                    GROUP BY table_schema
                """)
                
                result = cursor.fetchone()
                old_size = db.size
                db.size = result[0] if result else 0
                db.save()

                # Create notification if database size increased significantly
                if old_size > 0 and db.size > old_size * 1.5:  # 50% increase
                    Notification.objects.create(
                        title=f"Database Size Alert: {db.name}",
                        message=f"Database size increased by "
                                f"{((db.size - old_size) / old_size * 100):.1f}%",
                        level='WARNING'
                    )

            except Exception as e:
                Notification.objects.create(
                    title=f"Database Size Check Error: {db.name}",
                    message=f"Failed to check database size: {str(e)}",
                    level='ERROR'
                )

        conn.close()
    except Exception as e:
        Notification.objects.create(
            title="Database Size Update Error",
            message=f"Failed to update database sizes: {str(e)}",
            level='ERROR'
        )

@shared_task
def create_automated_backups():
    """Create automated backups for all databases."""
    backup_dir = '/var/lib/incontrol/backups/databases'
    os.makedirs(backup_dir, exist_ok=True)

    for db in Database.objects.all():
        try:
            # Create backup record
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(backup_dir, f"{db.name}_{timestamp}.sql")
            
            backup = DatabaseBackup.objects.create(
                database=db,
                filename=filename,
                status='in_progress',
                started_at=timezone.now()
            )

            # Run mysqldump
            cmd = [
                'mysqldump',
                f"--user={settings.DATABASES['default']['USER']}",
                f"--password={settings.DATABASES['default']['PASSWORD']}",
                '--single-transaction',
                '--quick',
                '--lock-tables=false',
                db.name,
            ]

            with open(filename, 'w') as f:
                subprocess.run(cmd, stdout=f, check=True)

            # Update backup status
            backup.status = 'completed'
            backup.completed_at = timezone.now()
            backup.size = os.path.getsize(filename)
            backup.save()

            # Clean up old backups (keep last 5)
            old_backups = DatabaseBackup.objects.filter(
                database=db,
                status='completed'
            ).order_by('-created_at')[5:]
            
            for old_backup in old_backups:
                try:
                    if os.path.exists(old_backup.filename):
                        os.remove(old_backup.filename)
                    old_backup.delete()
                except Exception:
                    pass

        except Exception as e:
            Notification.objects.create(
                title=f"Database Backup Error: {db.name}",
                message=f"Failed to create backup: {str(e)}",
                level='ERROR'
            )
            if 'backup' in locals():
                backup.status = 'failed'
                backup.error_message = str(e)
                backup.save()

@shared_task
def check_database_connections():
    """Monitor database connections and notify if too many."""
    try:
        conn = MySQLdb.connect(
            host='localhost',
            user=settings.DATABASES['default']['USER'],
            passwd=settings.DATABASES['default']['PASSWORD']
        )
        cursor = conn.cursor()

        # Get max_connections setting
        cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
        max_connections = int(cursor.fetchone()[1])

        # Get current connections
        cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
        current_connections = int(cursor.fetchone()[1])

        # Calculate percentage
        connection_percentage = (current_connections / max_connections) * 100

        # Notify if using more than 80% of available connections
        if connection_percentage > 80:
            Notification.objects.create(
                title="High Database Connections",
                message=f"Database is using {connection_percentage:.1f}% "
                        f"of available connections ({current_connections}/{max_connections})",
                level='WARNING'
            )

        conn.close()
    except Exception as e:
        Notification.objects.create(
            title="Database Connection Check Error",
            message=f"Failed to check database connections: {str(e)}",
            level='ERROR'
        ) 