from django.db import models

class MetricSnapshot(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    cpu_percent = models.FloatField()
    memory_percent = models.FloatField()
    disk_percent = models.FloatField()
    network_rx_bytes = models.BigIntegerField()
    network_tx_bytes = models.BigIntegerField()
    load_1 = models.FloatField()
    load_5 = models.FloatField()
    load_15 = models.FloatField()

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
        ]

class ServiceStatus(models.Model):
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20)
    uptime = models.DurationField()
    cpu_percent = models.FloatField()
    memory_percent = models.FloatField()
    last_check = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

class AlertRule(models.Model):
    METRIC_CHOICES = [
        ('cpu', 'CPU Usage'),
        ('memory', 'Memory Usage'),
        ('disk', 'Disk Usage'),
        ('load', 'Load Average'),
    ]
    SEVERITY_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    name = models.CharField(max_length=100)
    metric = models.CharField(max_length=20, choices=METRIC_CHOICES)
    threshold = models.FloatField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

class Alert(models.Model):
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
        ] 