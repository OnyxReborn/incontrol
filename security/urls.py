from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'firewall', views.FirewallRuleViewSet)
router.register(r'scans', views.SecurityScanViewSet)
router.register(r'incidents', views.SecurityIncidentViewSet)
router.register(r'ssh-keys', views.SSHKeyViewSet, basename='ssh-key')
router.register(r'failed-logins', views.FailedLoginViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 