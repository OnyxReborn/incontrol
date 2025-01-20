from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class VirtualHost(models.Model):
    SERVER_TYPE_CHOICES = [
        ('apache', 'Apache'),
        ('nginx', 'Nginx'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
    ]

    name = models.CharField(max_length=255)
    server_type = models.CharField(max_length=6, choices=SERVER_TYPE_CHOICES)
    domains = models.TextField(help_text="One domain per line")
    root_directory = models.CharField(max_length=255)
    configuration = models.TextField()
    ssl_enabled = models.BooleanField(default=False)
    ssl_certificate = models.CharField(max_length=255, blank=True)
    ssl_key = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='inactive')
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.server_type})"

    class Meta:
        unique_together = ('name', 'server_type')

class SSLCertificate(models.Model):
    name = models.CharField(max_length=255)
    domains = models.TextField(help_text="One domain per line")
    key_file = models.CharField(max_length=255)
    cert_file = models.CharField(max_length=255)
    chain_file = models.CharField(max_length=255, blank=True)
    issuer = models.CharField(max_length=255)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def is_expired(self):
        return self.valid_until < timezone.now()

    @property
    def days_until_expiry(self):
        delta = self.valid_until - timezone.now()
        return delta.days

class ProxyConfig(models.Model):
    PROXY_TYPE_CHOICES = [
        ('reverse', 'Reverse Proxy'),
        ('forward', 'Forward Proxy'),
    ]

    name = models.CharField(max_length=255)
    proxy_type = models.CharField(max_length=7, choices=PROXY_TYPE_CHOICES)
    source_url = models.CharField(max_length=255)
    target_url = models.CharField(max_length=255)
    virtual_host = models.ForeignKey(VirtualHost, on_delete=models.CASCADE, related_name='proxy_configs')
    preserve_host_header = models.BooleanField(default=True)
    websocket_support = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.source_url} -> {self.target_url}"

class AccessControl(models.Model):
    TYPE_CHOICES = [
        ('allow', 'Allow'),
        ('deny', 'Deny'),
    ]

    virtual_host = models.ForeignKey(VirtualHost, on_delete=models.CASCADE, related_name='access_controls')
    rule_type = models.CharField(max_length=5, choices=TYPE_CHOICES)
    source = models.CharField(max_length=255, help_text="IP, CIDR, or hostname")
    url_pattern = models.CharField(max_length=255, default='/')
    description = models.TextField(blank=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.rule_type} {self.source} -> {self.virtual_host.name}"

    class Meta:
        ordering = ['priority']

class EmailAccount(models.Model):
    username = models.CharField(max_length=64)
    domain = models.CharField(max_length=255)
    password = models.CharField(max_length=255)  # Will be hashed
    quota = models.IntegerField(default=1000)  # MB
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('username', 'domain')

    def __str__(self):
        return f"{self.username}@{self.domain}"

class EmailForwarder(models.Model):
    source = models.EmailField()
    destination = models.EmailField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source} → {self.destination}"

class SpamFilter(models.Model):
    TYPE_CHOICES = (
        ('blacklist', 'Blacklist'),
        ('whitelist', 'Whitelist'),
    )
    
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    value = models.CharField(max_length=255)  # Email or domain
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.type}: {self.value}"

class Database(models.Model):
    name = models.CharField(max_length=64, unique=True)
    collation = models.CharField(max_length=32, default='utf8mb4_general_ci')
    size = models.BigIntegerField(default=0)  # Size in bytes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class DatabaseUser(models.Model):
    username = models.CharField(max_length=32)
    host = models.CharField(max_length=255, default='localhost')
    password = models.CharField(max_length=255)  # Will be hashed
    databases = models.ManyToManyField(Database, related_name='users')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('username', 'host')

    def __str__(self):
        return f"{self.username}@{self.host}"

class DatabaseBackup(models.Model):
    database = models.ForeignKey(Database, on_delete=models.CASCADE, related_name='backups')
    file_path = models.CharField(max_length=255)
    size = models.BigIntegerField()  # Size in bytes
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.database.name} - {self.created_at}"

class IPBlock(models.Model):
    TYPE_CHOICES = [
        ('allow', 'Allow'),
        ('deny', 'Deny'),
    ]

    ip_address = models.CharField(max_length=50, help_text="IP address or CIDR range")
    rule_type = models.CharField(max_length=5, choices=TYPE_CHOICES, default='deny')
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.rule_type}: {self.ip_address}"

class ModSecurityRule(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('warning', 'Warning'),
        ('notice', 'Notice'),
    ]

    rule_id = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    rule_content = models.TextField(help_text="ModSecurity rule content")
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.rule_id}: {self.description}"

class ProtectedDirectory(models.Model):
    path = models.CharField(max_length=255)
    username = models.CharField(max_length=50)
    password = models.CharField(max_length=255)  # Will be hashed
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Protected Directories"
        unique_together = ('path', 'username')

    def __str__(self):
        return f"{self.path} ({self.username})"

class Subdomain(models.Model):
    name = models.CharField(max_length=255)
    domain = models.ForeignKey(VirtualHost, on_delete=models.CASCADE, related_name='subdomains')
    document_root = models.CharField(max_length=255)
    is_wildcard = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name}.{self.domain.name}"

