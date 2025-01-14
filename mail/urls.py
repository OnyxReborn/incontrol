from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'domains', views.MailDomainViewSet)
router.register(r'accounts', views.MailAccountViewSet)
router.register(r'aliases', views.MailAliasViewSet)
router.register(r'spam-filters', views.SpamFilterViewSet)
router.register(r'queue', views.MailQueueViewSet)
router.register(r'logs', views.MailLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 