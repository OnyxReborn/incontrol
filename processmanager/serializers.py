from rest_framework import serializers
from .models import Process, Service, ResourceUsage, ProcessLimit, ProcessAlert

class ProcessSerializer(serializers.ModelSerializer):
    memory_human = serializers.SerializerMethodField()

    class Meta:
        model = Process
        fields = '__all__'

    def get_memory_human(self, obj):
        """Convert memory percentage to human-readable format"""
        total_memory = self.context.get('total_memory', 0)
        memory_bytes = (obj.memory_percent / 100) * total_memory
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if memory_bytes < 1024:
                return f"{memory_bytes:.2f} {unit}"
            memory_bytes /= 1024
        return f"{memory_bytes:.2f} PB"

class ServiceSerializer(serializers.ModelSerializer):
    uptime = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = '__all__'

    def get_uptime(self, obj):
        """Calculate service uptime"""
        if obj.last_restart:
            from django.utils import timezone
            uptime = timezone.now() - obj.last_restart
            return str(uptime).split('.')[0]  # Remove microseconds
        return None

class ResourceUsageSerializer(serializers.ModelSerializer):
    disk_io_read_human = serializers.SerializerMethodField()
    disk_io_write_human = serializers.SerializerMethodField()
    network_io_receive_human = serializers.SerializerMethodField()
    network_io_send_human = serializers.SerializerMethodField()

    class Meta:
        model = ResourceUsage
        fields = '__all__'

    def _format_bytes(self, bytes_value):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.2f} PB"

    def get_disk_io_read_human(self, obj):
        return self._format_bytes(obj.disk_io_read)

    def get_disk_io_write_human(self, obj):
        return self._format_bytes(obj.disk_io_write)

    def get_network_io_receive_human(self, obj):
        return self._format_bytes(obj.network_io_receive)

    def get_network_io_send_human(self, obj):
        return self._format_bytes(obj.network_io_send)

class ProcessLimitSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ProcessLimit
        fields = '__all__'

class ProcessAlertSerializer(serializers.ModelSerializer):
    process_name = serializers.CharField(source='process.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = ProcessAlert
        fields = '__all__'

    def get_duration(self, obj):
        if obj.is_resolved and obj.resolved_at:
            duration = obj.resolved_at - obj.created_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None

class ProcessStatisticsSerializer(serializers.Serializer):
    total_processes = serializers.IntegerField()
    running_processes = serializers.IntegerField()
    sleeping_processes = serializers.IntegerField()
    stopped_processes = serializers.IntegerField()
    zombie_processes = serializers.IntegerField()
    total_threads = serializers.IntegerField()
    cpu_usage = serializers.FloatField()
    memory_usage = serializers.FloatField()
    swap_usage = serializers.FloatField()
    load_averages = serializers.DictField()
    top_cpu_processes = serializers.ListField()
    top_memory_processes = serializers.ListField()
    active_services = serializers.IntegerField()
    failed_services = serializers.IntegerField()
    recent_alerts = serializers.IntegerField()
    unresolved_alerts = serializers.IntegerField() 