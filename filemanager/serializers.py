from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Directory, File, FileShare, FileOperation, FileBackup

class FileSerializer(serializers.ModelSerializer):
    full_path = serializers.SerializerMethodField()
    size_human = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source='owner.username', read_only=True)

    class Meta:
        model = File
        fields = '__all__'

    def get_full_path(self, obj):
        return f"{obj.path}/{obj.name}"

    def get_size_human(self, obj):
        """Convert size to human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if obj.size < 1024:
                return f"{obj.size:.2f} {unit}"
            obj.size /= 1024
        return f"{obj.size:.2f} PB"

class DirectorySerializer(serializers.ModelSerializer):
    files = FileSerializer(many=True, read_only=True)
    size_human = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    full_path = serializers.SerializerMethodField()

    class Meta:
        model = Directory
        fields = '__all__'

    def get_size_human(self, obj):
        """Convert size to human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if obj.size < 1024:
                return f"{obj.size:.2f} {unit}"
            obj.size /= 1024
        return f"{obj.size:.2f} PB"

    def get_full_path(self, obj):
        return f"{obj.path}/{obj.name}"

class FileShareSerializer(serializers.ModelSerializer):
    file_name = serializers.CharField(source='file.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    share_url = serializers.SerializerMethodField()
    allowed_emails_list = serializers.SerializerMethodField()

    class Meta:
        model = FileShare
        fields = '__all__'
        extra_kwargs = {
            'token': {'read_only': True},
            'password_hash': {'write_only': True}
        }

    def get_share_url(self, obj):
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(f'/share/{obj.token}')
        return f'/share/{obj.token}'

    def get_allowed_emails_list(self, obj):
        return [email.strip() for email in obj.allowed_emails.split('\n') if email.strip()]

class FileOperationSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = FileOperation
        fields = '__all__'

    def get_duration(self, obj):
        if obj.completed_at and obj.created_at:
            duration = obj.completed_at - obj.created_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None

class FileBackupSerializer(serializers.ModelSerializer):
    directory_path = serializers.CharField(source='directory.path', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    size_human = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()

    class Meta:
        model = FileBackup
        fields = '__all__'

    def get_size_human(self, obj):
        """Convert size to human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if obj.size < 1024:
                return f"{obj.size:.2f} {unit}"
            obj.size /= 1024
        return f"{obj.size:.2f} PB"

    def get_duration(self, obj):
        if obj.completed_at and obj.started_at:
            duration = obj.completed_at - obj.started_at
            return str(duration).split('.')[0]  # Remove microseconds
        return None

class FileStatisticsSerializer(serializers.Serializer):
    total_files = serializers.IntegerField()
    total_directories = serializers.IntegerField()
    total_size = serializers.IntegerField()
    total_size_human = serializers.CharField()
    active_shares = serializers.IntegerField()
    recent_operations = serializers.IntegerField()
    mime_type_distribution = serializers.DictField()
    size_distribution = serializers.DictField()
    recent_backups = serializers.IntegerField()
    storage_usage_percent = serializers.FloatField() 