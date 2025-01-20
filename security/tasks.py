import os
import re
import subprocess
from datetime import datetime, timedelta
from celery import shared_task
from django.utils import timezone
from django.db.models import Count
from core.models import Notification
from .models import (
    SecurityIncident, FailedLogin, FirewallRule,
    SecurityScan
)

@shared_task
def monitor_auth_log():
    """Monitor authentication logs for failed login attempts."""
    try:
        # Read auth.log
        with open('/var/log/auth.log', 'r') as f:
            log_lines = f.readlines()

        # Process new lines
        for line in log_lines:
            if 'Failed password' in line or 'authentication failure' in line:
                # Parse log line
                timestamp_str = line[:15]
                timestamp = datetime.strptime(timestamp_str, '%b %d %H:%M:%S')
                
                # Add current year
                current_year = timezone.now().year
                timestamp = timestamp.replace(year=current_year)
                
                # Extract information
                ip_match = re.search(r'from (\d+\.\d+\.\d+\.\d+)', line)
                if ip_match:
                    ip = ip_match.group(1)
                    username = re.search(r'user (\w+)', line)
                    username = username.group(1) if username else 'unknown'
                    service = 'ssh' if 'sshd' in line else 'other'
                    
                    # Record failed login
                    FailedLogin.objects.create(
                        username=username,
                        source_ip=ip,
                        service=service,
                        attempt_time=timestamp,
                        details=line.strip()
                    )
                    
                    # Check for brute force attempts
                    recent_attempts = FailedLogin.objects.filter(
                        source_ip=ip,
                        attempt_time__gte=timezone.now() - timedelta(minutes=5)
                    ).count()
                    
                    if recent_attempts >= 5:
                        # Create security incident
                        SecurityIncident.objects.create(
                            title=f'Potential brute force attack from {ip}',
                            description=f'Multiple failed login attempts detected from {ip}',
                            severity='high',
                            status='open',
                            source_ip=ip
                        )
                        
                        # Block IP
                        block_ip_address.delay(ip)
                        
                        # Create notification
                        Notification.objects.create(
                            title='Security Alert',
                            message=f'Potential brute force attack detected from {ip}',
                            level='ERROR',
                            user_id=1  # Use the first admin user
                        )

    except Exception as e:
        Notification.objects.create(
            title="Auth Log Monitoring Error",
            message=f"Failed to monitor auth log: {str(e)}",
            level='ERROR',
            user_id=1  # Use the first admin user
        )

