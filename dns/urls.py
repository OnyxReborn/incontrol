from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'zones', views.DNSZoneViewSet)
router.register(r'records', views.DNSRecordViewSet)
router.register(r'templates', views.DNSTemplateViewSet)
router.register(r'queries', views.DNSQueryViewSet)
router.register(r'health', views.DNSHealthViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 