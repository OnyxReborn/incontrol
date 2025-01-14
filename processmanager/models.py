from django.db import models
from django.contrib.auth.models import User

class Process(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('sleeping', 'Sleeping'),
        ('stopped', 'Stopped'),
        ('zombie', 'Zombie'),
        ('dead', 'Dead'),
    ]

    pid = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES)
    user = models.CharField(max_length=255)
    cpu_percent = models.FloatField()
    memory_percent = models.FloatField()
    command = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.pid} - {self.name}"

    class Meta:
        ordering = ['-cpu_percent']

class Service(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('failed', 'Failed'),
        ('masked', 'Masked'),
    ]

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES)
    is_enabled = models.BooleanField(default=False)
    load_state = models.CharField(max_length=255)
    active_state = models.CharField(max_length=255)
    sub_state = models.CharField(max_length=255)
    unit_file_state = models.CharField(max_length=255)
    followed_by = models.CharField(max_length=255, blank=True)
    restart_count = models.IntegerField(default=0)
    last_restart = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status})"

class ResourceUsage(models.Model):
    timestamp = models.DateTimeField()
    cpu_percent = models.FloatField()
    memory_percent = models.FloatField()
    swap_percent = models.FloatField()
    disk_io_read = models.BigIntegerField()  # bytes
    disk_io_write = models.BigIntegerField()  # bytes
    network_io_receive = models.BigIntegerField()  # bytes
    network_io_send = models.BigIntegerField()  # bytes
    load_1m = models.FloatField()
    load_5m = models.FloatField()
    load_15m = models.FloatField()
    process_count = models.IntegerField()
    thread_count = models.IntegerField()

    def __str__(self):
        return f"Resource Usage at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        get_latest_by = 'timestamp'

class ProcessLimit(models.Model):
    RESOURCE_CHOICES = [
        ('cpu', 'CPU Usage'),
        ('memory', 'Memory Usage'),
        ('io', 'I/O Usage'),
        ('files', 'Open Files'),
    ]

    name = models.CharField(max_length=255)
    resource = models.CharField(max_length=6, choices=RESOURCE_CHOICES)
    limit_value = models.FloatField()
    is_active = models.BooleanField(default=True)
    action = models.CharField(max_length=255, default='notify')  # notify, kill, restart
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.resource} ({self.limit_value})"

class ProcessAlert(models.Model):
    SEVERITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]

    process = models.ForeignKey(Process, on_delete=models.CASCADE, null=True)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, null=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES)
    resource_type = models.CharField(max_length=255)  # cpu, memory, disk, etc.
    value = models.FloatField()
    threshold = models.FloatField()
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.severity}"

    class Meta:
        ordering = ['-created_at'] 