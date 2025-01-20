from django.db import models
from django.contrib.auth.models import User

class DNSZone(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_master = models.BooleanField(default=True)
    serial = models.BigIntegerField(default=1)
    refresh = models.IntegerField(default=3600)  # 1 hour
    retry = models.IntegerField(default=600)     # 10 minutes
    expire = models.IntegerField(default=86400)  # 1 day
    minimum = models.IntegerField(default=3600)  # 1 hour
    primary_ns = models.CharField(max_length=255)
    admin_email = models.EmailField()
    allow_transfer = models.TextField(blank=True, help_text="One IP per line")
    also_notify = models.TextField(blank=True, help_text="One IP per line")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class DNSRecord(models.Model):
    TYPE_CHOICES = [
        ('A', 'A'),
        ('AAAA', 'AAAA'),
        ('CNAME', 'CNAME'),
        ('MX', 'MX'),
        ('TXT', 'TXT'),
        ('SRV', 'SRV'),
        ('NS', 'NS'),
        ('PTR', 'PTR'),
        ('CAA', 'CAA'),
        ('SSHFP', 'SSHFP'),
    ]

    zone = models.ForeignKey(DNSZone, on_delete=models.CASCADE, related_name='records')
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    content = models.TextField()
    ttl = models.IntegerField(default=3600)  # 1 hour
    priority = models.IntegerField(null=True, blank=True)  # For MX and SRV records
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} {self.type} {self.content}"

    class Meta:
        unique_together = ('zone', 'name', 'type', 'content')
        ordering = ['name', 'type']

class DNSTemplate(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    records = models.JSONField(help_text="List of record templates")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class DNSQuery(models.Model):
    QUERY_TYPE_CHOICES = [
        ('ANY', 'ANY'),
        ('A', 'A'),
        ('AAAA', 'AAAA'),
        ('CNAME', 'CNAME'),
        ('MX', 'MX'),
        ('TXT', 'TXT'),
        ('SRV', 'SRV'),
        ('NS', 'NS'),
        ('PTR', 'PTR'),
        ('SOA', 'SOA'),
    ]

    domain = models.CharField(max_length=255)
    query_type = models.CharField(max_length=5, choices=QUERY_TYPE_CHOICES)
    nameserver = models.CharField(max_length=255, blank=True)
    response = models.JSONField()
    response_time = models.FloatField()  # in milliseconds
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.domain} {self.query_type}"

    class Meta:
        ordering = ['-created_at']

class DNSHealth(models.Model):
    STATUS_CHOICES = [
        ('ok', 'OK'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    zone = models.ForeignKey(DNSZone, on_delete=models.CASCADE)
    check_time = models.DateTimeField()
    status = models.CharField(max_length=7, choices=STATUS_CHOICES)
    primary_reachable = models.BooleanField()
    serial_synced = models.BooleanField()
    records_match = models.BooleanField()
    issues = models.JSONField(default=list)
    response_time = models.FloatField()  # in milliseconds
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.zone.name} - {self.status}"

    class Meta:
        ordering = ['-check_time']
        get_latest_by = 'check_time' 