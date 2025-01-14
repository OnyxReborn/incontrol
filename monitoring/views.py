from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import MetricSnapshot, ServiceStatus, AlertRule, Alert
from .serializers import (
    MetricSnapshotSerializer,
    ServiceStatusSerializer,
    AlertRuleSerializer,
    AlertSerializer
)

class MetricSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MetricSnapshot.objects.all()
    serializer_class = MetricSnapshotSerializer
    filterset_fields = ['timestamp']

    @action(detail=False, methods=['get'])
    def latest(self, request):
        latest = self.get_queryset().first()
        if latest:
            serializer = self.get_serializer(latest)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)

class ServiceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServiceStatus.objects.all()
    serializer_class = ServiceStatusSerializer
    filterset_fields = ['name', 'status']

class AlertRuleViewSet(viewsets.ModelViewSet):
    queryset = AlertRule.objects.all()
    serializer_class = AlertRuleSerializer
    filterset_fields = ['metric', 'severity', 'enabled']

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        rule = self.get_object()
        rule.enabled = not rule.enabled
        rule.save()
        return Response({'enabled': rule.enabled})

class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    filterset_fields = ['rule', 'acknowledged']

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        if not alert.acknowledged:
            alert.acknowledged = True
            alert.acknowledged_at = timezone.now()
            alert.acknowledged_by = request.user
            alert.save()
        return Response({'acknowledged': True}) 