@shared_task
def scan_for_vulnerabilities():
    """Run automated vulnerability scans."""
    try:
        # Create scan record
        scan = SecurityScan.objects.create(
            scan_type='vulnerability',
            target='localhost',
            status='in_progress',
            started_at=timezone.now()
        )

        # Run OpenVAS scan
        result = subprocess.run([
            'omp', '-u', 'admin', '-w', 'admin',
            '--xml', '<create_task><name>Auto Scan</name><target>localhost</target></create_task>'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            scan.findings = {'output': result.stdout}
            scan.status = 'completed'
        else:
            scan.findings = {'error': result.stderr}
            scan.status = 'failed'

        scan.completed_at = timezone.now()
        scan.save()

    except Exception as e:
        Notification.objects.create(
            title="Vulnerability Scan Error",
            message=f"Failed to run vulnerability scan: {str(e)}",
            level='ERROR',
            user_id=1  # Use the first admin user
        )

@shared_task
def check_file_integrity():
    """Check file integrity using AIDE."""
    try:
        # Run AIDE check
        result = subprocess.run(['aide', '--check'],
                             capture_output=True, text=True)
        
        if result.returncode != 0:
            # Files have been modified
            SecurityIncident.objects.create(
                title="File Integrity Violation Detected",
                description=result.stdout,
                severity='high',
                status='open',
                detected_at=timezone.now()
            )
            
            Notification.objects.create(
                title="File Integrity Alert",
                message="System files have been modified. Check security incidents.",
                level='WARNING',
                user_id=1  # Use the first admin user
            )

    except Exception as e:
        Notification.objects.create(
            title="File Integrity Check Error",
            message=f"Failed to check file integrity: {str(e)}",
            level='ERROR',
            user_id=1  # Use the first admin user
        )

@shared_task
def analyze_failed_logins():
    """Analyze failed login patterns and update firewall rules."""
    try:
        # Get failed logins from last hour
        hour_ago = timezone.now() - timedelta(hours=1)
        failed_logins = FailedLogin.objects.filter(
            attempt_time__gte=hour_ago
        ).values('source_ip').annotate(
            attempts=Count('id')
        ).filter(attempts__gte=10)

        for item in failed_logins:
            ip = item['source_ip']
            if not FirewallRule.objects.filter(source=ip).exists():
                # Create firewall rule to block IP
                FirewallRule.objects.create(
                    name=f"Auto Block {ip}",
                    source=ip,
                    destination='any',
                    protocol='all',
                    action='DROP',
                    description=f"Automatically blocked due to multiple failed logins",
                    is_active=True
                )
                
                Notification.objects.create(
                    title=f"IP Automatically Blocked: {ip}",
                    message=f"IP address {ip} has been blocked due to multiple failed logins",
                    level='WARNING',
                    user_id=1  # Use the first admin user
                )

    except Exception as e:
        Notification.objects.create(
            title="Failed Login Analysis Error",
            message=f"Failed to analyze login attempts: {str(e)}",
            level='ERROR',
            user_id=1  # Use the first admin user
        )

def block_ip(ip):
    """Block an IP address using iptables."""
    try:
        subprocess.run([
            'iptables', '-A', 'INPUT', '-s', ip, '-j', 'DROP'
        ], check=True)
        subprocess.run(['iptables-save'], check=True)
        
        # Update database
        FailedLogin.objects.filter(source_ip=ip).update(blocked=True)
        
        Notification.objects.create(
            title=f"IP Blocked: {ip}",
            message=f"IP address {ip} has been blocked",
            level='INFO',
            user_id=1  # Use the first admin user
        )
    except Exception as e:
        Notification.objects.create(
            title=f"IP Block Error: {ip}",
            message=f"Failed to block IP address: {str(e)}",
            level='ERROR',
            user_id=1  # Use the first admin user
        )

@shared_task
def apply_firewall_rule(rule_id):
    """Apply a firewall rule using iptables."""
    try:
        rule = FirewallRule.objects.get(id=rule_id)
        
        # Build iptables command
        command = ['iptables']
        if rule.action == 'ACCEPT':
            command.extend(['-A', 'INPUT'])
        elif rule.action == 'DROP':
            command.extend(['-A', 'INPUT'])
        elif rule.action == 'REJECT':
            command.extend(['-A', 'INPUT'])
            
        if rule.source:
            command.extend(['-s', rule.source])
        if rule.destination:
            command.extend(['-d', rule.destination])
            
        if rule.protocol != 'all':
            command.extend(['-p', rule.protocol])
            
        if rule.port_range:
            ports = rule.port_range.split('-')
            if len(ports) == 1:
                command.extend(['--dport', ports[0]])
            else:
                command.extend(['--dport', rule.port_range])
                
        command.extend(['-j', rule.action])
        
        # Execute command
        subprocess.run(command, check=True)
        
        rule.is_active = True
        rule.save()
        
        return True
    except Exception as e:
        print(f"Error applying firewall rule: {e}")
        return False

@shared_task
def remove_firewall_rule(rule_id):
    """Remove a firewall rule using iptables."""
    try:
        rule = FirewallRule.objects.get(id=rule_id)
        
        # Build iptables command
        command = ['iptables', '-D', 'INPUT']
        if rule.source:
            command.extend(['-s', rule.source])
        if rule.destination:
            command.extend(['-d', rule.destination])
            
        if rule.protocol != 'all':
            command.extend(['-p', rule.protocol])
            
        if rule.port_range:
            ports = rule.port_range.split('-')
            if len(ports) == 1:
                command.extend(['--dport', ports[0]])
            else:
                command.extend(['--dport', rule.port_range])
                
        command.extend(['-j', rule.action])
        
        # Execute command
        subprocess.run(command, check=True)
        
        return True
    except Exception as e:
        print(f"Error removing firewall rule: {e}")
        return False

@shared_task
def run_security_scan(scan_id):
    """Run a security scan."""
    try:
        scan = SecurityScan.objects.get(id=scan_id)
        scan.status = 'in_progress'
        scan.started_at = timezone.now()
        scan.save()
        
        findings = []
        
        if scan.scan_type == 'port':
            # Run nmap scan
            command = ['nmap', '-sV', scan.target]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            findings = result.stdout
        elif scan.scan_type == 'vulnerability':
            # Run vulnerability scan (e.g., with OpenVAS or similar tool)
            findings = "Vulnerability scan results would go here"
        elif scan.scan_type == 'malware':
            # Run malware scan (e.g., with ClamAV)
            command = ['clamscan', '-r', scan.target]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            findings = result.stdout
        elif scan.scan_type == 'rootkit':
            # Run rootkit scan (e.g., with rkhunter)
            command = ['rkhunter', '--check', '--skip-keypress']
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            findings = result.stdout
        elif scan.scan_type == 'integrity':
            # Run file integrity check
            findings = check_file_integrity()
            
        scan.findings = findings
        scan.status = 'completed'
        scan.completed_at = timezone.now()
        scan.save()
        
        # Create notification if issues found
        if findings and 'WARNING' in findings or 'ALERT' in findings:
            Notification.objects.create(
                title=f'Security Scan Alert',
                message=f'Issues found in {scan.scan_type} scan of {scan.target}',
                level='WARNING',
                user_id=1  # Use the first admin user
            )
            
        return True
    except Exception as e:
        scan.status = 'failed'
        scan.findings = str(e)
        scan.completed_at = timezone.now()
        scan.save()
        return False

@shared_task
def block_ip_address(ip):
    """Block an IP address using iptables."""
    try:
        command = ['iptables', '-A', 'INPUT', '-s', ip, '-j', 'DROP']
        subprocess.run(command, check=True)
        
        # Create notification
        Notification.objects.create(
            title='IP Blocked',
            message=f'IP address {ip} has been blocked',
            level='WARNING',
            user_id=1  # Use the first admin user
        )
        
        return True
    except Exception as e:
        print(f"Error blocking IP address: {e}")
        return False 