class DomainRedirect(models.Model):
    REDIRECT_TYPE_CHOICES = [
        ('301', 'Permanent (301)'),
        ('302', 'Temporary (302)'),
    ]

    source_domain = models.CharField(max_length=255)
    target_domain = models.CharField(max_length=255)
    redirect_type = models.CharField(max_length=3, choices=REDIRECT_TYPE_CHOICES, default='301')
    preserve_path = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source_domain} → {self.target_domain}"

class DNSZone(models.Model):
    RECORD_TYPE_CHOICES = [
        ('A', 'A Record'),
        ('AAAA', 'AAAA Record'),
        ('CNAME', 'CNAME Record'),
        ('MX', 'MX Record'),
        ('TXT', 'TXT Record'),
        ('SRV', 'SRV Record'),
        ('NS', 'NS Record'),
        ('PTR', 'PTR Record'),
        ('CAA', 'CAA Record'),
    ]

    domain = models.ForeignKey(VirtualHost, on_delete=models.CASCADE, related_name='dns_records')
    name = models.CharField(max_length=255)
    record_type = models.CharField(max_length=5, choices=RECORD_TYPE_CHOICES)
    content = models.CharField(max_length=255)
    ttl = models.IntegerField(default=3600)
    priority = models.IntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} {self.record_type} {self.content}"

class BackupConfig(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    backup_type = models.CharField(max_length=50, choices=[
        ('full', 'Full Backup'),
        ('incremental', 'Incremental Backup'),
        ('differential', 'Differential Backup')
    ])
    schedule = models.CharField(max_length=100, blank=True)  # Cron expression
    retention_days = models.IntegerField(default=30)
    backup_path = models.CharField(max_length=255, default='/var/lib/incontrol/backups')
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.backup_type})"

class BackupJob(models.Model):
    config = models.ForeignKey(BackupConfig, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=[
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ])
    backup_size = models.BigIntegerField(null=True, blank=True)
    file_path = models.CharField(max_length=255)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"Backup {self.id} - {self.config.name} ({self.status})"

class ResourceUsage(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    cpu_usage = models.FloatField()  # Percentage
    memory_usage = models.FloatField()  # Percentage
    disk_usage = models.FloatField()  # Percentage
    disk_read = models.BigIntegerField()  # Bytes/s
    disk_write = models.BigIntegerField()  # Bytes/s
    network_rx = models.BigIntegerField()  # Bytes/s
    network_tx = models.BigIntegerField()  # Bytes/s
    load_average = models.CharField(max_length=50)  # 1, 5, 15 min averages

    class Meta:
        ordering = ['-timestamp']

class BandwidthUsage(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    domain = models.ForeignKey(VirtualHost, on_delete=models.CASCADE, related_name='bandwidth_usage')
    bytes_in = models.BigIntegerField()
    bytes_out = models.BigIntegerField()
    requests = models.IntegerField()

    class Meta:
        ordering = ['-timestamp']

class ErrorLog(models.Model):
    LEVEL_CHOICES = [
        ('emergency', 'Emergency'),
        ('alert', 'Alert'),
        ('critical', 'Critical'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('notice', 'Notice'),
        ('info', 'Info'),
        ('debug', 'Debug')
    ]

    timestamp = models.DateTimeField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    source = models.CharField(max_length=100)  # nginx, php, mysql, etc.
    message = models.TextField()
    file_path = models.CharField(max_length=255)
    line_number = models.IntegerField(null=True, blank=True)
    stack_trace = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']

class AccessLog(models.Model):
    timestamp = models.DateTimeField()
    domain = models.ForeignKey(VirtualHost, on_delete=models.CASCADE, related_name='access_logs')
    ip_address = models.GenericIPAddressField()
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=2048)
    status_code = models.IntegerField()
    user_agent = models.TextField()
    referer = models.TextField(blank=True)
    response_time = models.FloatField()  # milliseconds
    response_size = models.IntegerField()  # bytes

    class Meta:
        ordering = ['-timestamp']

class CrontabSchedule(models.Model):
    minute = models.CharField(max_length=64, default='*')
    hour = models.CharField(max_length=64, default='*')
    day_of_week = models.CharField(max_length=64, default='*')
    day_of_month = models.CharField(max_length=64, default='*')
    month_of_year = models.CharField(max_length=64, default='*')
    timezone = models.CharField(max_length=64, default='UTC')

    class Meta:
        app_label = 'webserver'

    def __str__(self):
        return f'{self.minute} {self.hour} {self.day_of_month} {self.month_of_year} {self.day_of_week} (timezone: {self.timezone})'

class PeriodicTask(models.Model):
    name = models.CharField(max_length=200, unique=True)
    task = models.CharField(max_length=200)
    crontab = models.ForeignKey(
        CrontabSchedule,
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name='crontab schedule'
    )
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    total_run_count = models.PositiveIntegerField(default=0)
    date_changed = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True)

    class Meta:
        app_label = 'webserver'

    def __str__(self):
        return self.name
