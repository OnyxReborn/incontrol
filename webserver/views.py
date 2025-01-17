from django.shortcuts import render
from django.contrib.auth.hashers import make_password
from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils import timezone
import time
from .models import (
    EmailAccount, EmailForwarder, SpamFilter, Database, DatabaseUser, 
    DatabaseBackup, IPBlock, ModSecurityRule, ProtectedDirectory, 
    Subdomain, DomainRedirect, DNSZone, SSLCertificate, BackupConfig, 
    BackupJob, CrontabSchedule, PeriodicTask, ResourceUsage, 
    BandwidthUsage, ErrorLog, AccessLog, VirtualHost
)
from .serializers import (
    EmailAccountSerializer, EmailForwarderSerializer, SpamFilterSerializer, 
    DatabaseSerializer, DatabaseUserSerializer, DatabaseBackupSerializer, 
    IPBlockSerializer, ModSecurityRuleSerializer, ProtectedDirectorySerializer, 
    SubdomainSerializer, DomainRedirectSerializer, DNSZoneSerializer, 
    SSLCertificateSerializer, BackupConfigSerializer, BackupJobSerializer, 
    ResourceUsageSerializer, BandwidthUsageSerializer, ErrorLogSerializer, 
    AccessLogSerializer
)
from .tasks import create_backup, restore_backup
import subprocess
import os
from django.db import connection
from django.http import Response
from rest_framework.decorators import action
import zipfile
import tarfile
import shutil
from datetime import datetime
from django.http import FileResponse
import ssl
import OpenSSL

# Create your views here.

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

