from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BackupViewSet, BackupScheduleViewSet, BackupStatsView

router = DefaultRouter()
router.register(r'backups', BackupViewSet)
router.register(r'schedules', BackupScheduleViewSet)
router.register(r'stats', BackupStatsView, basename='backup-stats')

urlpatterns = [
    path('', include(router.urls)),
] 