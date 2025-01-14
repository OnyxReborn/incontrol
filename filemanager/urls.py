from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'directories', views.DirectoryViewSet)
router.register(r'files', views.FileViewSet)
router.register(r'shares', views.FileShareViewSet)
router.register(r'operations', views.FileOperationViewSet)
router.register(r'backups', views.FileBackupViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 