class DatabaseViewSet(viewsets.ModelViewSet):
    queryset = Database.objects.all()
    serializer_class = DatabaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def backup(self, request, pk=None):
        database = self.get_object()
        backup_path = f"/var/lib/mysql/backups/{database.name}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.sql"
        
        try:
            # Create backup using mysqldump
            subprocess.run([
                'mysqldump',
                '-u', settings.DATABASES['default']['USER'],
                f"-p{settings.DATABASES['default']['PASSWORD']}",
                database.name,
                f"--result-file={backup_path}"
            ], check=True)

            # Get backup size
            size = os.path.getsize(backup_path)

            # Create backup record
            backup = DatabaseBackup.objects.create(
                database=database,
                file_path=backup_path,
                size=size
            )

            return Response(DatabaseBackupSerializer(backup).data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class DatabaseUserViewSet(viewsets.ModelViewSet):
    queryset = DatabaseUser.objects.all()
    serializer_class = DatabaseUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        
        # Create MySQL user and grant privileges
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE USER '{instance.username}'@'{instance.host}' IDENTIFIED BY '{instance.password}'")
            
            for database in instance.databases.all():
                cursor.execute(f"GRANT ALL PRIVILEGES ON {database.name}.* TO '{instance.username}'@'{instance.host}'")
            
            cursor.execute("FLUSH PRIVILEGES")

    def perform_update(self, serializer):
        old_instance = self.get_object()
        instance = serializer.save()
        
        # Update MySQL user privileges
        with connection.cursor() as cursor:
            # Revoke all existing privileges
            cursor.execute(f"REVOKE ALL PRIVILEGES ON *.* FROM '{old_instance.username}'@'{old_instance.host}'")
            
            # Grant new privileges
            for database in instance.databases.all():
                cursor.execute(f"GRANT ALL PRIVILEGES ON {database.name}.* TO '{instance.username}'@'{instance.host}'")
            
            cursor.execute("FLUSH PRIVILEGES")

    def perform_destroy(self, instance):
        # Drop MySQL user
        with connection.cursor() as cursor:
            cursor.execute(f"DROP USER '{instance.username}'@'{instance.host}'")
            cursor.execute("FLUSH PRIVILEGES")
        
        instance.delete()

class DatabaseBackupViewSet(viewsets.ModelViewSet):
    queryset = DatabaseBackup.objects.all()
    serializer_class = DatabaseBackupSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        backup = self.get_object()
        
        try:
            # Restore backup using mysql
            subprocess.run([
                'mysql',
                '-u', settings.DATABASES['default']['USER'],
                f"-p{settings.DATABASES['default']['PASSWORD']}",
                backup.database.name,
                '<', backup.file_path
            ], check=True, shell=True)

            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    def perform_destroy(self, instance):
        # Delete backup file
        if os.path.exists(instance.file_path):
            os.remove(instance.file_path)
        instance.delete()

class FileViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        path = request.query_params.get('path', '/')
        full_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'))
        
        if not os.path.exists(full_path):
            return Response({'error': 'Path does not exist'}, status=404)
        
        files = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            stat = os.stat(item_path)
            files.append({
                'name': item,
                'type': 'directory' if os.path.isdir(item_path) else 'file',
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'permissions': oct(stat.st_mode)[-3:]
            })
        
        return Response(files)

    @action(detail=False, methods=['post'])
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

    @action(detail=False, methods=['post'])
    def delete(self, request):
        items = request.data.get('items', [])
        
        if not items:
            return Response({'error': 'No items provided'}, status=400)
        
        try:
            for item in items:
                full_path = os.path.join(settings.MEDIA_ROOT, item.lstrip('/'))
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def paste(self, request):
        items = request.data.get('items', [])
        destination = request.data.get('destination', '/')
        action = request.data.get('action')
        
        if not items or not action:
            return Response({'error': 'Items and action are required'}, status=400)
        
        try:
            dest_path = os.path.join(settings.MEDIA_ROOT, destination.lstrip('/'))
            
            for item in items:
                src_path = os.path.join(settings.MEDIA_ROOT, item.lstrip('/'))
                filename = os.path.basename(src_path)
                dest_file = os.path.join(dest_path, filename)
                
                if action == 'copy':
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dest_file)
                    else:
                        shutil.copy2(src_path, dest_file)
                elif action == 'cut':
                    shutil.move(src_path, dest_file)
            
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def compress(self, request):
        items = request.data.get('items', [])
        destination = request.data.get('destination', '/')
        
        if not items:
            return Response({'error': 'Items are required'}, status=400)
        
        try:
            dest_path = os.path.join(settings.MEDIA_ROOT, destination.lstrip('/'))
            archive_name = os.path.join(dest_path, 'archive.zip')
            
            with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for item in items:
                    full_path = os.path.join(settings.MEDIA_ROOT, item.lstrip('/'))
                    if os.path.isdir(full_path):
                        for root, dirs, files in os.walk(full_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, settings.MEDIA_ROOT)
                                zipf.write(file_path, arcname)
                    else:
                        arcname = os.path.relpath(full_path, settings.MEDIA_ROOT)
                        zipf.write(full_path, arcname)
            
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def extract(self, request):
        path = request.data.get('path')
        destination = request.data.get('destination', '/')
        
        if not path:
            return Response({'error': 'Path is required'}, status=400)
        
        try:
            src_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'))
            dest_path = os.path.join(settings.MEDIA_ROOT, destination.lstrip('/'))
            
            if path.endswith('.zip'):
                with zipfile.ZipFile(src_path, 'r') as zipf:
                    zipf.extractall(dest_path)
            elif path.endswith(('.tar', '.tar.gz', '.tgz')):
                with tarfile.open(src_path, 'r:*') as tarf:
                    tarf.extractall(dest_path)
            else:
                return Response({'error': 'Unsupported archive format'}, status=400)
            
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def chmod(self, request):
        path = request.data.get('path')
        permissions = request.data.get('permissions')
        
        if not path or not permissions:
            return Response({'error': 'Path and permissions are required'}, status=400)
        
        try:
            full_path = os.path.join(settings.MEDIA_ROOT, path.lstrip('/'))
            mode = 0
            
            # Convert permissions dict to octal mode
            for role in ['owner', 'group', 'others']:
                role_perms = permissions[role]
                mode = (mode << 3) | (
                    (1 if role_perms['read'] else 0) << 2 |
                    (1 if role_perms['write'] else 0) << 1 |
                    (1 if role_perms['execute'] else 0)
                )
            
            os.chmod(full_path, mode)
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def rename(self, request):
        old_path = request.data.get('oldPath')
        new_path = request.data.get('newPath')
        
        if not old_path or not new_path:
            return Response({'error': 'Old path and new path are required'}, status=400)
        
        try:
            old_full_path = os.path.join(settings.MEDIA_ROOT, old_path.lstrip('/'))
            new_full_path = os.path.join(settings.MEDIA_ROOT, new_path.lstrip('/'))
            
            os.rename(old_full_path, new_full_path)
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class IPBlockViewSet(viewsets.ModelViewSet):
    queryset = IPBlock.objects.all()
    serializer_class = IPBlockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_nginx_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_nginx_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_nginx_config()

    def _update_nginx_config(self):
        # Generate Nginx config for IP blocks
        config_lines = []
        for block in IPBlock.objects.filter(enabled=True):
            config_lines.append(f"{block.rule_type} {block.ip_address};")

        # Write to Nginx config file
        config_path = '/etc/nginx/conf.d/ip_blocks.conf'
        with open(config_path, 'w') as f:
            f.write('\n'.join(config_lines))

        # Reload Nginx
        subprocess.run(['nginx', '-s', 'reload'], check=True)

