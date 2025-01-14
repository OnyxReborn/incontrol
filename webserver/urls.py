from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'vhosts', views.VirtualHostViewSet)
router.register(r'certificates', views.SSLCertificateViewSet)
router.register(r'proxies', views.ProxyConfigViewSet)
router.register(r'access-controls', views.AccessControlViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 