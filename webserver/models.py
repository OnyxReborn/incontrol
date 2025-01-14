from django.db import models
from django.contrib.auth.models import User

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
    TYPE_CHOICES = [
        ('lets_encrypt', 'Let\'s Encrypt'),
        ('self_signed', 'Self-Signed'),
        ('custom', 'Custom'),
    ]

    name = models.CharField(max_length=255)
    domains = models.TextField(help_text="One domain per line")
    certificate_type = models.CharField(max_length=11, choices=TYPE_CHOICES)
    certificate_file = models.CharField(max_length=255)
    private_key_file = models.CharField(max_length=255)
    chain_file = models.CharField(max_length=255, blank=True)
    issued_date = models.DateTimeField()
    expiry_date = models.DateTimeField()
    auto_renew = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.certificate_type})"

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
