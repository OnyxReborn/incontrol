from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'metrics', views.MetricSnapshotViewSet)
router.register(r'services', views.ServiceStatusViewSet)
router.register(r'alerts', views.AlertViewSet)
router.register(r'alert-rules', views.AlertRuleViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('processes/', views.ProcessListView.as_view(), name='process-list'),
    path('processes/<int:pid>/<str:action>/', views.ProcessActionView.as_view(), name='process-action'),
    path('metrics/history/<str:type>/', views.MetricHistoryView.as_view(), name='metric-history'),
] 