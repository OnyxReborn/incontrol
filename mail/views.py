from django.shortcuts import render
from rest_framework import viewsets, permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Q
import subprocess
import os
from .models import MailDomain, MailAccount, MailAlias, SpamFilter, MailQueue, MailLog
from .serializers import (
    MailDomainSerializer, MailAccountSerializer, MailAliasSerializer,
    SpamFilterSerializer, MailQueueSerializer, MailLogSerializer,
    MailStatisticsSerializer
)

class MailDomainViewSet(viewsets.ModelViewSet):
    queryset = MailDomain.objects.all()
    serializer_class = MailDomainSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_postfix_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_postfix_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_postfix_config()

    def _update_postfix_config(self):
        # Generate virtual domains file
        domains = MailDomain.objects.filter(is_active=True)
        with open('/etc/postfix/virtual_domains', 'w') as f:
            for domain in domains:
                f.write(f"{domain.name}\n")

        # Update Postfix maps
        subprocess.run(['postmap', '/etc/postfix/virtual_domains'], check=True)
        subprocess.run(['postfix', 'reload'], check=True)

class MailAccountViewSet(viewsets.ModelViewSet):
    queryset = MailAccount.objects.all()
    serializer_class = MailAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if 'password' in self.request.data:
            password = self.request.data['password']
            password_hash = make_password(password)
            serializer.save(password_hash=password_hash)
        else:
            serializer.save()
        self._update_postfix_config()

    def perform_update(self, serializer):
        if 'password' in self.request.data:
            password = self.request.data['password']
            password_hash = make_password(password)
            serializer.save(password_hash=password_hash)
        else:
            serializer.save()
        self._update_postfix_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_postfix_config()

    def _update_postfix_config(self):
        # Generate virtual mailboxes file
        accounts = MailAccount.objects.filter(status='active')
        with open('/etc/postfix/virtual_mailboxes', 'w') as f:
            for account in accounts:
                f.write(f"{account.email} {account.email}/\n")

        # Update Postfix maps
        subprocess.run(['postmap', '/etc/postfix/virtual_mailboxes'], check=True)
        subprocess.run(['postfix', 'reload'], check=True)

class MailAliasViewSet(viewsets.ModelViewSet):
    queryset = MailAlias.objects.all()
    serializer_class = MailAliasSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_postfix_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_postfix_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_postfix_config()

    def _update_postfix_config(self):
        # Generate virtual aliases file
        aliases = MailAlias.objects.filter(is_active=True)
        with open('/etc/postfix/virtual_aliases', 'w') as f:
            for alias in aliases:
                destinations = [d.strip() for d in alias.destinations.split('\n') if d.strip()]
                if destinations:
                    f.write(f"{alias.email} {', '.join(destinations)}\n")

        # Update Postfix maps
        subprocess.run(['postmap', '/etc/postfix/virtual_aliases'], check=True)
        subprocess.run(['postfix', 'reload'], check=True)

class SpamFilterViewSet(viewsets.ModelViewSet):
    queryset = SpamFilter.objects.all()
    serializer_class = SpamFilterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._update_spamassassin_config()

    def perform_update(self, serializer):
        instance = serializer.save()
        self._update_spamassassin_config()

    def perform_destroy(self, instance):
        instance.delete()
        self._update_spamassassin_config()

    def _update_spamassassin_config(self):
        # Generate SpamAssassin rules file
        filters = SpamFilter.objects.filter(is_active=True).order_by('priority')
        with open('/etc/spamassassin/local.cf', 'w') as f:
            for filter in filters:
                if filter.filter_type == 'domain':
                    f.write(f"blacklist_from *@{filter.pattern}\n")
                elif filter.filter_type == 'email':
                    f.write(f"blacklist_from {filter.pattern}\n")
                elif filter.filter_type == 'ip':
                    f.write(f"blacklist_from {filter.pattern}\n")
                elif filter.filter_type == 'header':
                    f.write(f"header {filter.name} {filter.pattern}\n")
                elif filter.filter_type == 'content':
                    f.write(f"body {filter.name} {filter.pattern}\n")

        # Restart SpamAssassin
        subprocess.run(['systemctl', 'restart', 'spamassassin'], check=True)

class MailQueueViewSet(viewsets.ModelViewSet):
    queryset = MailQueue.objects.all()
    serializer_class = MailQueueSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        queue_item = self.get_object()
        try:
            # Attempt to resend the message
            subprocess.run(['postqueue', '-i', queue_item.message_id], check=True)
            queue_item.status = 'pending'
            queue_item.retry_count += 1
            queue_item.next_retry = timezone.now() + timedelta(minutes=5)
            queue_item.save()
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'])
    def delete(self, request, pk=None):
        queue_item = self.get_object()
        try:
            # Delete the message from the queue
            subprocess.run(['postsuper', '-d', queue_item.message_id], check=True)
            queue_item.delete()
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class MailLogViewSet(viewsets.ModelViewSet):
    queryset = MailLog.objects.all()
    serializer_class = MailLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        now = timezone.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        stats = {
            'total_accounts': MailAccount.objects.count(),
            'active_accounts': MailAccount.objects.filter(status='active').count(),
            'total_domains': MailDomain.objects.count(),
            'active_domains': MailDomain.objects.filter(is_active=True).count(),
            'total_aliases': MailAlias.objects.filter(is_active=True).count(),
            'messages_today': MailLog.objects.filter(timestamp__gte=today).count(),
            'messages_week': MailLog.objects.filter(timestamp__gte=week_ago).count(),
            'messages_month': MailLog.objects.filter(timestamp__gte=month_ago).count(),
            'spam_detected_today': MailLog.objects.filter(timestamp__gte=today, event='spam').count(),
            'virus_detected_today': MailLog.objects.filter(timestamp__gte=today, event='virus').count(),
            'queue_size': MailQueue.objects.exclude(status='sent').count(),
            'deferred_messages': MailQueue.objects.filter(status='deferred').count(),
            'storage_used': sum(account.used_quota for account in MailAccount.objects.all()),
        }

        # Convert storage to human-readable format
        storage_bytes = stats['storage_used']
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if storage_bytes < 1024:
                stats['storage_used_human'] = f"{storage_bytes:.2f} {unit}"
                break
            storage_bytes /= 1024

        serializer = MailStatisticsSerializer(stats)
        return Response(serializer.data)
