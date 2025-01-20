from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Count, Avg
from datetime import timedelta

from .models import (
    FirewallRule, SecurityScan, SecurityIncident,
    SSHKey, FailedLogin
)
from .serializers import (
    FirewallRuleSerializer, SecurityScanSerializer,
    SecurityIncidentSerializer, SSHKeySerializer,
    FailedLoginSerializer, SecurityStatisticsSerializer
)
from .tasks import (
    apply_firewall_rule, remove_firewall_rule,
    run_security_scan, block_ip_address
)

class FirewallRuleViewSet(viewsets.ModelViewSet):
    queryset = FirewallRule.objects.all()
    serializer_class = FirewallRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        rule = serializer.save()
        apply_firewall_rule.delay(rule.id)

    def perform_update(self, serializer):
        rule = serializer.save()
        apply_firewall_rule.delay(rule.id)

    def perform_destroy(self, instance):
        rule_id = instance.id
        instance.delete()
        remove_firewall_rule.delay(rule_id)

class SecurityScanViewSet(viewsets.ModelViewSet):
    queryset = SecurityScan.objects.all()
    serializer_class = SecurityScanSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        scan = serializer.save(created_by=self.request.user)
        run_security_scan.delay(scan.id)

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        scan = self.get_object()
        if scan.status == 'failed':
            scan.status = 'pending'
            scan.save()
            run_security_scan.delay(scan.id)
            return Response({'status': 'scan scheduled'})
        return Response(
            {'error': 'Can only retry failed scans'},
            status=status.HTTP_400_BAD_REQUEST
        )

class SecurityIncidentViewSet(viewsets.ModelViewSet):
    queryset = SecurityIncident.objects.all()
    serializer_class = SecurityIncidentSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        incident = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        incident.assigned_to_id = user_id
        incident.save()
        return Response({'status': 'incident assigned'})

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        incident = self.get_object()
        resolution = request.data.get('resolution')
        if not resolution:
            return Response(
                {'error': 'resolution is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        incident.status = 'resolved'
        incident.resolved_at = timezone.now()
        incident.resolution = resolution
        incident.save()
        return Response({'status': 'incident resolved'})

class SSHKeyViewSet(viewsets.ModelViewSet):
    serializer_class = SSHKeySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SSHKey.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FailedLoginViewSet(viewsets.ModelViewSet):
    queryset = FailedLogin.objects.all()
    serializer_class = FailedLoginSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['post'])
    def block_ip(self, request):
        ip_address = request.data.get('ip_address')
        if not ip_address:
            return Response(
                {'error': 'ip_address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        block_ip_address.delay(ip_address)
        FailedLogin.objects.filter(source_ip=ip_address).update(blocked=True)
        return Response({'status': 'IP blocked'})

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_scan = SecurityScan.objects.order_by('-completed_at').first()
        last_incident = SecurityIncident.objects.order_by('-detected_at').first()
        
        stats = {
            'total_incidents': SecurityIncident.objects.count(),
            'open_incidents': SecurityIncident.objects.filter(status='open').count(),
            'critical_incidents': SecurityIncident.objects.filter(severity='critical').count(),
            'recent_failed_logins': FailedLogin.objects.filter(attempt_time__gte=last_24h).count(),
            'blocked_ips': FailedLogin.objects.filter(blocked=True).values('source_ip').distinct().count(),
            'active_firewall_rules': FirewallRule.objects.filter(is_active=True).count(),
            'recent_scans': SecurityScan.objects.filter(completed_at__gte=last_24h).count(),
            'vulnerabilities_found': SecurityScan.objects.filter(
                scan_type='vulnerability',
                status='completed'
            ).aggregate(total=Count('id'))['total'],
            'ssh_keys_active': SSHKey.objects.filter(is_active=True).count(),
            'last_security_scan': last_scan.completed_at if last_scan else None,
            'last_incident': last_incident.detected_at if last_incident else None,
            'average_resolution_time': SecurityIncident.objects.filter(
                resolved_at__isnull=False
            ).aggregate(avg_time=Avg('resolved_at' - 'detected_at'))['avg_time']
        }
        
        serializer = SecurityStatisticsSerializer(stats)
        return Response(serializer.data)
