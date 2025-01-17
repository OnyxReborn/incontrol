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

# Version comparison function
version_gt() { test "$(printf '%s\n' "$@" | sort -V | head -n 1)" != "$1"; }

# Check Python version
check_python_version() {
    log "Checking Python version..."
    local min_version="3.8.0"
    local current_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    
    if ! version_gt "$min_version" "$current_version"; then
        log "✓ Python version $current_version meets minimum requirement ($min_version)"
        return 0
    else
        error "✗ Python version $current_version is below minimum requirement ($min_version)"
        return 1
    fi
}

# Check MariaDB version
check_mariadb_version() {
    log "Checking MariaDB version..."
    local min_version="10.3.0"
    
    if ! command -v mysql >/dev/null 2>&1; then
        warning "MariaDB not installed, will be installed during setup"
        return 0
    fi
    
    local current_version=$(mysql --version | grep -o 'Distrib \([0-9.]*\)' | awk '{print $2}')
    
    if ! version_gt "$min_version" "$current_version"; then
        log "✓ MariaDB version $current_version meets minimum requirement ($min_version)"
        return 0
    else
        error "✗ MariaDB version $current_version is below minimum requirement ($min_version)"
        return 1
    fi
}

# Check Redis version
check_redis_version() {
    log "Checking Redis version..."
    local min_version="6.0.0"
    
    if ! command -v redis-server >/dev/null 2>&1; then
        warning "Redis not installed, will be installed during setup"
        return 0
    fi
    
    local current_version=$(redis-server --version | grep -o 'v=[0-9.]*' | cut -d= -f2)
    
    if ! version_gt "$min_version" "$current_version"; then
        log "✓ Redis version $current_version meets minimum requirement ($min_version)"
        return 0
    else
        error "✗ Redis version $current_version is below minimum requirement ($min_version)"
        return 1
    fi
}

# Check disk space
check_disk_space() {
    log "Checking disk space..."
    local min_space_gb=10
    local available_space_gb=$(df -BG / | awk 'NR==2 {print $4}' | tr -d 'G')
    
    if [ "$available_space_gb" -ge "$min_space_gb" ]; then
        log "✓ Available disk space: ${available_space_gb}GB (minimum: ${min_space_gb}GB)"
        return 0
    else
        error "✗ Insufficient disk space: ${available_space_gb}GB (minimum: ${min_space_gb}GB)"
        return 1
    fi
}

# Check configuration files
check_config_files() {
    log "Validating configuration files..."
    local errors=0
    
    # Check Nginx configuration
    if [ -f deployment/nginx/nginx.conf ]; then
        nginx -t -c deployment/nginx/nginx.conf >/dev/null 2>&1 || {
            error "✗ Invalid Nginx configuration"
            ((errors++))
        }
    fi
    
    # Check BIND configuration
    if [ -f deployment/bind/named.conf ]; then
        named-checkconf deployment/bind/named.conf >/dev/null 2>&1 || {
            error "✗ Invalid BIND configuration"
            ((errors++))
        }
    fi
    
    # Check zone files
    for zonefile in deployment/bind/zones/db.*; do
        if [ -f "$zonefile" ]; then
            named-checkzone example.com "$zonefile" >/dev/null 2>&1 || {
                error "✗ Invalid zone file: $zonefile"
                ((errors++))
            }
        fi
    done
    
    # Validate systemd service files
    for service in deployment/systemd/*.service; do
        if [ -f "$service" ]; then
            systemd-analyze verify "$service" >/dev/null 2>&1 || {
                error "✗ Invalid systemd service file: $service"
                ((errors++))
            }
        fi
    done
    
    return $errors
}

# Check system dependencies
check_dependencies() {
    log "Checking system dependencies..."
    local deps=(
        "curl"
        "wget"
        "git"
        "make"
        "gcc"
        "openssl"
        "libssl-dev"
    )
    local missing=()
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            missing+=("$dep")
        fi
    done
    
    if [ ${#missing[@]} -eq 0 ]; then
        log "✓ All required system dependencies are installed"
        return 0
    else
        error "✗ Missing dependencies: ${missing[*]}"
        return 1
    fi
}

# Main function
main() {
    log "Starting pre-installation checks..."
    local errors=0
    
    # Run all checks
    check_python_version || ((errors++))
    check_mariadb_version || ((errors++))
    check_redis_version || ((errors++))
    check_disk_space || ((errors++))
    check_config_files || ((errors++))
    check_dependencies || ((errors++))
    
    # Summary
    if [ $errors -eq 0 ]; then
        log "All pre-installation checks passed successfully!"
        return 0
    else
        error "Pre-installation checks completed with $errors errors"
        return 1
    fi
}

# Run main function
main 