from rest_framework import serializers
from .models import (
    MetricSnapshot,
    ServiceStatus,
    Alert,
    AlertRule,
    NetworkInterface,
    DiskPartition,
    Process,
    ServiceLog,
)

class MetricSnapshotSerializer(serializers.ModelSerializer):
    load_average = serializers.SerializerMethodField()

    class Meta:
        model = MetricSnapshot
        fields = '__all__'

    def get_load_average(self, obj):
        return [obj.load_average_1m, obj.load_average_5m, obj.load_average_15m]

class ServiceStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceStatus
        fields = '__all__'

class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = '__all__'

class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = '__all__'

class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = '__all__'

class DiskPartitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiskPartition
        fields = '__all__'

class ProcessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Process
        fields = '__all__'

class ServiceLogSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = ServiceLog
        fields = '__all__'

class SystemMetricsSerializer(serializers.Serializer):
    cpu_usage = serializers.FloatField()
    memory_usage = serializers.FloatField()
    disk_usage = serializers.FloatField()
    network_in = serializers.IntegerField()
    network_out = serializers.IntegerField()
    load_average = serializers.ListField(child=serializers.FloatField())
    uptime = serializers.IntegerField()

class ResourceUsageSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField()
    cpu = serializers.FloatField()
    memory = serializers.FloatField()
    disk = serializers.FloatField()
    network_in = serializers.IntegerField()
    network_out = serializers.IntegerField()

class SystemInfoSerializer(serializers.Serializer):
    hostname = serializers.CharField()
    os = serializers.CharField()
    platform = serializers.CharField()
    cpu_count = serializers.IntegerField()
    total_memory = serializers.IntegerField()
    total_disk = serializers.IntegerField()
    python_version = serializers.CharField()
    timezone = serializers.CharField()

class NetworkStatsSerializer(serializers.Serializer):
    interface = serializers.CharField()
    bytes_sent = serializers.IntegerField()
    bytes_received = serializers.IntegerField()
    packets_sent = serializers.IntegerField()
    packets_received = serializers.IntegerField()
    errors_in = serializers.IntegerField()
    errors_out = serializers.IntegerField()

class AlertRuleTestResultSerializer(serializers.Serializer):
    triggered = serializers.BooleanField()
    current_value = serializers.FloatField()
    threshold = serializers.FloatField()
    message = serializers.CharField()
    would_notify = serializers.ListField(child=serializers.CharField()) 