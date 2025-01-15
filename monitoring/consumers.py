import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from .models import MetricSnapshot, ServiceStatus, Alert
from .serializers import MetricSnapshotSerializer, ServiceStatusSerializer, AlertSerializer

User = get_user_model()

class MonitoringConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        token = self.scope['url_route']['kwargs'].get('token')
        if not token:
            await self.close()
            return

        try:
            access_token = AccessToken(token)
            user_id = access_token.payload.get('user_id')
            if not user_id:
                await self.close()
                return

            self.user = await self.get_user(user_id)
            if not self.user:
                await self.close()
                return

            await self.channel_layer.group_add('monitoring', self.channel_name)
            await self.accept()
            await self.send(json.dumps({
                'type': 'connection_established',
                'message': 'Connected to monitoring websocket'
            }))

        except TokenError:
            await self.close()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('monitoring', self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            group = data.get('group')

            if action == 'subscribe' and group:
                await self.channel_layer.group_add(group, self.channel_name)
                if group == 'process_monitoring':
                    processes = await self.get_processes()
                    await self.send_processes(processes)
                elif group == 'resource_monitoring':
                    metrics = await self.get_metrics()
                    await self.send_metrics(metrics)
                elif group == 'service_monitoring':
                    services = await self.get_services()
                    await self.send_services(services)
                elif group == 'alert_monitoring':
                    alerts = await self.get_alerts()
                    await self.send_alerts(alerts)

            elif action == 'unsubscribe' and group:
                await self.channel_layer.group_discard(group, self.channel_name)

        except json.JSONDecodeError:
            pass

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_processes(self):
        import psutil
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status']):
            try:
                pinfo = proc.as_dict()
                processes.append({
                    'pid': pinfo['pid'],
                    'name': pinfo['name'],
                    'user': pinfo['username'],
                    'cpu_percent': pinfo['cpu_percent'],
                    'memory_percent': pinfo['memory_percent'],
                    'status': pinfo['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return processes

    @database_sync_to_async
    def get_metrics(self):
        try:
            latest_metrics = MetricSnapshot.objects.latest('timestamp')
            return MetricSnapshotSerializer(latest_metrics).data
        except MetricSnapshot.DoesNotExist:
            return None

    @database_sync_to_async
    def get_services(self):
        services = ServiceStatus.objects.all()
        return ServiceStatusSerializer(services, many=True).data

    @database_sync_to_async
    def get_alerts(self):
        alerts = Alert.objects.filter(acknowledged=False).order_by('-timestamp')
        return AlertSerializer(alerts, many=True).data

    async def send_processes(self, processes):
        await self.send(json.dumps({
            'type': 'process_monitoring',
            'payload': {
                'processes': processes
            }
        }))

    async def send_metrics(self, metrics):
        await self.send(json.dumps({
            'type': 'resource_monitoring',
            'payload': {
                'metrics': metrics
            }
        }))

    async def send_services(self, services):
        await self.send(json.dumps({
            'type': 'service_monitoring',
            'payload': {
                'services': services
            }
        }))

    async def send_alerts(self, alerts):
        await self.send(json.dumps({
            'type': 'alert_monitoring',
            'payload': {
                'alerts': alerts
            }
        }))

    async def process_update(self, event):
        await self.send_processes(event['processes'])

    async def metric_update(self, event):
        await self.send_metrics(event['metrics'])

    async def service_update(self, event):
        await self.send_services(event['services'])

    async def alert_update(self, event):
        await self.send_alerts(event['alerts']) 