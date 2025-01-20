from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'databases', views.DatabaseViewSet)
router.register(r'users', views.DatabaseUserViewSet)
router.register(r'backups', views.DatabaseBackupViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 