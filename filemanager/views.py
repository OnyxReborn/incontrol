import os
import shutil
import hashlib
import mimetypes
import uuid
from datetime import datetime
from django.utils import timezone
from django.db.models import Sum, Count
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Directory, File, FileShare, FileOperation, FileBackup
from .serializers import (
    DirectorySerializer, FileSerializer, FileShareSerializer,
    FileOperationSerializer, FileBackupSerializer, FileStatisticsSerializer
)
from .tasks import process_file_operation, create_directory_backup

class DirectoryViewSet(viewsets.ModelViewSet):
    queryset = Directory.objects.all()
    serializer_class = DirectorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Directory.objects.all()
        path = self.request.query_params.get('path', None)
        if path is not None:
            queryset = queryset.filter(path__startswith=path)
        return queryset

    @action(detail=True, methods=['post'])
    def scan(self, request, pk=None):
        """Scan directory for changes"""
        directory = self.get_object()
        try:
            total_size = 0
            files_count = 0
            dirs_count = 0

            for root, dirs, files in os.walk(directory.path):
                dirs_count += len(dirs)
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        stat = os.stat(file_path)
                        total_size += stat.st_size
                        files_count += 1
                    except OSError:
                        continue

            directory.size = total_size
            directory.files_count = files_count
            directory.dirs_count = dirs_count
            directory.last_scanned = timezone.now()
            directory.save()

            return Response({
                'size': total_size,
                'files_count': files_count,
                'dirs_count': dirs_count
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = File.objects.all()
        directory_id = self.request.query_params.get('directory', None)
        if directory_id is not None:
            queryset = queryset.filter(directory_id=directory_id)
        return queryset

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download file"""
        file = self.get_object()
        try:
            file_path = os.path.join(file.path, file.name)
            if os.path.exists(file_path):
                response = FileResponse(
                    open(file_path, 'rb'),
                    content_type=file.mime_type
                )
                response['Content-Disposition'] = f'attachment; filename="{file.name}"'
                file.last_accessed = timezone.now()
                file.save()
                return response
            raise Http404
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def calculate_hash(self, request, pk=None):
        """Calculate MD5 hash of file"""
        file = self.get_object()
        try:
            file_path = os.path.join(file.path, file.name)
            md5_hash = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5_hash.update(chunk)
            file.md5_hash = md5_hash.hexdigest()
            file.save()
            return Response({'md5_hash': file.md5_hash})
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class FileShareViewSet(viewsets.ModelViewSet):
    queryset = FileShare.objects.all()
    serializer_class = FileShareSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        token = uuid.uuid4().hex
        serializer.save(created_by=self.request.user, token=token)

    @action(detail=True, methods=['post'])
    def validate_access(self, request, pk=None):
        """Validate access to shared file"""
        share = self.get_object()
        password = request.data.get('password')
        email = request.data.get('email')

        if share.expires_at and share.expires_at < timezone.now():
            return Response(
                {'error': 'Share link has expired'},
                status=status.HTTP_403_FORBIDDEN
            )

        if share.max_downloads and share.download_count >= share.max_downloads:
            return Response(
                {'error': 'Maximum downloads reached'},
                status=status.HTTP_403_FORBIDDEN
            )

        if share.share_type == 'password' and not share.password_hash == password:
            return Response(
                {'error': 'Invalid password'},
                status=status.HTTP_403_FORBIDDEN
            )

        if share.share_type == 'email' and email not in share.allowed_emails_list:
            return Response(
                {'error': 'Email not authorized'},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({'status': 'access granted'})

class FileOperationViewSet(viewsets.ModelViewSet):
    queryset = FileOperation.objects.all()
    serializer_class = FileOperationSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        operation = serializer.save(user=self.request.user)
        process_file_operation.delay(operation.id)

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """Retry failed operation"""
        operation = self.get_object()
        if operation.status == 'failed':
            operation.status = 'pending'
            operation.error_message = ''
            operation.save()
            process_file_operation.delay(operation.id)
            return Response({'status': 'operation queued'})
        return Response(
            {'error': 'Operation cannot be retried'},
            status=status.HTTP_400_BAD_REQUEST
        )

class FileBackupViewSet(viewsets.ModelViewSet):
    queryset = FileBackup.objects.all()
    serializer_class = FileBackupSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        backup = serializer.save(created_by=self.request.user)
        create_directory_backup.delay(backup.id)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get file system statistics"""
        now = timezone.now()
        total_size = File.objects.aggregate(total=Sum('size'))['total'] or 0
        
        stats = {
            'total_files': File.objects.count(),
            'total_directories': Directory.objects.count(),
            'total_size': total_size,
            'total_size_human': self._format_size(total_size),
            'active_shares': FileShare.objects.filter(
                expires_at__gt=now
            ).count(),
            'recent_operations': FileOperation.objects.filter(
                created_at__gte=now - timezone.timedelta(days=1)
            ).count(),
            'mime_type_distribution': dict(
                File.objects.values('mime_type')
                .annotate(count=Count('id'))
                .values_list('mime_type', 'count')
            ),
            'size_distribution': self._get_size_distribution(),
            'recent_backups': FileBackup.objects.filter(
                created_at__gte=now - timezone.timedelta(days=7)
            ).count(),
            'storage_usage_percent': self._get_storage_usage()
        }

        serializer = FileStatisticsSerializer(stats)
        return Response(serializer.data)

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    def _get_size_distribution(self):
        ranges = {
            '0-1MB': (0, 1024**2),
            '1MB-10MB': (1024**2, 10*1024**2),
            '10MB-100MB': (10*1024**2, 100*1024**2),
            '100MB-1GB': (100*1024**2, 1024**3),
            '>1GB': (1024**3, float('inf'))
        }
        
        distribution = {}
        for range_name, (min_size, max_size) in ranges.items():
            count = File.objects.filter(
                size__gte=min_size,
                size__lt=max_size
            ).count()
            distribution[range_name] = count
        
        return distribution

    def _get_storage_usage(self):
        try:
            stat = os.statvfs('/')
            total = stat.f_blocks * stat.f_frsize
            used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize
            return (used / total) * 100
        except:
            return 0 