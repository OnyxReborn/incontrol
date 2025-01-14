from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'files', views.LogFileViewSet)
router.register(r'entries', views.LogEntryViewSet)
router.register(r'alerts', views.LogAlertViewSet)
router.register(r'rotation-policies', views.LogRotationPolicyViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 