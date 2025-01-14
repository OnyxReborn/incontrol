from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    FirewallRule, SecurityScan, SecurityIncident,
    SSHKey, FailedLogin
)

class FirewallRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirewallRule
        fields = '__all__'

class SecurityScanSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = SecurityScan
        fields = '__all__'

    def get_duration(self, obj):
        if obj.started_at and obj.completed_at:
            duration = obj.completed_at - obj.started_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None

class SecurityIncidentSerializer(serializers.ModelSerializer):
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    time_to_resolve = serializers.SerializerMethodField()

    class Meta:
        model = SecurityIncident
        fields = '__all__'

    def get_time_to_resolve(self, obj):
        if obj.detected_at and obj.resolved_at:
            duration = obj.resolved_at - obj.detected_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None

class SSHKeySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = SSHKey
        fields = '__all__'
        extra_kwargs = {
            'fingerprint': {'read_only': True}
        }

    def create(self, validated_data):
        # Generate fingerprint before saving
        from hashlib import sha256
        key = validated_data['public_key'].strip()
        fingerprint = sha256(key.encode()).hexdigest()
        validated_data['fingerprint'] = fingerprint
        return super().create(validated_data)

class FailedLoginSerializer(serializers.ModelSerializer):
    time_since = serializers.SerializerMethodField()

    class Meta:
        model = FailedLogin
        fields = '__all__'

    def get_time_since(self, obj):
        from django.utils import timezone
        delta = timezone.now() - obj.attempt_time
        return str(delta).split('.')[0]  # Remove microseconds

class SecurityStatisticsSerializer(serializers.Serializer):
    total_incidents = serializers.IntegerField()
    open_incidents = serializers.IntegerField()
    critical_incidents = serializers.IntegerField()
    recent_failed_logins = serializers.IntegerField()
    blocked_ips = serializers.IntegerField()
    active_firewall_rules = serializers.IntegerField()
    recent_scans = serializers.IntegerField()
    vulnerabilities_found = serializers.IntegerField()
    ssh_keys_active = serializers.IntegerField()
    last_security_scan = serializers.DateTimeField()
    last_incident = serializers.DateTimeField()
    average_resolution_time = serializers.CharField() 