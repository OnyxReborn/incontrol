from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'services', views.ServiceViewSet)
router.register(r'packages', views.PackageViewSet)
router.register(r'backups', views.BackupViewSet)
router.register(r'cron-jobs', views.CronJobViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 