class ModSecurityRuleViewSet(viewsets.ModelViewSet):
    queryset = ModSecurityRule.objects.all()
    serializer_class = ModSecurityRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_modsecurity_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_modsecurity_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_modsecurity_config()

    def _update_modsecurity_config(self):
        # Generate ModSecurity config
        config_lines = []
        for rule in ModSecurityRule.objects.filter(enabled=True):
            config_lines.append(f"# {rule.description}")
            config_lines.append(f"SecRule {rule.rule_content}")
            config_lines.append("")

        # Write to ModSecurity config file
        config_path = '/etc/nginx/modsecurity/rules.conf'
        with open(config_path, 'w') as f:
            f.write('\n'.join(config_lines))

        # Reload Nginx
        subprocess.run(['nginx', '-s', 'reload'], check=True)

class ProtectedDirectoryViewSet(viewsets.ModelViewSet):
    queryset = ProtectedDirectory.objects.all()
    serializer_class = ProtectedDirectorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_htpasswd(instance)
        self._update_nginx_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        if 'password' in self.request.data:
            self._update_htpasswd(instance)
        self._update_nginx_config()

    def perform_destroy(self, instance):
        self._remove_htpasswd(instance)
        instance.delete()
        self._update_nginx_config()

    def _update_htpasswd(self, instance):
        # Create .htpasswd file for the directory
        htpasswd_dir = '/etc/nginx/htpasswd'
        os.makedirs(htpasswd_dir, exist_ok=True)
        htpasswd_file = os.path.join(htpasswd_dir, f"{instance.id}.htpasswd")
        
        subprocess.run([
            'htpasswd',
            '-cb',  # Create and use bcrypt
            htpasswd_file,
            instance.username,
            instance.password
        ], check=True)

    def _remove_htpasswd(self, instance):
        htpasswd_file = f'/etc/nginx/htpasswd/{instance.id}.htpasswd'
        if os.path.exists(htpasswd_file):
            os.remove(htpasswd_file)

    def _update_nginx_config(self):
        # Generate Nginx config for protected directories
        config_lines = []
        for protected in ProtectedDirectory.objects.filter(enabled=True):
            config_lines.extend([
                f"location {protected.path} {{",
                "    auth_basic \"Restricted Area\";",
                f"    auth_basic_user_file /etc/nginx/htpasswd/{protected.id}.htpasswd;",
                "    try_files $uri $uri/ =404;",
                "}",
                ""
            ])

        # Write to Nginx config file
        config_path = '/etc/nginx/conf.d/protected_dirs.conf'
        with open(config_path, 'w') as f:
            f.write('\n'.join(config_lines))

        # Reload Nginx
        subprocess.run(['nginx', '-s', 'reload'], check=True)

