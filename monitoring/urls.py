from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'metrics', views.MetricSnapshotViewSet)
router.register(r'services', views.ServiceStatusViewSet)
router.register(r'alert-rules', views.AlertRuleViewSet)
router.register(r'alerts', views.AlertViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 