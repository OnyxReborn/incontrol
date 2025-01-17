#!/bin/bash

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# Function to generate secure passwords
generate_password() {
    tr -dc 'A-Za-z0-9!#$%&()*+,-./:;<=>?@[\]^_`{|}~' </dev/urandom | head -c 32
}

# Function to set up initial configuration
setup_initial_config() {
    log "Setting up initial configuration..."
    
    # Create .env file directory
    mkdir -p /opt/incontrol
    
    # Check if DOMAIN is set in environment
    if [ -z "${DOMAIN}" ]; then
        # If running in Docker, use a default domain for testing
        if [ -f "/.dockerenv" ]; then
            DOMAIN="localhost"
            warning "Running in Docker environment. Using default domain: ${DOMAIN}"
        else
            # Prompt for domain if not in Docker
            read -p "Enter your domain name (e.g., example.com): " DOMAIN
            if [ -z "${DOMAIN}" ]; then
                error "Domain name cannot be empty"
            fi
        fi
    fi
    
    # Generate passwords if not set
    DB_PASSWORD=${DB_PASSWORD:-$(generate_password)}
    REDIS_PASSWORD=${REDIS_PASSWORD:-$(generate_password)}
    MAIL_DB_PASSWORD=${MAIL_DB_PASSWORD:-$(generate_password)}
    
    # Create .env file
    cat > /opt/incontrol/.env << EOF
DOMAIN=${DOMAIN}
DB_PASSWORD=${DB_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
MAIL_DB_PASSWORD=${MAIL_DB_PASSWORD}
DJANGO_SECRET_KEY=$(generate_password)
EOF

    # Set proper permissions
    chmod 600 /opt/incontrol/.env
}

# Function to install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    apt-get update
    apt-get install -y \
        curl \
        wget \
        git \
        make \
        gcc \
        openssl \
        libssl-dev \
        python3-dev \
        python3-pip \
        python3-venv \
        libmariadb-dev
}

# Function to create required directories
create_directories() {
    log "Creating required directories..."
    
    # Main application directories
    mkdir -p /opt/incontrol
    mkdir -p /var/log/incontrol
    mkdir -p /var/lib/incontrol/backups
    mkdir -p /etc/incontrol
    
    # Service-specific directories
    mkdir -p /etc/nginx/ssl
    mkdir -p /var/mail/vhosts
    mkdir -p /etc/bind/zones
    mkdir -p /var/log/named
    mkdir -p /var/cache/bind
    mkdir -p /etc/prometheus
    mkdir -p /etc/alertmanager
    mkdir -p /var/lib/prometheus
    mkdir -p /var/lib/alertmanager
}

# Function to copy configuration files
copy_configs() {
    log "Copying configuration files..."
    
    # Create necessary directories first
    mkdir -p /etc/nginx/sites-available
    mkdir -p /etc/nginx/sites-enabled
    mkdir -p /etc/postfix
    mkdir -p /etc/dovecot
    mkdir -p /etc/bind/zones
    mkdir -p /etc/prometheus
    mkdir -p /etc/alertmanager
    mkdir -p /etc/fail2ban
    
    # Copy configuration files from deployment directory
    cp -r deployment/nginx/* /etc/nginx/
    cp -r deployment/mail/* /etc/postfix/
    cp -r deployment/bind/* /etc/bind/
    cp -r deployment/prometheus/* /etc/prometheus/
    cp -r deployment/alertmanager/* /etc/alertmanager/
    cp -r deployment/fail2ban/* /etc/fail2ban/
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    error "Please run as root (sudo ./install.sh)"
fi

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    error "This script requires Ubuntu OS"
fi

# Setup initial configuration
setup_initial_config

# Install dependencies first
install_dependencies

# Create required directories
create_directories

# Copy configuration files
copy_configs

# Rest of your installation script... 