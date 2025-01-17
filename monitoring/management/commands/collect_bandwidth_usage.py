import re
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db.models import Sum
from monitoring.models import BandwidthUsage
from webserver.models import VirtualHost

class Command(BaseCommand):
    help = 'Collects bandwidth usage statistics from Nginx access logs'

    def handle(self, *args, **options):
        log_pattern = re.compile(
            r'(?P<ip>\d+\.\d+\.\d+\.\d+)\s+-\s+(?P<user>[^\s]*)\s+\[(?P<time>[^\]]+)\]\s+'
            r'"(?P<method>\w+)\s+(?P<path>[^\s]+)\s+[^"]+"\s+(?P<status>\d+)\s+'
            r'(?P<size>\d+)\s+"[^"]*"\s+"[^"]*"\s+(?P<request_time>[^\s]+)'
        )

        # Get all virtual hosts
        vhosts = VirtualHost.objects.all()
        
        # Process access log
        try:
            with open('/var/log/nginx/access.log', 'r') as f:
                for line in f:
                    match = log_pattern.match(line)
                    if match:
                        data = match.groupdict()
                        path = data['path']
                        size = int(data['size'])
                        
                        # Find matching virtual host
                        for vhost in vhosts:
                            if any(domain in path for domain in vhost.domains):
                                # Update or create bandwidth usage
                                usage, created = BandwidthUsage.objects.get_or_create(
                                    domain=vhost,
                                    defaults={
                                        'bytes_in': 0,
                                        'bytes_out': size,
                                        'requests': 1
                                    }
                                )
                                
                                if not created:
                                    usage.bytes_out += size
                                    usage.requests += 1
                                    usage.save()
                                
                                break

            # Calculate totals
            totals = BandwidthUsage.objects.aggregate(
                total_in=Sum('bytes_in'),
                total_out=Sum('bytes_out'),
                total_requests=Sum('requests')
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully collected bandwidth usage statistics. "
                    f"Total In: {totals['total_in'] or 0} bytes, "
                    f"Total Out: {totals['total_out'] or 0} bytes, "
                    f"Total Requests: {totals['total_requests'] or 0}"
                )
            )

        except FileNotFoundError:
            self.stdout.write(
                self.style.WARNING('Access log file not found at /var/log/nginx/access.log')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error collecting bandwidth usage statistics: {str(e)}')
            ) 