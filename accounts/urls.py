from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'profiles', views.UserProfileViewSet)
router.register(r'groups', views.UserGroupViewSet)
router.register(r'access-keys', views.AccessKeyViewSet, basename='access-key')

urlpatterns = [
    path('', include(router.urls)),
] 