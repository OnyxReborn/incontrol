from rest_framework import serializers
from .models import Service, Package, Backup, CronJob

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = '__all__'
        read_only_fields = ('status', 'last_check')

class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = '__all__'
        read_only_fields = ('is_installed', 'installation_date', 'last_update')

class BackupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Backup
        fields = '__all__'
        read_only_fields = ('status', 'file_size', 'started_at', 'completed_at', 'error_message')

class CronJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = CronJob
        fields = '__all__'
        read_only_fields = ('last_run', 'next_run') 