from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'processes', views.ProcessViewSet)
router.register(r'services', views.ServiceViewSet)
router.register(r'resource-usage', views.ResourceUsageViewSet)
router.register(r'limits', views.ProcessLimitViewSet)
router.register(r'alerts', views.ProcessAlertViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 