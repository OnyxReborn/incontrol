from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class MetricSnapshot(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    cpu_usage = models.FloatField()
    memory_usage = models.FloatField()
    disk_usage = models.FloatField()
    network_in = models.BigIntegerField()
    network_out = models.BigIntegerField()
    load_average_1m = models.FloatField()
    load_average_5m = models.FloatField()
    load_average_15m = models.FloatField()

    class Meta:
        ordering = ['-timestamp']

class ServiceStatus(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=[
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    ])
    uptime = models.IntegerField(default=0)
    memory_usage = models.FloatField(default=0)
    cpu_usage = models.FloatField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.status})"

class Alert(models.Model):
    type = models.CharField(max_length=100)
    severity = models.CharField(max_length=50, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ])
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=[
        ('active', 'Active'),
        ('resolved', 'Resolved'),
    ], default='active')
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.type} - {self.severity} ({self.status})"

class AlertRule(models.Model):
    name = models.CharField(max_length=255)
    metric = models.CharField(max_length=100, choices=[
        ('cpu_usage', 'CPU Usage'),
        ('memory_usage', 'Memory Usage'),
        ('disk_usage', 'Disk Usage'),
        ('network_in', 'Network In'),
        ('network_out', 'Network Out'),
        ('service_status', 'Service Status'),
    ])
    condition = models.CharField(max_length=50, choices=[
        ('gt', 'Greater Than'),
        ('lt', 'Less Than'),
        ('eq', 'Equals'),
        ('ne', 'Not Equals'),
    ])
    threshold = models.FloatField()
    duration = models.IntegerField(help_text='Duration in minutes', default=5)
    severity = models.CharField(max_length=50, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ])
    is_active = models.BooleanField(default=True)
    notification_channels = models.JSONField(default=list)
    cooldown_period = models.IntegerField(
        help_text='Cooldown period in minutes',
        default=60
    )
    last_triggered = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.metric})"

class NetworkInterface(models.Model):
    name = models.CharField(max_length=100)
    ip_address = models.CharField(max_length=100)
    mac_address = models.CharField(max_length=100)
    is_up = models.BooleanField(default=True)
    bytes_sent = models.BigIntegerField(default=0)
    bytes_received = models.BigIntegerField(default=0)
    packets_sent = models.BigIntegerField(default=0)
    packets_received = models.BigIntegerField(default=0)
    errors_in = models.IntegerField(default=0)
    errors_out = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.ip_address})"

class DiskPartition(models.Model):
    device = models.CharField(max_length=100)
    mountpoint = models.CharField(max_length=255)
    filesystem_type = models.CharField(max_length=100)
    total_size = models.BigIntegerField()
    used_size = models.BigIntegerField()
    free_size = models.BigIntegerField()
    usage_percent = models.FloatField()
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.device} ({self.mountpoint})"

class Process(models.Model):
    pid = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=100)
    cpu_percent = models.FloatField()
    memory_percent = models.FloatField()
    status = models.CharField(max_length=50)
    created_time = models.DateTimeField()
    command = models.TextField()
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (PID: {self.pid})"

class ServiceLog(models.Model):
    service = models.ForeignKey(ServiceStatus, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=50, choices=[
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ])
    message = models.TextField()

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.service.name} - {self.level} - {self.timestamp}" 