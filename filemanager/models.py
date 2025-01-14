from django.db import models
from django.contrib.auth.models import User
import os

class Directory(models.Model):
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=1024)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.CharField(max_length=255)
    permissions = models.CharField(max_length=9, default='rwxr-xr-x')  # Unix-style permissions
    size = models.BigIntegerField(default=0)  # Total size in bytes
    files_count = models.IntegerField(default=0)
    dirs_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_scanned = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.path

    class Meta:
        unique_together = ('path', 'name')
        ordering = ['path', 'name']

class File(models.Model):
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=1024)
    directory = models.ForeignKey(Directory, on_delete=models.CASCADE, related_name='files')
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.CharField(max_length=255)
    permissions = models.CharField(max_length=9, default='rw-r--r--')  # Unix-style permissions
    size = models.BigIntegerField(default=0)  # Size in bytes
    mime_type = models.CharField(max_length=255)
    md5_hash = models.CharField(max_length=32, blank=True)
    is_symlink = models.BooleanField(default=False)
    symlink_target = models.CharField(max_length=1024, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return os.path.join(self.path, self.name)

    class Meta:
        unique_together = ('path', 'name')
        ordering = ['name']

class FileShare(models.Model):
    TYPE_CHOICES = [
        ('public', 'Public Link'),
        ('password', 'Password Protected'),
        ('email', 'Email Restricted'),
    ]

    file = models.ForeignKey(File, on_delete=models.CASCADE)
    share_type = models.CharField(max_length=8, choices=TYPE_CHOICES)
    token = models.CharField(max_length=64, unique=True)
    password_hash = models.CharField(max_length=128, blank=True)
    allowed_emails = models.TextField(blank=True, help_text="One email per line")
    expires_at = models.DateTimeField(null=True, blank=True)
    max_downloads = models.IntegerField(null=True, blank=True)
    download_count = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.file.name} - {self.share_type}"

class FileOperation(models.Model):
    OPERATION_CHOICES = [
        ('create', 'Create'),
        ('modify', 'Modify'),
        ('delete', 'Delete'),
        ('move', 'Move'),
        ('copy', 'Copy'),
        ('chmod', 'Change Permissions'),
        ('chown', 'Change Owner'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    operation = models.CharField(max_length=10, choices=OPERATION_CHOICES)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='pending')
    source_path = models.CharField(max_length=1024)
    destination_path = models.CharField(max_length=1024, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.operation} - {self.source_path}"

    class Meta:
        ordering = ['-created_at']

class FileBackup(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    directory = models.ForeignKey(Directory, on_delete=models.CASCADE)
    backup_path = models.CharField(max_length=1024)
    size = models.BigIntegerField(default=0)  # Size in bytes
    files_count = models.IntegerField(default=0)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.directory.path} - {self.created_at}"

    class Meta:
        ordering = ['-created_at'] 