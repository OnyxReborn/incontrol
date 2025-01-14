from rest_framework import serializers
from django.contrib.auth.models import User
from .models import LogFile, LogEntry, LogAlert, LogRotationPolicy

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']

class LogFileSerializer(serializers.ModelSerializer):
    size = serializers.SerializerMethodField()
    last_modified = serializers.SerializerMethodField()

    class Meta:
        model = LogFile
        fields = '__all__'

    def get_size(self, obj):
        try:
            import os
            return os.path.getsize(obj.path)
        except:
            return 0

    def get_last_modified(self, obj):
        try:
            import os
            return os.path.getmtime(obj.path)
        except:
            return None

class LogEntrySerializer(serializers.ModelSerializer):
    log_file_name = serializers.CharField(source='log_file.name', read_only=True)
    relative_time = serializers.SerializerMethodField()

    class Meta:
        model = LogEntry
        fields = '__all__'

    def get_relative_time(self, obj):
        from django.utils import timezone
        from datetime import datetime
        now = timezone.now()
        diff = now - obj.timestamp

        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours} hours ago"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago"
        else:
            return f"{diff.seconds} seconds ago"

class LogAlertSerializer(serializers.ModelSerializer):
    notify_users = UserSerializer(many=True, read_only=True)
    log_file_name = serializers.CharField(source='log_file.name', read_only=True)

    class Meta:
        model = LogAlert
        fields = '__all__'

    def validate(self, data):
        if data['alert_type'] == 'pattern' and not data.get('pattern'):
            raise serializers.ValidationError("Pattern is required for pattern-based alerts")
        elif data['alert_type'] == 'frequency' and not data.get('frequency_threshold'):
            raise serializers.ValidationError("Frequency threshold is required for frequency-based alerts")
        elif data['alert_type'] == 'severity' and not data.get('severity_threshold'):
            raise serializers.ValidationError("Severity threshold is required for severity-based alerts")
        return data

class LogRotationPolicySerializer(serializers.ModelSerializer):
    log_file_name = serializers.CharField(source='log_file.name', read_only=True)
    next_rotation = serializers.SerializerMethodField()

    class Meta:
        model = LogRotationPolicy
        fields = '__all__'

    def get_next_rotation(self, obj):
        from datetime import datetime, timedelta
        if not obj.last_rotation:
            return None

        if obj.rotation_unit == 'daily':
            return obj.last_rotation + timedelta(days=1)
        elif obj.rotation_unit == 'weekly':
            return obj.last_rotation + timedelta(weeks=1)
        elif obj.rotation_unit == 'monthly':
            # Approximate month as 30 days
            return obj.last_rotation + timedelta(days=30)
        else:
            return None

class LogStatisticsSerializer(serializers.Serializer):
    total_logs = serializers.IntegerField()
    total_entries = serializers.IntegerField()
    entries_by_severity = serializers.DictField()
    entries_by_source = serializers.DictField()
    entries_last_24h = serializers.IntegerField()
    active_alerts = serializers.IntegerField()
    total_size = serializers.IntegerField()
    rotation_pending = serializers.IntegerField() 