from django.db import models

class Service(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
        ('unknown', 'Unknown'),
    ]

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unknown')
    is_monitored = models.BooleanField(default=True)
    last_check = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.status}"

class Package(models.Model):
    name = models.CharField(max_length=255, unique=True)
    version = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_installed = models.BooleanField(default=False)
    installation_date = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.version}"

class Backup(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    TYPE_CHOICES = [
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
        ('differential', 'Differential Backup'),
    ]

    name = models.CharField(max_length=255)
    backup_type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='pending')
    source_path = models.CharField(max_length=255)
    destination_path = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.backup_type} - {self.status}"

class CronJob(models.Model):
    name = models.CharField(max_length=255)
    command = models.TextField()
    schedule = models.CharField(max_length=100)  # Cron expression
    is_active = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.schedule}"
