from rest_framework import serializers
from .models import MetricSnapshot, ServiceStatus, AlertRule, Alert

class MetricSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricSnapshot
        fields = '__all__'

class ServiceStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStatus
        fields = '__all__'

class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = '__all__'

class AlertSerializer(serializers.ModelSerializer):
    rule = AlertRuleSerializer(read_only=True)
    acknowledged_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Alert
        fields = '__all__' 