from celery import shared_task
from django.utils import timezone
from .models import DNSZone, DNSHealth
import dns.resolver
import dns.zone
import dns.query
import dns.exception
import socket
import time

@shared_task
def check_zone_health(zone_id):
    """Check the health of a DNS zone"""
    zone = DNSZone.objects.get(pk=zone_id)
    issues = []
    status = 'ok'
    primary_reachable = False
    serial_synced = False
    records_match = False

    try:
        # Check if primary nameserver is reachable
        start_time = time.time()
        socket.gethostbyname(zone.primary_ns)
        primary_reachable = True

        # Check zone serial
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [socket.gethostbyname(zone.primary_ns)]
        soa_answer = resolver.resolve(zone.name, 'SOA')
        remote_serial = soa_answer[0].serial
        serial_synced = (remote_serial == zone.serial)
        if not serial_synced:
            issues.append(f"Zone serial mismatch: local={zone.serial}, remote={remote_serial}")
            status = 'warning'

        # Check zone transfer
        try:
            xfr = dns.query.xfr(zone.primary_ns, zone.name)
            zone_data = dns.zone.from_xfr(xfr)
            records_match = True
        except Exception as e:
            issues.append(f"Zone transfer failed: {str(e)}")
            status = 'error'

        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

    except Exception as e:
        issues.append(f"Primary nameserver check failed: {str(e)}")
        status = 'error'
        response_time = 0

    # Create health record
    DNSHealth.objects.create(
        zone=zone,
        check_time=timezone.now(),
        status=status,
        primary_reachable=primary_reachable,
        serial_synced=serial_synced,
        records_match=records_match,
        issues=issues,
        response_time=response_time
    )

@shared_task
def monitor_all_zones():
    """Monitor health of all active DNS zones"""
    for zone in DNSZone.objects.filter(is_active=True):
        check_zone_health.delay(zone.id)

@shared_task
def cleanup_old_health_records():
    """Clean up old health records (keep last 30 days)"""
    threshold = timezone.now() - timezone.timedelta(days=30)
    DNSHealth.objects.filter(check_time__lt=threshold).delete()

@shared_task
def update_zone_serials():
    """Update zone serials for modified zones"""
    for zone in DNSZone.objects.filter(is_active=True):
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [socket.gethostbyname(zone.primary_ns)]
            soa_answer = resolver.resolve(zone.name, 'SOA')
            remote_serial = soa_answer[0].serial
            
            if remote_serial > zone.serial:
                zone.serial = remote_serial
                zone.save()
        except Exception as e:
            print(f"Failed to update serial for zone {zone.name}: {str(e)}")

@shared_task
def sync_zone_records(zone_id):
    """Sync records for a specific zone"""
    zone = DNSZone.objects.get(pk=zone_id)
    try:
        # Attempt zone transfer
        xfr = dns.query.xfr(zone.primary_ns, zone.name)
        zone_data = dns.zone.from_xfr(xfr)
        
        # Update local records
        for name, node in zone_data.items():
            for rdataset in node.rdatasets:
                for rdata in rdataset:
                    DNSRecord.objects.update_or_create(
                        zone=zone,
                        name=str(name),
                        type=dns.rdatatype.to_text(rdataset.rdtype),
                        defaults={
                            'content': str(rdata),
                            'ttl': rdataset.ttl
                        }
                    )
        return True
    except Exception as e:
        print(f"Failed to sync records for zone {zone.name}: {str(e)}")
        return False 