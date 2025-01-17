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

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    error "Please run as root (sudo ./uninstall.sh)"
fi

# Function to remove systemd services
remove_services() {
    log "Removing systemd services..."
    
    # Stop and disable services
    systemctl stop incontrol incontrol-worker incontrol-beat incontrol-ws prometheus alertmanager node_exporter grafana-server redis-server postfix dovecot bind9 fail2ban || true
    systemctl disable incontrol incontrol-worker incontrol-beat incontrol-ws prometheus alertmanager node_exporter grafana-server redis-server postfix dovecot bind9 fail2ban || true
    
    # Remove service files
    rm -f /etc/systemd/system/incontrol*.service
    rm -f /etc/systemd/system/prometheus.service
    rm -f /etc/systemd/system/alertmanager.service
    rm -f /etc/systemd/system/node_exporter.service
    
    systemctl daemon-reload
}

# Function to remove monitoring components
remove_monitoring() {
    log "Removing monitoring components..."
    
    # Remove binaries
    rm -f /usr/local/bin/prometheus
    rm -f /usr/local/bin/promtool
    rm -f /usr/local/bin/node_exporter
    rm -f /usr/local/bin/alertmanager
    rm -f /usr/local/bin/amtool
    
    # Remove directories
    rm -rf /etc/prometheus
    rm -rf /var/lib/prometheus
    rm -rf /etc/alertmanager
    rm -rf /var/lib/alertmanager
    
    # Remove users
    userdel -r prometheus || true
    userdel -r node_exporter || true
    userdel -r alertmanager || true
}

# Function to remove mail server
remove_mail() {
    log "Removing mail server..."
    
    # Stop services first
    systemctl stop postfix dovecot opendkim || true
    
    # Remove mail directories
    rm -rf /var/mail/vhosts
    rm -rf /etc/postfix/ssl
    rm -rf /etc/dovecot/ssl
    rm -rf /etc/opendkim
    
    # Remove configuration files
    rm -f /etc/postfix/main.cf
    rm -f /etc/dovecot/dovecot.conf
    rm -f /etc/opendkim.conf
    
    # Remove mail database
    mysql -e "DROP DATABASE IF EXISTS mail;"
    mysql -e "DROP USER IF EXISTS 'mail_admin'@'localhost';"
    
    # Remove mail user
    userdel -r vmail || true
}

# Function to remove DNS server
remove_dns() {
    log "Removing DNS server..."
    
    # Stop service
    systemctl stop bind9 || true
    
    # Remove directories and files
    rm -rf /etc/bind
    rm -rf /var/log/named
    rm -rf /var/cache/bind
}

# Function to remove web server
remove_web() {
    log "Removing web server configuration..."
    
    # Stop nginx
    systemctl stop nginx || true
    
    # Remove configuration files
    rm -f /etc/nginx/sites-available/incontrol
    rm -f /etc/nginx/sites-enabled/incontrol
    rm -rf /etc/nginx/ssl
    rm -rf /etc/nginx/modsecurity
    rm -f /etc/nginx/nginx.conf
    
    # Remove web directories
    rm -rf /var/www/vhosts
}

# Function to remove database
remove_database() {
    log "Removing database..."
    
    # Drop database and user
    mysql -e "DROP DATABASE IF EXISTS incontrol;"
    mysql -e "DROP USER IF EXISTS 'incontrol'@'localhost';"
}

# Function to remove Redis
remove_redis() {
    log "Removing Redis..."
    
    # Stop service
    systemctl stop redis-server || true
    
    # Remove directories
    rm -rf /var/lib/redis
    rm -rf /var/log/redis
    rm -f /etc/redis/redis.conf
}

# Function to remove security components
remove_security() {
    log "Removing security components..."
    
    # Stop services
    systemctl stop fail2ban || true
    
    # Remove configuration files
    rm -f /etc/fail2ban/jail.local
    
    # Remove SSL certificates
    certbot delete --cert-name ${DOMAIN} || true
    rm -f /etc/cron.d/certbot-renew
}

# Function to remove Node.js
remove_nodejs() {
    log "Removing Node.js..."
    
    # Remove global packages
    npm uninstall -g n yarn || true
    
    # Remove Node.js
    apt-get remove -y nodejs || true
    rm -rf /etc/apt/sources.list.d/nodesource.list
}

# Function to remove maintenance scripts
remove_maintenance() {
    log "Removing maintenance scripts..."
    
    # Remove cron jobs
    rm -f /etc/cron.d/incontrol-backup
    rm -f /etc/cron.d/incontrol-validate
    
    # Remove backup directory
    rm -rf /var/lib/incontrol/backups
}

# Function to remove application files
remove_application() {
    log "Removing application files..."
    
    # Remove application directories
    rm -rf /opt/incontrol
    rm -rf /var/log/incontrol
    rm -rf /var/lib/incontrol
    rm -rf /etc/incontrol
    
    # Remove application user
    userdel -r incontrol || true
}

# Function to remove installed packages
remove_packages() {
    log "Removing installed packages..."
    
    # Remove packages installed during setup
    apt-get remove -y \
        nginx certbot python3-certbot-nginx \
        mariadb-server \
        redis-server \
        postfix postfix-mysql dovecot-core dovecot-imapd dovecot-pop3d dovecot-mysql \
        bind9 bind9utils bind9-doc \
        prometheus node-exporter alertmanager \
        grafana \
        fail2ban \
        opendkim opendkim-tools \
        nginx-module-modsecurity libmodsecurity3 \
        modsecurity-crs \
        python3-pip python3-venv \
        libmariadb-dev \
        || true
    
    # Clean up unused packages
    apt-get autoremove -y
    apt-get clean
}

# Function to remove firewall rules
remove_firewall() {
    log "Removing firewall rules..."
    
    # Remove specific rules
    ufw delete allow ssh
    ufw delete allow http
    ufw delete allow https
    ufw delete allow 25/tcp
    ufw delete allow 587/tcp
    ufw delete allow 993/tcp
    ufw delete allow 995/tcp
    ufw delete allow 53/tcp
    ufw delete allow 53/udp
    ufw delete allow 9090/tcp
    ufw delete allow 9093/tcp
    ufw delete allow 9100/tcp
    ufw delete allow 3000/tcp
}

# Main uninstallation function
main() {
    log "Starting InControl uninstallation..."
    
    # Ask for confirmation
    read -p "This will remove InControl and all its components. Are you sure? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
    
    # Get domain from .env file if it exists
    if [ -f "/opt/incontrol/.env" ]; then
        DOMAIN=$(grep "DOMAIN=" /opt/incontrol/.env | cut -d'=' -f2)
    fi
    
    # Stop and remove services first
    remove_services
    
    # Remove components in reverse order of installation
    remove_maintenance
    remove_firewall
    remove_security
    remove_monitoring
    remove_grafana
    remove_dns
    remove_mail
    remove_mail_db
    remove_redis
    remove_web
    remove_database
    remove_nodejs
    remove_application
    
    # Remove packages last
    remove_packages
    
    log "Uninstallation completed successfully!"
    log "Your system has been restored to its state before InControl was installed."
    log "Note: Some system configurations and log files may still remain. Please review manually if needed."
}

# Run main uninstallation
main 