class SubdomainViewSet(viewsets.ModelViewSet):
    queryset = Subdomain.objects.all()
    serializer_class = SubdomainSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_nginx_config(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_nginx_config(instance)

    def perform_destroy(self, instance):
        self._remove_nginx_config(instance)
        instance.delete()

    def _update_nginx_config(self, instance):
        config_path = f'/etc/nginx/sites-available/subdomain_{instance.id}.conf'
        config_lines = [
            f'server {{',
            f'    listen 80;',
            f'    server_name {instance.name}.{instance.domain.name};',
            f'    root {instance.document_root};',
            f'    index index.html index.htm;',
            f'    location / {{',
            f'        try_files $uri $uri/ =404;',
            f'    }}',
            f'}}'
        ]
        
        with open(config_path, 'w') as f:
            f.write('\n'.join(config_lines))

        enabled_path = f'/etc/nginx/sites-enabled/subdomain_{instance.id}.conf'
        if instance.enabled:
            if not os.path.exists(enabled_path):
                os.symlink(config_path, enabled_path)
        else:
            if os.path.exists(enabled_path):
                os.unlink(enabled_path)

        subprocess.run(['nginx', '-s', 'reload'], check=True)

    def _remove_nginx_config(self, instance):
        config_path = f'/etc/nginx/sites-available/subdomain_{instance.id}.conf'
        enabled_path = f'/etc/nginx/sites-enabled/subdomain_{instance.id}.conf'
        
        if os.path.exists(enabled_path):
            os.unlink(enabled_path)
        if os.path.exists(config_path):
            os.unlink(config_path)

        subprocess.run(['nginx', '-s', 'reload'], check=True)

class DomainRedirectViewSet(viewsets.ModelViewSet):
    queryset = DomainRedirect.objects.all()
    serializer_class = DomainRedirectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_nginx_config(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_nginx_config(instance)

    def perform_destroy(self, instance):
        self._remove_nginx_config(instance)
        instance.delete()

    def _update_nginx_config(self, instance):
        config_path = f'/etc/nginx/sites-available/redirect_{instance.id}.conf'
        config_lines = [
            f'server {{',
            f'    listen 80;',
            f'    server_name {instance.source_domain};',
            f'    return {instance.redirect_type} {"$scheme://" + instance.target_domain + "$request_uri" if instance.preserve_path else instance.target_domain};',
            f'}}'
        ]
        
        with open(config_path, 'w') as f:
            f.write('\n'.join(config_lines))

        enabled_path = f'/etc/nginx/sites-enabled/redirect_{instance.id}.conf'
        if instance.enabled:
            if not os.path.exists(enabled_path):
                os.symlink(config_path, enabled_path)
        else:
            if os.path.exists(enabled_path):
                os.unlink(enabled_path)

        subprocess.run(['nginx', '-s', 'reload'], check=True)

    def _remove_nginx_config(self, instance):
        config_path = f'/etc/nginx/sites-available/redirect_{instance.id}.conf'
        enabled_path = f'/etc/nginx/sites-enabled/redirect_{instance.id}.conf'
        
        if os.path.exists(enabled_path):
            os.unlink(enabled_path)
        if os.path.exists(config_path):
            os.unlink(config_path)

        subprocess.run(['nginx', '-s', 'reload'], check=True)

class DNSZoneViewSet(viewsets.ModelViewSet):
    queryset = DNSZone.objects.all()
    serializer_class = DNSZoneSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_bind_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_bind_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_bind_config()

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

class SSLCertificateViewSet(viewsets.ModelViewSet):
    queryset = SSLCertificate.objects.all()
    serializer_class = SSLCertificateSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        certificate = self.get_object()
        try:
            # Run certbot renew for the specific certificate
            domains = [d.strip() for d in certificate.domains.split('\n') if d.strip()]
            domain_args = sum([['--domain', d] for d in domains], [])
            
            subprocess.run([
                'certbot', 'certonly', '--nginx',
                '--non-interactive', '--agree-tos',
                '--email', 'admin@example.com',
                *domain_args
            ], check=True)

            # Update certificate information
            cert_path = f'/etc/letsencrypt/live/{domains[0]}/cert.pem'
            cert_data = ssl.get_server_certificate((domains[0], 443))
            x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert_data)
            
            certificate.valid_from = datetime.strptime(x509.get_notBefore().decode(), '%Y%m%d%H%M%SZ')
            certificate.valid_until = datetime.strptime(x509.get_notAfter().decode(), '%Y%m%d%H%M%SZ')
            certificate.save()

            return Response({'status': 'Certificate renewed successfully'})
        except subprocess.CalledProcessError as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['post'])
    def request_new(self, request):
        domains = request.data.get('domains', '').split('\n')
        domains = [d.strip() for d in domains if d.strip()]
        
        if not domains:
            return Response({'error': 'No domains provided'}, status=400)

        try:
            # Request new certificate using certbot
            domain_args = sum([['--domain', d] for d in domains], [])
            subprocess.run([
                'certbot', 'certonly', '--nginx',
                '--non-interactive', '--agree-tos',
                '--email', 'admin@example.com',
                *domain_args
            ], check=True)

            # Create new certificate record
            cert_path = f'/etc/letsencrypt/live/{domains[0]}'
            cert_data = ssl.get_server_certificate((domains[0], 443))
            x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert_data)

            certificate = SSLCertificate.objects.create(
                name=f'Certificate for {domains[0]}',
                domains='\n'.join(domains),
                key_file=f'{cert_path}/privkey.pem',
                cert_file=f'{cert_path}/cert.pem',
                chain_file=f'{cert_path}/chain.pem',
                issuer=x509.get_issuer().commonName,
                valid_from=datetime.strptime(x509.get_notBefore().decode(), '%Y%m%d%H%M%SZ'),
                valid_until=datetime.strptime(x509.get_notAfter().decode(), '%Y%m%d%H%M%SZ'),
                auto_renew=True
            )

            return Response(SSLCertificateSerializer(certificate).data)
        except subprocess.CalledProcessError as e:
            return Response({'error': str(e)}, status=400)

