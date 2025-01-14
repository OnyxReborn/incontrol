from django.db import models
from django.contrib.auth.models import User

class Database(models.Model):
    name = models.CharField(max_length=64, unique=True)
    character_set = models.CharField(max_length=32, default='utf8mb4')
    collation = models.CharField(max_length=32, default='utf8mb4_unicode_ci')
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    size = models.BigIntegerField(default=0)  # Size in bytes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class DatabaseUser(models.Model):
    username = models.CharField(max_length=32, unique=True)
    host = models.CharField(max_length=255, default='localhost')
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    databases = models.ManyToManyField(Database, through='DatabasePrivilege')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('username', 'host')

    def __str__(self):
        return f"{self.username}@{self.host}"

class DatabasePrivilege(models.Model):
    PRIVILEGE_CHOICES = [
        ('ALL', 'All Privileges'),
        ('SELECT', 'Select'),
        ('INSERT', 'Insert'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('CREATE', 'Create'),
        ('DROP', 'Drop'),
        ('REFERENCES', 'References'),
        ('INDEX', 'Index'),
        ('ALTER', 'Alter'),
        ('CREATE_TMP', 'Create Temporary Tables'),
        ('LOCK', 'Lock Tables'),
        ('EXECUTE', 'Execute'),
        ('CREATE_VIEW', 'Create View'),
        ('SHOW_VIEW', 'Show View'),
        ('CREATE_ROUTINE', 'Create Routine'),
        ('ALTER_ROUTINE', 'Alter Routine'),
        ('EVENT', 'Event'),
        ('TRIGGER', 'Trigger'),
    ]

    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    user = models.ForeignKey(DatabaseUser, on_delete=models.CASCADE)
    privileges = models.JSONField(default=list)  # List of privileges
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('database', 'user')

    def __str__(self):
        return f"{self.user} -> {self.database}"

class DatabaseBackup(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    database = models.ForeignKey(Database, on_delete=models.CASCADE)
    filename = models.CharField(max_length=255)
    size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.database.name} - {self.created_at}"
