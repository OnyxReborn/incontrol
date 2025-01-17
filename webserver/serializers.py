from rest_framework import serializers
from .models import VirtualHost, SSLCertificate, ProxyConfig, AccessControl, EmailAccount, EmailForwarder, SpamFilter, Database, DatabaseUser, DatabaseBackup, IPBlock, ModSecurityRule, ProtectedDirectory, Subdomain, DomainRedirect, DNSZone, BackupConfig, BackupJob, ResourceUsage, BandwidthUsage, ErrorLog, AccessLog
from django.contrib.auth.hashers import make_password

class ProxyConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProxyConfig
        fields = '__all__'

class AccessControlSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessControl
        fields = '__all__'

class VirtualHostSerializer(serializers.ModelSerializer):
    proxy_configs = ProxyConfigSerializer(many=True, read_only=True)
    access_controls = AccessControlSerializer(many=True, read_only=True)
    domains_list = serializers.SerializerMethodField()

    class Meta:
        model = VirtualHost
        fields = '__all__'
        read_only_fields = ('status',)

    def get_domains_list(self, obj):
        return [domain.strip() for domain in obj.domains.split('\n') if domain.strip()]

class SSLCertificateSerializer(serializers.ModelSerializer):
    days_until_expiry = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    domains_list = serializers.SerializerMethodField()

    class Meta:
        model = SSLCertificate
        fields = ['id', 'name', 'domains', 'domains_list', 'key_file', 'cert_file', 'chain_file', 'issuer', 
                 'valid_from', 'valid_until', 'auto_renew', 'is_expired', 'days_until_expiry', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at', 'is_expired', 'days_until_expiry']

    def get_domains_list(self, obj):
        return [domain.strip() for domain in obj.domains.split('\n') if domain.strip()]

class EmailAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAccount
        fields = ['id', 'username', 'domain', 'quota', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = super().create(validated_data)
        if password:
            instance.password = make_password(password)
            instance.save()
        return instance

class EmailForwarderSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailForwarder
        fields = ['id', 'source', 'destination', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class SpamFilterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpamFilter
        fields = ['id', 'type', 'value', 'description', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at'] 

class DatabaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Database
        fields = ['id', 'name', 'collation', 'size', 'created_at', 'updated_at']
        read_only_fields = ['size', 'created_at', 'updated_at']

class DatabaseUserSerializer(serializers.ModelSerializer):
    databases = serializers.PrimaryKeyRelatedField(many=True, queryset=Database.objects.all())

    class Meta:
        model = DatabaseUser
        fields = ['id', 'username', 'host', 'databases', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = super().create(validated_data)
        if password:
            instance.password = make_password(password)
            instance.save()
        return instance

class DatabaseBackupSerializer(serializers.ModelSerializer):
    database_name = serializers.CharField(source='database.name', read_only=True)

    class Meta:
        model = DatabaseBackup
        fields = ['id', 'database', 'database_name', 'file_path', 'size', 'created_at']
        read_only_fields = ['file_path', 'size', 'created_at'] 

class IPBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPBlock
        fields = ['id', 'ip_address', 'rule_type', 'description', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class ModSecurityRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModSecurityRule
        fields = ['id', 'rule_id', 'description', 'rule_content', 'severity', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class ProtectedDirectorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProtectedDirectory
        fields = ['id', 'path', 'username', 'description', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = super().create(validated_data)
        if password:
            instance.password = make_password(password)
            instance.save()
        return instance 

class SubdomainSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = Subdomain
        fields = ['id', 'name', 'domain', 'domain_name', 'document_root', 'is_wildcard', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class DomainRedirectSerializer(serializers.ModelSerializer):
    class Meta:
        model = DomainRedirect
        fields = ['id', 'source_domain', 'target_domain', 'redirect_type', 'preserve_path', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

class DNSZoneSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = DNSZone
        fields = ['id', 'domain', 'domain_name', 'name', 'record_type', 'content', 'ttl', 'priority', 'enabled', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at'] 

class BackupConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupConfig
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

class BackupJobSerializer(serializers.ModelSerializer):
    config_name = serializers.CharField(source='config.name', read_only=True)
    
    class Meta:
        model = BackupJob
        fields = '__all__'
        read_only_fields = ('started_at', 'completed_at', 'backup_size', 'file_path', 'error_message') 

class ResourceUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceUsage
        fields = '__all__'

class BandwidthUsageSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = BandwidthUsage
        fields = '__all__'

class ErrorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorLog
        fields = '__all__'

class AccessLogSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = AccessLog
        fields = '__all__' 