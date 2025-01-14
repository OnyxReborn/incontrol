from rest_framework import serializers
from .models import Database, DatabaseUser, DatabasePrivilege, DatabaseBackup

class DatabaseSerializer(serializers.ModelSerializer):
    size_human = serializers.SerializerMethodField()

    class Meta:
        model = Database
        fields = '__all__'
        read_only_fields = ('size',)

    def get_size_human(self, obj):
        """Convert size to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if obj.size < 1024:
                return f"{obj.size:.2f} {unit}"
            obj.size /= 1024
        return f"{obj.size:.2f} PB"

class DatabaseUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = DatabaseUser
        fields = '__all__'
        extra_fields = ['password']

class DatabasePrivilegeSerializer(serializers.ModelSerializer):
    database_name = serializers.CharField(source='database.name', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = DatabasePrivilege
        fields = '__all__'

    def validate_privileges(self, value):
        """Validate that all privileges are valid choices."""
        valid_privileges = [choice[0] for choice in DatabasePrivilege.PRIVILEGE_CHOICES]
        for privilege in value:
            if privilege not in valid_privileges:
                raise serializers.ValidationError(f"Invalid privilege: {privilege}")
        return value

class DatabaseBackupSerializer(serializers.ModelSerializer):
    database_name = serializers.CharField(source='database.name', read_only=True)
    size_human = serializers.SerializerMethodField()

    class Meta:
        model = DatabaseBackup
        fields = '__all__'
        read_only_fields = ('status', 'size', 'error_message', 'started_at', 'completed_at')

    def get_size_human(self, obj):
        """Convert size to human-readable format."""
        if obj.size is None:
            return None
        
        size = obj.size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB" 