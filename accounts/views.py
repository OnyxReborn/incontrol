import os
import pwd
import grp
import crypt
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.utils import timezone
from .models import UserProfile, UserGroup, AccessKey
from .serializers import UserSerializer, UserProfileSerializer, UserGroupSerializer, AccessKeySerializer

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        user = serializer.save()
        # Create system user
        try:
            os.system(f'useradd -m -s {user.profile.shell_path} {user.username}')
            os.system(f'chown -R {user.username}:{user.username} /home/{user.username}')
        except Exception as e:
            user.delete()
            raise Exception(f"Failed to create system user: {str(e)}")

    def perform_destroy(self, instance):
        username = instance.username
        super().perform_destroy(instance)
        # Remove system user
        try:
            os.system(f'userdel -r {username}')
        except Exception as e:
            raise Exception(f"Failed to remove system user: {str(e)}")

    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        user = self.get_object()
        password = request.data.get('password')
        if not password:
            return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(password)
        user.save()
        
        # Update system user password
        try:
            encrypted_pass = crypt.crypt(password)
            os.system(f'usermod -p "{encrypted_pass}" {user.username}')
        except Exception as e:
            return Response({'error': f'Failed to update system password: {str(e)}'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'status': 'password changed'})

class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'])
    def update_quota(self, request, pk=None):
        profile = self.get_object()
        quota = request.data.get('quota')
        if not quota:
            return Response({'error': 'Quota is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        profile.disk_quota = quota
        profile.save()
        
        # Update system quota
        try:
            os.system(f'setquota -u {profile.user.username} {quota} {quota} 0 0 -a')
        except Exception as e:
            return Response({'error': f'Failed to update system quota: {str(e)}'}, 
                          status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({'status': 'quota updated'})

class UserGroupViewSet(viewsets.ModelViewSet):
    queryset = UserGroup.objects.all()
    serializer_class = UserGroupSerializer
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        group = serializer.save()
        # Create system group
        try:
            os.system(f'groupadd {group.name}')
        except Exception as e:
            group.delete()
            raise Exception(f"Failed to create system group: {str(e)}")

    def perform_destroy(self, instance):
        group_name = instance.name
        super().perform_destroy(instance)
        # Remove system group
        try:
            os.system(f'groupdel {group_name}')
        except Exception as e:
            raise Exception(f"Failed to remove system group: {str(e)}")

class AccessKeyViewSet(viewsets.ModelViewSet):
    serializer_class = AccessKeySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return AccessKey.objects.all()
        return AccessKey.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        key = serializer.save()
        if key.key_type == 'SSH':
            # Add SSH key to authorized_keys
            try:
                ssh_dir = os.path.expanduser(f'~{key.user.username}/.ssh')
                os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
                auth_keys_file = os.path.join(ssh_dir, 'authorized_keys')
                with open(auth_keys_file, 'a') as f:
                    f.write(f'{key.key_value}\n')
                os.chmod(auth_keys_file, 0o600)
                os.chown(auth_keys_file, 
                        pwd.getpwnam(key.user.username).pw_uid,
                        grp.getgrnam(key.user.username).gr_gid)
            except Exception as e:
                key.delete()
                raise Exception(f"Failed to add SSH key: {str(e)}")

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        key = self.get_object()
        key.is_active = False
        key.save()
        return Response({'status': 'key deactivated'})
