from django.shortcuts import render
from django.contrib.auth.hashers import make_password
from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils import timezone
import time
from .models import (
    EmailAccount, EmailForwarder, SpamFilter, IPBlock, ModSecurityRule, 
    ProtectedDirectory, Subdomain, DomainRedirect, DNSZone, SSLCertificate, 
    BackupConfig, BackupJob, ResourceUsage, BandwidthUsage, ErrorLog, 
    AccessLog, VirtualHost, ProxyConfig, AccessControl
)
from .serializers import (
    EmailAccountSerializer, EmailForwarderSerializer, SpamFilterSerializer, 
    IPBlockSerializer, ModSecurityRuleSerializer, ProtectedDirectorySerializer, 
    SubdomainSerializer, DomainRedirectSerializer, DNSZoneSerializer, 
    SSLCertificateSerializer, BackupConfigSerializer, BackupJobSerializer, 
    ResourceUsageSerializer, BandwidthUsageSerializer, ErrorLogSerializer, 
    AccessLogSerializer, VirtualHostSerializer, ProxyConfigSerializer,
    AccessControlSerializer
)
from .tasks import check_ssl_certificates, renew_lets_encrypt_certificate, create_backup, restore_backup
import subprocess
import os
from django.db import connection
from django.http import JsonResponse, FileResponse
from rest_framework.decorators import action, api_view, permission_classes
import zipfile
import tarfile
import shutil
from datetime import datetime
import ssl
import OpenSSL
from rest_framework.response import Response
from rest_framework import status

# Create your views here.

class VirtualHostViewSet(viewsets.ModelViewSet):
    queryset = VirtualHost.objects.all()
    serializer_class = VirtualHostSerializer
    permission_classes = [permissions.IsAuthenticated]

class SSLCertificateViewSet(viewsets.ModelViewSet):
    queryset = SSLCertificate.objects.all()
    serializer_class = SSLCertificateSerializer
    permission_classes = [permissions.IsAuthenticated]

class ProxyConfigViewSet(viewsets.ModelViewSet):
    queryset = ProxyConfig.objects.all()
    serializer_class = ProxyConfigSerializer
    permission_classes = [permissions.IsAuthenticated]

class AccessControlViewSet(viewsets.ModelViewSet):
    queryset = AccessControl.objects.all()
    serializer_class = AccessControlSerializer
    permission_classes = [permissions.IsAuthenticated]

class EmailAccountViewSet(viewsets.ModelViewSet):
    queryset = EmailAccount.objects.all()
    serializer_class = EmailAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        password = self.request.data.get('password')
        if password:
            instance.password = make_password(password)
        serializer.save()

class EmailForwarderViewSet(viewsets.ModelViewSet):
    queryset = EmailForwarder.objects.all()
    serializer_class = EmailForwarderSerializer
    permission_classes = [permissions.IsAuthenticated]

class SpamFilterViewSet(viewsets.ModelViewSet):
    queryset = SpamFilter.objects.all()
    serializer_class = SpamFilterSerializer
    permission_classes = [permissions.IsAuthenticated]

class FileViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        return Response({'status': 'success'})

    def create(self, request):
        return Response({'status': 'success'})

    def retrieve(self, request, pk=None):
        return Response({'status': 'success'})

    def update(self, request, pk=None):
        return Response({'status': 'success'})

    def destroy(self, request, pk=None):
        return Response({'status': 'success'})

    def create_folder(self, request):
        path = request.data.get('path', '/')
        name = request.data.get('name')
        
        if not name:
            return Response({'error': 'Name is required'}, status=400)
        
        full_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'), name)
        
        try:
            os.makedirs(full_path)
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def upload(self, request):
        path = request.data.get('path', '/')
        files = request.FILES.getlist('files')
        
        if not files:
            return Response({'error': 'No files provided'}, status=400)
        
        full_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'))
        
        try:
            for file in files:
                with open(os.path.join(full_path, file.name), 'wb+') as destination:
                    for chunk in file.chunks():
                        destination.write(chunk)
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def download(self, request):
        path = request.query_params.get('path')
        
        if not path:
            return Response({'error': 'Path is required'}, status=400)
        
        full_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'))
        
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return Response({'error': 'File not found'}, status=404)
        
        try:
            return FileResponse(open(full_path, 'rb'))
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class IPBlockViewSet(viewsets.ModelViewSet):
    queryset = IPBlock.objects.all()
    serializer_class = IPBlockSerializer
    permission_classes = [permissions.IsAuthenticated]