class BackupConfigViewSet(viewsets.ModelViewSet):
    queryset = BackupConfig.objects.all()
    serializer_class = BackupConfigSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        config = serializer.save()
        if config.schedule:
            # Add to celery beat schedule
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=config.schedule.split()[0],
                hour=config.schedule.split()[1],
                day_of_week=config.schedule.split()[4],
                day_of_month=config.schedule.split()[2],
                month_of_year=config.schedule.split()[3]
            )
            PeriodicTask.objects.create(
                name=f'backup-{config.id}',
                task='webserver.tasks.create_backup',
                crontab=schedule,
                args=[config.id]
            )

    def perform_destroy(self, instance):
        # Remove from celery beat schedule
        PeriodicTask.objects.filter(name=f'backup-{instance.id}').delete()
        instance.delete()

class BackupJobViewSet(viewsets.ModelViewSet):
    queryset = BackupJob.objects.all().order_by('-started_at')
    serializer_class = BackupJobSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def create_backup(self, request):
        config_id = request.data.get('config_id')
        try:
            config = BackupConfig.objects.get(id=config_id)
            job = BackupJob.objects.create(
                config=config,
                status='pending',
                file_path=f"{config.backup_path}/{timezone.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
            )
            create_backup.delay(job.id)
            return Response({'status': 'Backup job created', 'job_id': job.id})
        except BackupConfig.DoesNotExist:
            return Response({'error': 'Backup configuration not found'}, status=404)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        job = self.get_object()
        if job.status != 'completed':
            return Response({'error': 'Can only restore from completed backups'}, status=400)
        
        restore_backup.delay(job.id)
        return Response({'status': 'Restore job initiated'})

