import os
import subprocess
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.db.models import F
from core.models import Notification
from .models import MailAccount, MailQueue, MailLog

@shared_task
def update_mailbox_quotas():
    """Update used quota for all mail accounts."""
    for account in MailAccount.objects.filter(status='active'):
        try:
            username = account.email.split('@')[0]
            maildir = f"/var/mail/{account.domain.name}/{username}"
            
            # Get mailbox size using du command
            result = subprocess.run(['du', '-sb', maildir],
                                 capture_output=True, text=True)
            if result.returncode == 0:
                size = int(result.stdout.split()[0])
                old_size = account.used_quota
                account.used_quota = size
                account.save()

                # Notify if quota is nearly full
                if size > account.quota * 0.9:  # 90% full
                    Notification.objects.create(
                        title=f"Mailbox Almost Full: {account.email}",
                        message=f"Mailbox is using {(size/account.quota)*100:.1f}% "
                                f"of quota ({size/(1024*1024*1024):.2f} GB used)",
                        level='WARNING'
                    )

        except Exception as e:
            Notification.objects.create(
                title=f"Quota Update Error: {account.email}",
                message=f"Failed to update mailbox quota: {str(e)}",
                level='ERROR'
            )

@shared_task
def process_mail_queue():
    """Process and monitor mail queue."""
    try:
        # Get queue information from postqueue
        result = subprocess.run(['postqueue', '-p'],
                             capture_output=True, text=True)
        
        if result.returncode == 0:
            # Parse queue output and update database
            queue_items = parse_postqueue_output(result.stdout)
            
            for item in queue_items:
                queue_entry, created = MailQueue.objects.update_or_create(
                    message_id=item['id'],
                    defaults={
                        'from_address': item['from'],
                        'to_address': item['to'],
                        'subject': item['subject'],
                        'size': item['size'],
                        'status': item['status'],
                        'error_message': item.get('error', ''),
                    }
                )

                # Notify about long-queued messages
                if not created and queue_entry.status == 'deferred':
                    time_in_queue = timezone.now() - queue_entry.created_at
                    if time_in_queue > timedelta(hours=24):
                        Notification.objects.create(
                            title="Message Stuck in Queue",
                            message=f"Message {queue_entry.message_id} to "
                                    f"{queue_entry.to_address} has been in the "
                                    f"queue for {time_in_queue.days} days",
                            level='WARNING'
                        )

    except Exception as e:
        Notification.objects.create(
            title="Mail Queue Processing Error",
            message=f"Failed to process mail queue: {str(e)}",
            level='ERROR'
        )

@shared_task
def clean_mail_logs():
    """Clean up old mail logs."""
    try:
        # Delete logs older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        MailLog.objects.filter(timestamp__lt=cutoff_date).delete()
    except Exception as e:
        Notification.objects.create(
            title="Mail Log Cleanup Error",
            message=f"Failed to clean up mail logs: {str(e)}",
            level='ERROR'
        )

@shared_task
def monitor_mail_services():
    """Monitor mail-related services."""
    services = ['postfix', 'dovecot', 'spamassassin', 'opendkim']
    
    for service in services:
        try:
            result = subprocess.run(['systemctl', 'is-active', service],
                                 capture_output=True, text=True)
            
            if result.returncode != 0:
                Notification.objects.create(
                    title=f"Mail Service Down: {service}",
                    message=f"The {service} service is not running",
                    level='CRITICAL'
                )
                
                # Try to restart the service
                subprocess.run(['systemctl', 'restart', service])
                
        except Exception as e:
            Notification.objects.create(
                title=f"Service Check Error: {service}",
                message=f"Failed to check {service} status: {str(e)}",
                level='ERROR'
            )

def parse_postqueue_output(output):
    """Parse postqueue -p output and return structured data."""
    items = []
    current_item = None
    
    for line in output.split('\n'):
        if line.startswith('-'):
            if current_item:
                items.append(current_item)
            current_item = {}
        elif current_item is not None:
            if line.startswith('queue_id|'):
                current_item['id'] = line.split('|')[1]
            elif line.startswith('from|'):
                current_item['from'] = line.split('|')[1]
            elif line.startswith('to|'):
                current_item['to'] = line.split('|')[1]
            elif line.startswith('subject|'):
                current_item['subject'] = line.split('|')[1]
            elif line.startswith('size|'):
                current_item['size'] = int(line.split('|')[1])
            elif line.startswith('status|'):
                current_item['status'] = line.split('|')[1]
            elif line.startswith('error|'):
                current_item['error'] = line.split('|')[1]
    
    if current_item:
        items.append(current_item)
    
    return items 