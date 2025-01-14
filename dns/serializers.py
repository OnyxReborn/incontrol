from rest_framework import serializers
from .models import DNSZone, DNSRecord, DNSTemplate, DNSQuery, DNSHealth

class DNSRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DNSRecord
        fields = '__all__'

class DNSZoneSerializer(serializers.ModelSerializer):
    records = DNSRecordSerializer(many=True, read_only=True)
    records_count = serializers.SerializerMethodField()
    health_status = serializers.SerializerMethodField()

    class Meta:
        model = DNSZone
        fields = '__all__'

    def get_records_count(self, obj):
        return obj.records.count()

    def get_health_status(self, obj):
        latest_health = obj.dnshealth_set.first()
        if latest_health:
            return {
                'status': latest_health.status,
                'check_time': latest_health.check_time,
                'issues': latest_health.issues
            }
        return None

class DNSTemplateSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = DNSTemplate
        fields = '__all__'

class DNSQuerySerializer(serializers.ModelSerializer):
    response_formatted = serializers.SerializerMethodField()

    class Meta:
        model = DNSQuery
        fields = '__all__'

    def get_response_formatted(self, obj):
        """Format DNS response for better readability"""
        formatted = []
        for record in obj.response.get('answers', []):
            formatted.append({
                'name': record.get('name'),
                'type': record.get('type'),
                'ttl': record.get('ttl'),
                'data': record.get('data')
            })
        return formatted

class DNSHealthSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source='zone.name', read_only=True)

    class Meta:
        model = DNSHealth
        fields = '__all__'

class DNSStatisticsSerializer(serializers.Serializer):
    total_zones = serializers.IntegerField()
    active_zones = serializers.IntegerField()
    total_records = serializers.IntegerField()
    zones_with_issues = serializers.IntegerField()
    average_response_time = serializers.FloatField()
    record_types_distribution = serializers.DictField()
    recent_queries = serializers.IntegerField()
    health_summary = serializers.DictField()
    last_check = serializers.DateTimeField() 