class ResourceUsageViewSet(viewsets.ModelViewSet):
    queryset = ResourceUsage.objects.all()
    serializer_class = ResourceUsageSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current resource usage"""
        import psutil
        
        # Get CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_usage = disk.percent
        
        # Get disk I/O
        disk_io = psutil.disk_io_counters()
        disk_read = disk_io.read_bytes
        disk_write = disk_io.write_bytes
        
        # Get network I/O
        net_io = psutil.net_io_counters()
        network_rx = net_io.bytes_recv
        network_tx = net_io.bytes_sent
        
        # Get load average
        load_avg = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
        
        usage = ResourceUsage.objects.create(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage,
            disk_read=disk_read,
            disk_write=disk_write,
            network_rx=network_rx,
            network_tx=network_tx,
            load_average=','.join(map(str, load_avg))
        )
        
        return Response(ResourceUsageSerializer(usage).data)

class BandwidthUsageViewSet(viewsets.ModelViewSet):
    queryset = BandwidthUsage.objects.all()
    serializer_class = BandwidthUsageSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def by_domain(self, request):
        """Get bandwidth usage grouped by domain"""
        from django.db.models import Sum
        from django.utils import timezone
        from datetime import timedelta

        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        usage = BandwidthUsage.objects.filter(
            timestamp__gte=start_date
        ).values(
            'domain', 'domain__name'
        ).annotate(
            total_in=Sum('bytes_in'),
            total_out=Sum('bytes_out'),
            total_requests=Sum('requests')
        )

        return Response(usage)

class ErrorLogViewSet(viewsets.ModelViewSet):
    queryset = ErrorLog.objects.all()
    serializer_class = ErrorLogSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def tail(self, request):
        """Get the latest error logs"""
        lines = int(request.query_params.get('lines', 100))
        source = request.query_params.get('source')
        level = request.query_params.get('level')

        queryset = self.get_queryset()
        if source:
            queryset = queryset.filter(source=source)
        if level:
            queryset = queryset.filter(level=level)

        logs = queryset[:lines]
        return Response(ErrorLogSerializer(logs, many=True).data)

    @action(detail=False, methods=['post'])
    def parse_logs(self, request):
        """Parse error logs from files"""
        import re
        from datetime import datetime

        # Parse Nginx error logs
        nginx_pattern = r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (\d+)#\d+: \*\d+ (.+)'
        with open('/var/log/nginx/error.log', 'r') as f:
            for line in f:
                match = re.match(nginx_pattern, line)
                if match:
                    timestamp = datetime.strptime(match.group(1), '%Y/%m/%d %H:%M:%S')
                    ErrorLog.objects.create(
                        timestamp=timestamp,
                        level=match.group(2).lower(),
                        source='nginx',
                        message=match.group(4),
                        file_path='/var/log/nginx/error.log'
                    )

        # Parse PHP error logs
        php_pattern = r'\[(\d{2}-\w{3}-\d{4} \d{2}:\d{2}:\d{2})\] PHP (\w+): (.+) in (.+) on line (\d+)'
        with open('/var/log/php/error.log', 'r') as f:
            for line in f:
                match = re.match(php_pattern, line)
                if match:
                    timestamp = datetime.strptime(match.group(1), '%d-%b-%Y %H:%M:%S')
                    ErrorLog.objects.create(
                        timestamp=timestamp,
                        level=match.group(2).lower(),
                        source='php',
                        message=match.group(3),
                        file_path=match.group(4),
                        line_number=int(match.group(5))
                    )

        return Response({'status': 'Logs parsed successfully'})

class AccessLogViewSet(viewsets.ModelViewSet):
    queryset = AccessLog.objects.all()
    serializer_class = AccessLogSerializer
    permission_classes = [IsAuthenticated]

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
