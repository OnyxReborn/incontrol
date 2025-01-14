from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from core.models import Notification
from .models import SSLCertificate

@shared_task
def check_ssl_certificates():
    """Check SSL certificates for expiration."""
    certificates = SSLCertificate.objects.all()
    warning_threshold = timezone.now() + timedelta(days=30)
    critical_threshold = timezone.now() + timedelta(days=7)

    for cert in certificates:
        try:
            # Critical warning for certificates expiring within 7 days
            if cert.expiry_date <= critical_threshold:
                Notification.objects.create(
                    title=f"SSL Certificate Critical: {cert.name}",
                    message=f"SSL Certificate for {cert.domains} will expire in "
                           f"{(cert.expiry_date - timezone.now()).days} days!",
                    level='CRITICAL'
                )
            # Warning for certificates expiring within 30 days
            elif cert.expiry_date <= warning_threshold:
                Notification.objects.create(
                    title=f"SSL Certificate Warning: {cert.name}",
                    message=f"SSL Certificate for {cert.domains} will expire in "
                           f"{(cert.expiry_date - timezone.now()).days} days.",
                    level='WARNING'
                )

            # Auto-renew Let's Encrypt certificates
            if cert.certificate_type == 'lets_encrypt' and cert.auto_renew:
                if cert.expiry_date <= warning_threshold:
                    renew_lets_encrypt_certificate.delay(cert.id)

        except Exception as e:
            Notification.objects.create(
                title=f"SSL Certificate Check Error: {cert.name}",
                message=f"Error checking certificate: {str(e)}",
                level='ERROR'
            )

@shared_task
def renew_lets_encrypt_certificate(cert_id):
    """Renew a Let's Encrypt certificate."""
    from subprocess import run, CalledProcessError
    
    try:
        cert = SSLCertificate.objects.get(id=cert_id)
        if cert.certificate_type != 'lets_encrypt':
            raise ValueError("Not a Let's Encrypt certificate")

        # Run certbot renew for specific domains
        domains = cert.domains_list
        cmd = ['certbot', 'renew', '--non-interactive', '--cert-name', domains[0]]
        
        result = run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)

        # Update certificate record
        cert.issued_date = timezone.now()
        cert.expiry_date = timezone.now() + timedelta(days=90)
        cert.save()

        Notification.objects.create(
            title=f"SSL Certificate Renewed: {cert.name}",
            message=f"Successfully renewed Let's Encrypt certificate for {cert.domains}",
            level='INFO'
        )

    except Exception as e:
        Notification.objects.create(
            title=f"SSL Certificate Renewal Error",
            message=f"Failed to renew certificate: {str(e)}",
            level='ERROR'
        ) 