class ModSecurityRuleViewSet(viewsets.ModelViewSet):
    queryset = ModSecurityRule.objects.all()
    serializer_class = ModSecurityRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

class ProtectedDirectoryViewSet(viewsets.ModelViewSet):
    queryset = ProtectedDirectory.objects.all()
    serializer_class = ProtectedDirectorySerializer
    permission_classes = [permissions.IsAuthenticated]

class SubdomainViewSet(viewsets.ModelViewSet):
    queryset = Subdomain.objects.all()
    serializer_class = SubdomainSerializer
    permission_classes = [permissions.IsAuthenticated]

class DomainRedirectViewSet(viewsets.ModelViewSet):
    queryset = DomainRedirect.objects.all()
    serializer_class = DomainRedirectSerializer
    permission_classes = [permissions.IsAuthenticated]

class DNSZoneViewSet(viewsets.ModelViewSet):
    queryset = DNSZone.objects.all()
    serializer_class = DNSZoneSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _update_bind_config(self):
        # Group records by domain
        domains = {}
        for record in DNSZone.objects.filter(enabled=True):
            if record.domain.name not in domains:
                domains[record.domain.name] = []
            domains[record.domain.name].append(record)

        # Update zone files for each domain
        for domain_name, records in domains.items():
            zone_path = f'/etc/bind/zones/db.{domain_name}'
            os.makedirs(os.path.dirname(zone_path), exist_ok=True)

            config_lines = [
                f'$TTL 86400',
                f'@    IN    SOA    ns1.{domain_name}. admin.{domain_name}. (',
                f'                  {int(time.time())}    ; Serial',
                f'                  3600       ; Refresh',
                f'                  1800       ; Retry',
                f'                  604800     ; Expire',
                f'                  86400 )    ; Minimum TTL',
                f'',
                f'@    IN    NS     ns1.{domain_name}.',
                f'@    IN    NS     ns2.{domain_name}.',
                f''
            ]

            for record in records:
                if record.record_type == 'MX':
                    config_lines.append(f'{record.name}    IN    {record.record_type}    {record.priority}    {record.content}')
                else:
                    config_lines.append(f'{record.name}    IN    {record.record_type}    {record.content}')

            with open(zone_path, 'w') as f:
                f.write('\n'.join(config_lines))

        # Reload BIND
        subprocess.run(['rndc', 'reload'], check=True)

class AccessLogViewSet(viewsets.ModelViewSet):
    queryset = AccessLog.objects.all()
    serializer_class = AccessLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def tail(self, request):
        """Get the latest access logs"""
        lines = int(request.query_params.get('lines', 100))
        domain_id = request.query_params.get('domain')
        status_code = request.query_params.get('status_code')

        queryset = self.get_queryset()
        if domain_id:
            queryset = queryset.filter(domain_id=domain_id)
        if status_code:
            queryset = queryset.filter(status_code=status_code)

        logs = queryset[:lines]
        return Response(AccessLogSerializer(logs, many=True).data)

    @action(detail=False, methods=['post'])
    def parse_logs(self, request):
        """Parse access logs from files"""
        import re
        from datetime import datetime
        from django.utils import timezone

        # Parse Nginx access logs
        nginx_pattern = r'(\d+\.\d+\.\d+\.\d+) .+ \[(.+)\] "(\w+) (.+) HTTP/\d\.\d" (\d+) (\d+) "([^"]*)" "([^"]*)" (\d+\.\d+)'
        with open('/var/log/nginx/access.log', 'r') as f:
            for line in f:
                match = re.match(nginx_pattern, line)
                if match:
                    timestamp = datetime.strptime(match.group(2), '%d/%b/%Y:%H:%M:%S %z')
                    path = match.group(4)
                    domain = None

                    # Try to find matching domain
                    for vh in VirtualHost.objects.all():
                        if any(domain in path for domain in vh.domains.split('\n')):
                            domain = vh
                            break

                    if domain:
                        AccessLog.objects.create(
                            timestamp=timestamp,
                            domain=domain,
                            ip_address=match.group(1),
                            method=match.group(3),
                            path=path,
                            status_code=int(match.group(5)),
                            response_size=int(match.group(6)),
                            referer=match.group(7),
                            user_agent=match.group(8),
                            response_time=float(match.group(9))
                        )

        return Response({'status': 'Logs parsed successfully'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ssl_info(request):
    try:
        # Your SSL info logic here
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_nginx_status(request):
    try:
        # Your Nginx status logic here
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
