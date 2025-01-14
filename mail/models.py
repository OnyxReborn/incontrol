from django.db import models
from django.contrib.auth.models import User

class MailDomain(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    dkim_enabled = models.BooleanField(default=True)
    dkim_private_key = models.TextField(blank=True)
    dkim_public_key = models.TextField(blank=True)
    spf_record = models.CharField(max_length=255, blank=True)
    dmarc_record = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class MailAccount(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('disabled', 'Disabled'),
    ]

    email = models.EmailField(unique=True)
    domain = models.ForeignKey(MailDomain, on_delete=models.CASCADE, related_name='accounts')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    password_hash = models.CharField(max_length=255)
    quota = models.BigIntegerField(default=1073741824)  # 1GB in bytes
    used_quota = models.BigIntegerField(default=0)
    status = models.CharField(max_length=9, choices=STATUS_CHOICES, default='active')
    forward_to = models.TextField(blank=True, help_text="One email per line")
    auto_reply_enabled = models.BooleanField(default=False)
    auto_reply_subject = models.CharField(max_length=255, blank=True)
    auto_reply_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email

class MailAlias(models.Model):
    email = models.EmailField(unique=True)
    domain = models.ForeignKey(MailDomain, on_delete=models.CASCADE, related_name='aliases')
    destinations = models.TextField(help_text="One email per line")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email

class SpamFilter(models.Model):
    FILTER_TYPE_CHOICES = [
        ('domain', 'Domain'),
        ('email', 'Email Address'),
        ('ip', 'IP Address'),
        ('header', 'Header'),
        ('content', 'Content'),
    ]

    ACTION_CHOICES = [
        ('reject', 'Reject'),
        ('quarantine', 'Quarantine'),
        ('tag', 'Tag'),
    ]

    name = models.CharField(max_length=255)
    filter_type = models.CharField(max_length=7, choices=FILTER_TYPE_CHOICES)
    pattern = models.CharField(max_length=255)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.filter_type})"

    class Meta:
        ordering = ['priority']

class MailQueue(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('deferred', 'Deferred'),
    ]

    message_id = models.CharField(max_length=255, unique=True)
    from_address = models.EmailField()
    to_address = models.EmailField()
    subject = models.CharField(max_length=255)
    size = models.IntegerField()
    status = models.CharField(max_length=8, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    next_retry = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.message_id} - {self.status}"

class MailLog(models.Model):
    EVENT_CHOICES = [
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('deferred', 'Deferred'),
        ('bounced', 'Bounced'),
        ('rejected', 'Rejected'),
        ('virus', 'Virus Detected'),
        ('spam', 'Spam Detected'),
    ]

    timestamp = models.DateTimeField()
    event = models.CharField(max_length=8, choices=EVENT_CHOICES)
    from_address = models.EmailField()
    to_address = models.EmailField()
    subject = models.CharField(max_length=255)
    message_id = models.CharField(max_length=255)
    size = models.IntegerField()
    client_ip = models.GenericIPAddressField()
    server_ip = models.GenericIPAddressField()
    status = models.CharField(max_length=255)
    status_code = models.CharField(max_length=3)
    tls_enabled = models.BooleanField(default=False)
    spam_score = models.FloatField(null=True, blank=True)
    queue_id = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)

    def __str__(self):
        return f"{self.timestamp} - {self.event} - {self.message_id}"

    class Meta:
        ordering = ['-timestamp']
