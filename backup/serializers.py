from rest_framework import serializers
from .models import Backup, BackupSchedule, BackupLog

class BackupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupLog
        fields = ['id', 'timestamp', 'message', 'level']

class BackupSerializer(serializers.ModelSerializer):
    logs = BackupLogSerializer(many=True, read_only=True)

    class Meta:
        model = Backup
        fields = [
            'id', 'name', 'type', 'status', 'size', 'path',
            'created_at', 'completed_at', 'error_message', 'logs'
        ]
        read_only_fields = ['id', 'size', 'path', 'created_at', 'completed_at', 'status', 'error_message']

    def validate_name(self, value):
        if len(value.strip()) == 0:
            raise serializers.ValidationError("Backup name cannot be empty")
        return value

    def validate_type(self, value):
        if value not in dict(Backup.BACKUP_TYPES):
            raise serializers.ValidationError("Invalid backup type")
        return value

class BackupScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupSchedule
        fields = [
            'id', 'name', 'type', 'frequency', 'retention_days',
            'next_run', 'last_run', 'enabled', 'created_at'
        ]
        read_only_fields = ['id', 'next_run', 'last_run', 'created_at']

    def validate_name(self, value):
        if len(value.strip()) == 0:
            raise serializers.ValidationError("Schedule name cannot be empty")
        return value

    def validate_type(self, value):
        if value not in dict(BackupSchedule.BACKUP_TYPES):
            raise serializers.ValidationError("Invalid backup type")
        return value

    def validate_frequency(self, value):
        if value not in dict(BackupSchedule.FREQUENCY_CHOICES):
            raise serializers.ValidationError("Invalid frequency")
        return value

    def validate_retention_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Retention days must be at least 1")
        return value

class BackupStatsSerializer(serializers.Serializer):
    total_backups = serializers.IntegerField()
    total_size = serializers.IntegerField()
    active_schedules = serializers.IntegerField()
    last_backup_time = serializers.DateTimeField(allow_null=True)
    storage_usage = serializers.DictField(
        child=serializers.IntegerField(),
        allow_empty=True
    )
    backup_types = serializers.DictField(
        child=serializers.IntegerField(),
        allow_empty=True
    )
    success_rate = serializers.FloatField()
    average_backup_size = serializers.IntegerField()
    backup_frequency = serializers.DictField(
        child=serializers.IntegerField(),
        allow_empty=True
    )
    storage_locations = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(),
            allow_empty=False
        ),
        allow_empty=True
    ) 