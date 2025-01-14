from rest_framework import serializers
from .models import VirtualHost, SSLCertificate, ProxyConfig, AccessControl

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
    domains_list = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()

    class Meta:
        model = SSLCertificate
        fields = '__all__'

    def get_domains_list(self, obj):
        return [domain.strip() for domain in obj.domains.split('\n') if domain.strip()]

    def get_days_until_expiry(self, obj):
        from django.utils import timezone
        delta = obj.expiry_date - timezone.now()
        return delta.days 