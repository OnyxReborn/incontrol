from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

class ServiceViewSet(viewsets.ViewSet):
    basename = 'service'

    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({})

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def restart(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

class PackageViewSet(viewsets.ViewSet):
    basename = 'package'

    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({})

    @action(detail=True, methods=["post"])
    def install(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def uninstall(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

class BackupViewSet(viewsets.ViewSet):
    basename = 'backup'

    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({})

    @action(detail=True, methods=["post"])
    def create_backup(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

class CronJobViewSet(viewsets.ViewSet):
    basename = 'cronjob'

    def list(self, request):
        return Response([])

    def retrieve(self, request, pk=None):
        return Response({})

    @action(detail=True, methods=["post"])
    def enable(self, request, pk=None):
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None):
        return Response(status=status.HTTP_200_OK) 