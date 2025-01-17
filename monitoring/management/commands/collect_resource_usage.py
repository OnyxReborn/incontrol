import psutil
from django.core.management.base import BaseCommand
from monitoring.models import ResourceUsage

class Command(BaseCommand):
    help = 'Collects current system resource usage statistics'

    def handle(self, *args, **options):
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

        # Get load averages
        load_avg = psutil.getloadavg()

        # Create new resource usage entry
        ResourceUsage.objects.create(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage,
            disk_read=disk_read,
            disk_write=disk_write,
            network_rx=network_rx,
            network_tx=network_tx,
            load_1=load_avg[0],
            load_5=load_avg[1],
            load_15=load_avg[2]
        )

        self.stdout.write(self.style.SUCCESS('Successfully collected resource usage statistics')) 