import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.serializers import serialize
from .models import Process, MetricSnapshot, ServiceStatus, Alert
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

class MonitoringConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection."""
        # Get the token from query parameters
        query_string = self.scope.get('query_string', b'').decode()
        params = dict(param.split('=') for param in query_string.split('&') if param)
        token = params.get('token')

        if not token:
            await self.close()
            return

        try:
            # Validate token
            access_token = AccessToken(token)
            user = await database_sync_to_async(get_user_model().objects.get)(id=access_token['user_id'])
            self.scope['user'] = user
        except Exception:
            await self.close()
            return

        # Accept the connection
        await self.accept()
        self.groups = set()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave all groups
        for group in self.groups:
            await self.channel_layer.group_discard(
                group,
                self.channel_name
            )

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            group = data.get('group')

            if action == 'subscribe':
                if group not in self.groups:
                    await self.channel_layer.group_add(
                        f'monitoring_{group}',
                        self.channel_name
                    )
                    self.groups.add(group)
                    # Send initial data
                    if group == 'process_monitoring':
                        await self.send_process_data()
                    elif group == 'resource_monitoring':
                        await self.send_resource_data()
                    elif group == 'service_monitoring':
                        await self.send_service_data()

            elif action == 'unsubscribe':
                if group in self.groups:
                    await self.channel_layer.group_discard(
                        f'monitoring_{group}',
                        self.channel_name
                    )
                    self.groups.remove(group)

        except json.JSONDecodeError:
            pass

    @database_sync_to_async
    def get_process_data(self):
        """Get process data from database."""
        processes = Process.objects.all()
        return json.loads(serialize('json', processes))

    @database_sync_to_async
    def get_resource_data(self):
        """Get resource metrics from database."""
        metrics = MetricSnapshot.objects.order_by('-timestamp')[:60]  # Last hour of metrics
        return json.loads(serialize('json', metrics))

    @database_sync_to_async
    def get_service_data(self):
        """Get service status data from database."""
        services = ServiceStatus.objects.all()
        return json.loads(serialize('json', services))

    @database_sync_to_async
    def get_alert_data(self):
        """Get recent alerts from database."""
        alerts = Alert.objects.filter(acknowledged=False).order_by('-timestamp')[:10]
        return json.loads(serialize('json', alerts))

    async def send_process_data(self):
        """Send process data to client."""
        data = await self.get_process_data()
        await self.send(text_data=json.dumps({
            'type': 'process_data',
            'data': data
        }))

    async def send_resource_data(self):
        """Send resource data to client."""
        data = await self.get_resource_data()
        await self.send(text_data=json.dumps({
            'type': 'resource_data',
            'data': data
        }))

    async def send_service_data(self):
        """Send service status data to client."""
        data = await self.get_service_data()
        await self.send(text_data=json.dumps({
            'type': 'service_data',
            'data': data
        }))

    async def send_alert_data(self):
        """Send alert data to client."""
        data = await self.get_alert_data()
        await self.send(text_data=json.dumps({
            'type': 'alert_data',
            'data': data
        }))

    async def process_update(self, event):
        """Handle process update event."""
        await self.send_process_data()

    async def resource_update(self, event):
        """Handle resource update event."""
        await self.send_resource_data()

    async def service_update(self, event):
        """Handle service update event."""
        await self.send_service_data()

    async def alert_update(self, event):
        """Handle alert update event."""
        await self.send_alert_data() 