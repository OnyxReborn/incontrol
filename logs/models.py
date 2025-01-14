from django.db import models
from django.contrib.auth.models import User

class LogFile(models.Model):
    LOG_TYPES = [
        ('system', 'System Log'),
        ('application', 'Application Log'),
        ('security', 'Security Log'),
        ('apache', 'Apache Log'),
        ('nginx', 'Nginx Log'),
        ('mysql', 'MySQL Log'),
        ('postgresql', 'PostgreSQL Log'),
        ('mail', 'Mail Log'),
        ('custom', 'Custom Log'),
    ]

    name = models.CharField(max_length=255)
    path = models.CharField(max_length=512)
    log_type = models.CharField(max_length=20, choices=LOG_TYPES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    max_size = models.BigIntegerField(help_text="Maximum size in bytes")
    retention_days = models.IntegerField(default=30)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.log_type})"

class LogEntry(models.Model):
    SEVERITY_LEVELS = [
        ('debug', 'Debug'),
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    log_file = models.ForeignKey(LogFile, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS)
    source = models.CharField(max_length=255)
    message = models.TextField()
    raw_data = models.TextField()
    process_id = models.IntegerField(null=True, blank=True)
    thread_id = models.CharField(max_length=50, blank=True)
    user = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.timestamp} - {self.severity}: {self.message[:50]}"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['severity']),
            models.Index(fields=['source']),
        ]

class LogAlert(models.Model):
    ALERT_TYPES = [
        ('pattern', 'Pattern Match'),
        ('frequency', 'Event Frequency'),
        ('severity', 'Severity Level'),
        ('custom', 'Custom Rule'),
    ]

    name = models.CharField(max_length=255)
    log_file = models.ForeignKey(LogFile, on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    pattern = models.CharField(max_length=512, blank=True)
    severity_threshold = models.CharField(max_length=10, choices=LogEntry.SEVERITY_LEVELS, null=True, blank=True)
    frequency_threshold = models.IntegerField(null=True, blank=True, help_text="Events per minute")
    is_active = models.BooleanField(default=True)
    notify_users = models.ManyToManyField(User)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.alert_type})"

class LogRotationPolicy(models.Model):
    ROTATION_UNITS = [
        ('size', 'Size Based'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    COMPRESSION_TYPES = [
        ('none', 'No Compression'),
        ('gzip', 'GZip'),
        ('bzip2', 'BZip2'),
        ('xz', 'XZ'),
    ]

    log_file = models.OneToOneField(LogFile, on_delete=models.CASCADE)
    rotation_unit = models.CharField(max_length=10, choices=ROTATION_UNITS)
    max_size = models.BigIntegerField(null=True, blank=True, help_text="Size in bytes")
    keep_count = models.IntegerField(default=5)
    compression = models.CharField(max_length=10, choices=COMPRESSION_TYPES, default='gzip')
    is_active = models.BooleanField(default=True)
    last_rotation = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Rotation Policy for {self.log_file.name}"
