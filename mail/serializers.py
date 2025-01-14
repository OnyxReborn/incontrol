from rest_framework import serializers
from .models import MailDomain, MailAccount, MailAlias, SpamFilter, MailQueue, MailLog

class MailDomainSerializer(serializers.ModelSerializer):
    accounts_count = serializers.SerializerMethodField()
    aliases_count = serializers.SerializerMethodField()

    class Meta:
        model = MailDomain
        fields = '__all__'
        extra_kwargs = {
            'dkim_private_key': {'write_only': True}
        }

    def get_accounts_count(self, obj):
        return obj.accounts.count()

    def get_aliases_count(self, obj):
        return obj.aliases.count()

class MailAccountSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.name', read_only=True)
    quota_used_percent = serializers.SerializerMethodField()
    forward_to_list = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = MailAccount
        fields = '__all__'
        read_only_fields = ('password_hash', 'used_quota')
        extra_kwargs = {
            'password_hash': {'write_only': True}
        }

    def get_quota_used_percent(self, obj):
        if obj.quota > 0:
            return (obj.used_quota / obj.quota) * 100
        return 0

    def get_forward_to_list(self, obj):
        return [email.strip() for email in obj.forward_to.split('\n') if email.strip()]

class MailAliasSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.name', read_only=True)
    destinations_list = serializers.SerializerMethodField()

    class Meta:
        model = MailAlias
        fields = '__all__'

    def get_destinations_list(self, obj):
        return [email.strip() for email in obj.destinations.split('\n') if email.strip()]

class SpamFilterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpamFilter
        fields = '__all__'

class MailQueueSerializer(serializers.ModelSerializer):
    time_in_queue = serializers.SerializerMethodField()

    class Meta:
        model = MailQueue
        fields = '__all__'

    def get_time_in_queue(self, obj):
        from django.utils import timezone
        delta = timezone.now() - obj.created_at
        hours = delta.total_seconds() / 3600
        return round(hours, 2)

class MailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MailLog
        fields = '__all__'

class MailStatisticsSerializer(serializers.Serializer):
    total_accounts = serializers.IntegerField()
    active_accounts = serializers.IntegerField()
    total_domains = serializers.IntegerField()
    active_domains = serializers.IntegerField()
    total_aliases = serializers.IntegerField()
    messages_today = serializers.IntegerField()
    messages_week = serializers.IntegerField()
    messages_month = serializers.IntegerField()
    spam_detected_today = serializers.IntegerField()
    virus_detected_today = serializers.IntegerField()
    queue_size = serializers.IntegerField()
    deferred_messages = serializers.IntegerField()
    storage_used = serializers.IntegerField()
    storage_used_human = serializers.CharField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Convert storage to human-readable format
        size = instance['storage_used']
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                data['storage_used_human'] = f"{size:.2f} {unit}"
                break
            size /= 1024
        return data 