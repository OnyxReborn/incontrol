from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.MonitoringViewSet, basename='monitoring')
router.register(r'services', views.ServiceStatusViewSet)
router.register(r'alerts', views.AlertViewSet)
router.register(r'alert-rules', views.AlertRuleViewSet)
router.register(r'network-interfaces', views.NetworkInterfaceViewSet)
router.register(r'disk-partitions', views.DiskPartitionViewSet)
router.register(r'processes', views.ProcessViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 