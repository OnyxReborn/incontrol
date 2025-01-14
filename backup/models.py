from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

class BackupLocation(models.Model):
    LOCATION_TYPES = [
        ('local', 'Local Storage'),
        ('s3', 'Amazon S3'),
        ('ftp', 'FTP Server'),
        ('sftp', 'SFTP Server'),
    ]

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=LOCATION_TYPES)
    path = models.CharField(max_length=255, help_text="Local path or remote URL")
    credentials = models.JSONField(null=True, blank=True, help_text="Encrypted credentials for remote storage")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_verified = models.DateTimeField(null=True, blank=True)
    max_storage = models.BigIntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Maximum storage size in bytes"
    )

    def __str__(self):
        return f"{self.name} ({self.type})"

    class Meta:
        ordering = ['name']

class Backup(models.Model):
    BACKUP_TYPES = [
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    size = models.BigIntegerField(default=0)
    path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    location = models.ForeignKey(
        BackupLocation,
        on_delete=models.SET_NULL,
        null=True,
        related_name='backups'
    )

    def __str__(self):
        return f"{self.name} ({self.type}) - {self.status}"

    class Meta:
        ordering = ['-created_at']

class BackupSchedule(models.Model):
    BACKUP_TYPES = [
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
    ]

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=BACKUP_TYPES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    retention_days = models.IntegerField(default=7)
    next_run = models.DateTimeField()
    last_run = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.frequency})"

    def save(self, *args, **kwargs):
        if not self.next_run:
            self.next_run = self.calculate_next_run()
        super().save(*args, **kwargs)

    def calculate_next_run(self):
        now = timezone.now()
        if self.frequency == 'daily':
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timezone.timedelta(days=1)
        elif self.frequency == 'weekly':
            days_ahead = 7 - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timezone.timedelta(days=days_ahead)
        else:  # monthly
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)
            return next_month.replace(hour=0, minute=0, second=0, microsecond=0)

    class Meta:
        ordering = ['next_run']

class BackupLog(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    message = models.TextField()
    level = models.CharField(max_length=20, default='info')

    def __str__(self):
        return f"{self.backup.name} - {self.timestamp}"

    class Meta:
        ordering = ['-timestamp'] 