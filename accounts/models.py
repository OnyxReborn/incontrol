from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    ssh_key = models.TextField(blank=True)
    is_active_shell = models.BooleanField(default=False)
    shell_path = models.CharField(max_length=255, default='/bin/bash')
    home_directory = models.CharField(max_length=255)
    disk_quota = models.BigIntegerField(default=5368709120)  # 5GB in bytes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

class UserGroup(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    users = models.ManyToManyField(User, related_name='custom_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class AccessKey(models.Model):
    KEY_TYPE_CHOICES = [
        ('API', 'API Key'),
        ('SSH', 'SSH Key'),
        ('FTP', 'FTP Credentials'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='access_keys')
    key_type = models.CharField(max_length=3, choices=KEY_TYPE_CHOICES)
    key_name = models.CharField(max_length=255)
    key_value = models.TextField()
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'key_name', 'key_type')

    def __str__(self):
        return f"{self.user.username} - {self.key_name} ({self.key_type})"
