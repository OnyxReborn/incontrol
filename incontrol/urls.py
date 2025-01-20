"""
URL configuration for incontrol project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/core/', include('core.urls')),
    # path('api/monitoring/', include('monitoring.urls')),
    # path('api/accounts/', include('accounts.urls')),
    # path('api/system/', include('system.urls')),
    # path('api/webserver/', include('webserver.urls')),
    # path('api/database/', include('database.urls')),
    # path('api/mail/', include('mail.urls')),
    # path('api/security/', include('security.urls')),
    # path('api/backup/', include('backup.urls')),
    # path('api/dns/', include('dns.urls')),
    # path('api/filemanager/', include('filemanager.urls')),
    # path('api/processmanager/', include('processmanager.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
