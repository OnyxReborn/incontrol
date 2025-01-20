from django.shortcuts import render
from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils import timezone
from django.db import connection
from rest_framework.decorators import action
from rest_framework.response import Response
import subprocess
import os
from .models import Database, DatabaseUser, DatabaseBackup
from .serializers import DatabaseSerializer, DatabaseUserSerializer, DatabaseBackupSerializer

# Create your views here.

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
