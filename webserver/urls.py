from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'vhosts', views.VirtualHostViewSet)
router.register(r'certificates', views.SSLCertificateViewSet)
router.register(r'proxies', views.ProxyConfigViewSet)
router.register(r'access-controls', views.AccessControlViewSet)
router.register(r'email/accounts', views.EmailAccountViewSet)
router.register(r'email/forwarders', views.EmailForwarderViewSet)
router.register(r'email/spam-filters', views.SpamFilterViewSet)
router.register(r'databases', views.DatabaseViewSet)
router.register(r'database-users', views.DatabaseUserViewSet)
router.register(r'database-backups', views.DatabaseBackupViewSet)
router.register(r'files', views.FileViewSet, basename='files')
router.register(r'security/ip-blocks', views.IPBlockViewSet)
router.register(r'security/modsecurity-rules', views.ModSecurityRuleViewSet)
router.register(r'security/protected-directories', views.ProtectedDirectoryViewSet)
router.register(r'subdomains', views.SubdomainViewSet)
router.register(r'domain-redirects', views.DomainRedirectViewSet)
router.register(r'dns-zones', views.DNSZoneViewSet)
router.register(r'ssl-certificates', views.SSLCertificateViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 