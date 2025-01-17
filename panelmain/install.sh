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

# Function to install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
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
        libmariadb-dev \
        nginx \
        mariadb-server \
        redis-server \
        postfix \
        dovecot-core \
        bind9 \
        prometheus \
        node-exporter \
        alertmanager \
        fail2ban \
        certbot
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
    mkdir -p /etc/nginx/sites-available
    mkdir -p /etc/nginx/sites-enabled
    mkdir -p /var/mail/vhosts
    mkdir -p /etc/postfix
    mkdir -p /etc/dovecot
    mkdir -p /etc/bind/zones
    mkdir -p /var/log/named
    mkdir -p /var/cache/bind
    mkdir -p /etc/prometheus
    mkdir -p /etc/alertmanager
    mkdir -p /var/lib/prometheus
    mkdir -p /var/lib/alertmanager
    mkdir -p /etc/fail2ban
    
    # Set proper permissions
    chown -R www-data:www-data /var/log/incontrol
    chown -R www-data:www-data /var/lib/incontrol
}

# Function to copy configuration files
copy_configs() {
    log "Copying configuration files..."
    
    # Copy configuration files from deployment directory
    cp -r deployment/nginx/* /etc/nginx/ || warning "No Nginx configs found"
    cp -r deployment/mail/* /etc/postfix/ || warning "No mail configs found"
    cp -r deployment/bind/* /etc/bind/ || warning "No BIND configs found"
    cp -r deployment/prometheus/* /etc/prometheus/ || warning "No Prometheus configs found"
    cp -r deployment/alertmanager/* /etc/alertmanager/ || warning "No Alertmanager configs found"
    cp -r deployment/fail2ban/* /etc/fail2ban/ || warning "No Fail2ban configs found"
    cp -r deployment/systemd/*.service /etc/systemd/system/ || warning "No systemd service files found"
    
    # Reload systemd
    systemctl daemon-reload
}

# Function to setup database
setup_database() {
    log "Setting up database..."
    
    # Start MariaDB if not running
    systemctl start mariadb
    systemctl enable mariadb
    
    # Create database and user
    mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    mysql -e "CREATE USER IF NOT EXISTS 'incontrol'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
    mysql -e "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';"
    mysql -e "FLUSH PRIVILEGES;"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    error "Please run as root (sudo ./install.sh)"
fi

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    error "This script requires Ubuntu OS"
fi

log "Starting InControl installation..."

# Install dependencies first
install_dependencies

# Setup initial configuration
setup_initial_config

# Create required directories
create_directories

# Setup database
setup_database

# Copy configuration files
copy_configs

log "Installation completed successfully!"
log "You can find your credentials in /opt/incontrol/.env" 