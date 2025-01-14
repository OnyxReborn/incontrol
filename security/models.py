from django.db import models
from django.contrib.auth.models import User

class FirewallRule(models.Model):
    ACTION_CHOICES = [
        ('ACCEPT', 'Accept'),
        ('DROP', 'Drop'),
        ('REJECT', 'Reject'),
    ]

    PROTOCOL_CHOICES = [
        ('tcp', 'TCP'),
        ('udp', 'UDP'),
        ('icmp', 'ICMP'),
        ('all', 'All'),
    ]

    name = models.CharField(max_length=255)
    source = models.CharField(max_length=255, help_text="IP, CIDR, or hostname")
    destination = models.CharField(max_length=255, help_text="IP, CIDR, or hostname")
    protocol = models.CharField(max_length=4, choices=PROTOCOL_CHOICES)
    port_range = models.CharField(max_length=255, blank=True, help_text="e.g., 80 or 1024:2048")
    action = models.CharField(max_length=6, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.action})"

    class Meta:
        ordering = ['priority']

class SecurityScan(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    TYPE_CHOICES = [
        ('port', 'Port Scan'),
        ('vulnerability', 'Vulnerability Scan'),
        ('malware', 'Malware Scan'),
        ('rootkit', 'Rootkit Detection'),
        ('integrity', 'File Integrity Check'),
    ]

    scan_type = models.CharField(max_length=13, choices=TYPE_CHOICES)
    target = models.CharField(max_length=255)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='pending')
    findings = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.scan_type} - {self.target} ({self.status})"

class SecurityIncident(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    target_ip = models.GenericIPAddressField(null=True, blank=True)
    detected_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.severity} ({self.status})"

    class Meta:
        ordering = ['-detected_at']

class SSHKey(models.Model):
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    public_key = models.TextField()
    fingerprint = models.CharField(max_length=255, unique=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.user.username})"

class FailedLogin(models.Model):
    username = models.CharField(max_length=255)
    source_ip = models.GenericIPAddressField()
    service = models.CharField(max_length=255)  # ssh, ftp, web, etc.
    attempt_time = models.DateTimeField()
    details = models.TextField(blank=True)
    blocked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} from {self.source_ip} ({self.service})"

    class Meta:
        ordering = ['-attempt_time']
