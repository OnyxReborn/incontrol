from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'services', views.ServiceViewSet, basename='service')
router.register(r'packages', views.PackageViewSet, basename='package')
router.register(r'backups', views.BackupViewSet, basename='backup')
router.register(r'cron-jobs', views.CronJobViewSet, basename='cronjob')

urlpatterns = [
    path('', include(router.urls)),
] 