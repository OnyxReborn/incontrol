from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Count, Avg
from .models import DNSZone, DNSRecord, DNSTemplate, DNSQuery, DNSHealth
from .serializers import (
    DNSZoneSerializer, DNSRecordSerializer, DNSTemplateSerializer,
    DNSQuerySerializer, DNSHealthSerializer, DNSStatisticsSerializer
)
import dns.resolver
import dns.zone
import dns.query
import dns.exception

class DNSZoneViewSet(viewsets.ModelViewSet):
    queryset = DNSZone.objects.all()
    serializer_class = DNSZoneSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def sync_records(self, request, pk=None):
        """Sync records with primary nameserver"""
        zone = self.get_object()
        try:
            # Attempt zone transfer
            xfr = dns.query.xfr(zone.primary_ns, zone.name)
            zone_data = dns.zone.from_xfr(xfr)
            
            # Update local records
            for name, node in zone_data.items():
                for rdataset in node.rdatasets:
                    for rdata in rdataset:
                        DNSRecord.objects.update_or_create(
                            zone=zone,
                            name=str(name),
                            type=dns.rdatatype.to_text(rdataset.rdtype),
                            defaults={
                                'content': str(rdata),
                                'ttl': rdataset.ttl
                            }
                        )
            
            return Response({'status': 'success'})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def apply_template(self, request, pk=None):
        """Apply a DNS template to the zone"""
        zone = self.get_object()
        template_id = request.data.get('template_id')
        
        try:
            template = DNSTemplate.objects.get(pk=template_id)
            for record in template.records:
                DNSRecord.objects.create(
                    zone=zone,
                    name=record['name'],
                    type=record['type'],
                    content=record['content'],
                    ttl=record.get('ttl', 3600),
                    priority=record.get('priority')
                )
            return Response({'status': 'success'})
        except DNSTemplate.DoesNotExist:
            return Response(
                {'error': 'Template not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DNSRecordViewSet(viewsets.ModelViewSet):
    queryset = DNSRecord.objects.all()
    serializer_class = DNSRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DNSRecord.objects.all()
        zone_id = self.request.query_params.get('zone', None)
        if zone_id is not None:
            queryset = queryset.filter(zone_id=zone_id)
        return queryset

class DNSTemplateViewSet(viewsets.ModelViewSet):
    queryset = DNSTemplate.objects.all()
    serializer_class = DNSTemplateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class DNSQueryViewSet(viewsets.ModelViewSet):
    queryset = DNSQuery.objects.all()
    serializer_class = DNSQuerySerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def lookup(self, request):
        """Perform DNS lookup"""
        domain = request.data.get('domain')
        query_type = request.data.get('type', 'A')
        nameserver = request.data.get('nameserver', '')

        try:
            resolver = dns.resolver.Resolver()
            if nameserver:
                resolver.nameservers = [nameserver]

            start_time = timezone.now()
            answers = resolver.resolve(domain, query_type)
            end_time = timezone.now()
            response_time = (end_time - start_time).total_seconds() * 1000

            response = {
                'answers': [
                    {
                        'name': str(answer.name),
                        'type': dns.rdatatype.to_text(answer.rdtype),
                        'ttl': answer.ttl,
                        'data': str(answer)
                    }
                    for answer in answers
                ]
            }

            query = DNSQuery.objects.create(
                domain=domain,
                query_type=query_type,
                nameserver=nameserver,
                response=response,
                response_time=response_time
            )

            return Response(DNSQuerySerializer(query).data)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DNSHealthViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DNSHealth.objects.all()
    serializer_class = DNSHealthSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = DNSHealth.objects.all()
        zone_id = self.request.query_params.get('zone', None)
        if zone_id is not None:
            queryset = queryset.filter(zone_id=zone_id)
        return queryset

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get DNS health statistics"""
        now = timezone.now()
        stats = {
            'total_zones': DNSZone.objects.count(),
            'active_zones': DNSZone.objects.filter(is_active=True).count(),
            'total_records': DNSRecord.objects.count(),
            'zones_with_issues': DNSHealth.objects.filter(
                status__in=['warning', 'error']
            ).values('zone').distinct().count(),
            'average_response_time': DNSHealth.objects.filter(
                check_time__gte=now - timezone.timedelta(hours=24)
            ).aggregate(avg_time=Avg('response_time'))['avg_time'] or 0,
            'record_types_distribution': dict(
                DNSRecord.objects.values('type')
                .annotate(count=Count('id'))
                .values_list('type', 'count')
            ),
            'recent_queries': DNSQuery.objects.filter(
                created_at__gte=now - timezone.timedelta(hours=24)
            ).count(),
            'health_summary': dict(
                DNSHealth.objects.values('status')
                .annotate(count=Count('id'))
                .values_list('status', 'count')
            ),
            'last_check': DNSHealth.objects.latest('check_time').check_time
            if DNSHealth.objects.exists() else None
        }

        serializer = DNSStatisticsSerializer(stats)
        return Response(serializer.data) 