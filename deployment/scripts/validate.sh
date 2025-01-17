#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() { echo -e "${GREEN}[CHECK] $1${NC}"; }
error() { echo -e "${RED}[ERROR] $1${NC}" >&2; }
warning() { echo -e "${YELLOW}[WARNING] $1${NC}"; }

# Check service status
check_service() {
    local service=$1
    log "Checking $service status..."
    if systemctl is-active --quiet $service; then
        log "✓ $service is running"
        return 0
    else
        error "✗ $service is not running"
        return 1
    fi
}

# Check port availability
check_port() {
    local port=$1
    local service=$2
    log "Checking port $port for $service..."
    if nc -z localhost $port; then
        log "✓ Port $port ($service) is open"
        return 0
    else
        error "✗ Port $port ($service) is not accessible"
        return 1
    fi
}

# Check file permissions
check_permissions() {
    local path=$1
    local expected_owner=$2
    local expected_perms=$3
    log "Checking permissions for $path..."
    
    if [ ! -e "$path" ]; then
        error "✗ Path $path does not exist"
        return 1
    fi
    
    local actual_owner=$(stat -c '%U:%G' "$path")
    local actual_perms=$(stat -c '%a' "$path")
    
    if [ "$actual_owner" != "$expected_owner" ]; then
        error "✗ Wrong ownership on $path: expected $expected_owner, got $actual_owner"
        return 1
    fi
    
    if [ "$actual_perms" != "$expected_perms" ]; then
        error "✗ Wrong permissions on $path: expected $expected_perms, got $actual_perms"
        return 1
    fi
    
    log "✓ Permissions correct for $path"
    return 0
}

# Check database connectivity
check_database() {
    log "Checking database connectivity..."
    if mysql -u incontrol -p"${DB_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
        log "✓ Database connection successful"
        return 0
    else
        error "✗ Database connection failed"
        return 1
    fi
}

# Check Redis connectivity
check_redis() {
    log "Checking Redis connectivity..."
    if redis-cli -a "${REDIS_PASSWORD}" ping | grep -q "PONG"; then
        log "✓ Redis connection successful"
        return 0
    else
        error "✗ Redis connection failed"
        return 1
    fi
}

# Check mail services
check_mail() {
    log "Checking mail services..."
    
    # Test Postfix configuration
    if postfix check >/dev/null 2>&1; then
        log "✓ Postfix configuration is valid"
    else
        error "✗ Postfix configuration is invalid"
        return 1
    fi
    
    # Test Dovecot configuration
    if dovecot -n >/dev/null 2>&1; then
        log "✓ Dovecot configuration is valid"
    else
        error "✗ Dovecot configuration is invalid"
        return 1
    fi
    
    return 0
}

# Check DNS services
check_dns() {
    log "Checking DNS services..."
    
    # Test BIND configuration
    if named-checkconf >/dev/null 2>&1; then
        log "✓ BIND configuration is valid"
    else
        error "✗ BIND configuration is invalid"
        return 1
    fi
    
    return 0
}

# Main validation function
main() {
    local errors=0
    
    # Load environment variables
    source /opt/incontrol/.env
    
    # Check core services
    check_service nginx || ((errors++))
    check_service mariadb || ((errors++))
    check_service redis-server || ((errors++))
    check_service postfix || ((errors++))
    check_service dovecot || ((errors++))
    check_service bind9 || ((errors++))
    check_service prometheus || ((errors++))
    check_service alertmanager || ((errors++))
    check_service grafana-server || ((errors++))
    check_service fail2ban || ((errors++))
    
    # Check ports
    check_port 80 "HTTP" || ((errors++))
    check_port 443 "HTTPS" || ((errors++))
    check_port 3306 "MariaDB" || ((errors++))
    check_port 6379 "Redis" || ((errors++))
    check_port 25 "SMTP" || ((errors++))
    check_port 993 "IMAP" || ((errors++))
    check_port 53 "DNS" || ((errors++))
    
    # Check permissions
    check_permissions "/opt/incontrol" "incontrol:incontrol" "755" || ((errors++))
    check_permissions "/var/log/incontrol" "incontrol:incontrol" "755" || ((errors++))
    check_permissions "/etc/nginx/ssl" "root:root" "700" || ((errors++))
    check_permissions "/var/mail/vhosts" "vmail:mail" "755" || ((errors++))
    
    # Check services
    check_database || ((errors++))
    check_redis || ((errors++))
    check_mail || ((errors++))
    check_dns || ((errors++))
    
    # Summary
    if [ $errors -eq 0 ]; then
        log "All validation checks passed successfully!"
        return 0
    else
        error "Validation completed with $errors errors"
        return 1
    fi
}

# Run validation
main 