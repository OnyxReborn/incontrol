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
    error "Please run as root (sudo ./install.sh)"
fi

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    error "This script requires Ubuntu OS"
fi

# Add after initial checks
if [ -z "$DOMAIN" ]; then
    error "DOMAIN environment variable must be set"
    exit 1
fi

# Function to install Node.js
install_nodejs() {
    log "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    apt-get install -y nodejs

    # Clear npm cache and update npm without engine restrictions
    npm cache clean -f
    npm install -g npm@8.19.4 --force

    # Install n for Node.js version management
    npm install -g n
    
    # Install yarn as an alternative package manager
    npm install -g yarn
}

# Function to install and configure MySQL/MariaDB
setup_database() {
    log "Setting up database server..."
    apt-get install -y mariadb-server
    systemctl start mariadb
    systemctl enable mariadb

    # Secure MySQL installation
    mysql_secure_installation << EOF
n
y
y
y
y
y
EOF

    # Create database and user with more secure password handling
    local DB_PASSWORD=$(openssl rand -base64 32)
    mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    mysql -e "DROP USER IF EXISTS 'incontrol'@'localhost';"
    mysql -e "CREATE USER 'incontrol'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
    mysql -e "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';"
    mysql -e "FLUSH PRIVILEGES;"

    # Save database credentials to environment file
    {
        echo "DB_NAME=incontrol"
        echo "DB_USER=incontrol"
        echo "DB_PASSWORD=${DB_PASSWORD}"
        echo "DB_HOST=localhost"
    } >> /opt/incontrol/.env
}

# Function to install Python and dependencies
setup_python() {
    log "Setting up Python environment..."
    
    # Remove conflicting packages first
    apt-get remove -y libmysqlclient-dev || true
    apt-get autoremove -y
    
    # Install Python and build dependencies
    apt-get install -y python3 python3-pip python3-venv build-essential python3-dev \
        pkg-config libssl-dev libffi-dev

    # Install MariaDB development files specifically
    apt-get install -y libmariadb-dev

    # Create and activate virtual environment
    python3 -m venv /opt/incontrol/venv
    source /opt/incontrol/venv/bin/activate

    # Upgrade pip and install requirements
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
}

# Function to set up Nginx
setup_nginx() {
    log "Setting up Nginx..."
    apt-get install -y nginx certbot python3-certbot-nginx

    # Create directories for virtual hosts
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
    mkdir -p /var/www/vhosts
    chown -R www-data:www-data /var/www/vhosts
    chmod 755 /var/www/vhosts

    # Copy main Nginx configuration
    cp deployment/nginx/nginx.conf /etc/nginx/nginx.conf

    # Create virtual host configuration
    cat > /etc/nginx/sites-available/incontrol << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias /opt/incontrol/static/;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    location /media/ {
        alias /opt/incontrol/media/;
        expires 1h;
        add_header Cache-Control "public, no-transform";
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    # Enable the site
    ln -sf /etc/nginx/sites-available/incontrol /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default

    # Create SSL directory
    mkdir -p /etc/nginx/ssl
    chown -R root:root /etc/nginx/ssl
    chmod 700 /etc/nginx/ssl

    # Set up SSL certificate
    certbot --nginx -d ${DOMAIN} --non-interactive --agree-tos --email admin@${DOMAIN}

    # Set up certificate renewal
    echo "0 0 * * * root certbot renew --quiet" > /etc/cron.d/certbot-renew
    chmod 644 /etc/cron.d/certbot-renew

    systemctl restart nginx

    mkdir -p /etc/nginx/modules-enabled
    chown root:root /etc/nginx/modules-enabled
    chmod 755 /etc/nginx/modules-enabled
}

# Function to set up monitoring
setup_monitoring() {
    log "Setting up monitoring..."
    
    # Install Prometheus
    useradd -rs /bin/false prometheus || true
    mkdir -p /etc/prometheus /var/lib/prometheus
    curl -LO "https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz"
    tar xvf prometheus-*.tar.gz
    cp prometheus-*/prometheus /usr/local/bin/
    cp prometheus-*/promtool /usr/local/bin/
    cp -r prometheus-*/consoles /etc/prometheus
    cp -r prometheus-*/console_libraries /etc/prometheus
    rm -rf prometheus-*

    # Install Node Exporter
    useradd -rs /bin/false node_exporter || true
    curl -LO "https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz"
    tar xvf node_exporter-*.tar.gz
    cp node_exporter-*/node_exporter /usr/local/bin
    rm -rf node_exporter-*

    # Install AlertManager
    useradd -rs /bin/false alertmanager || true
    mkdir -p /etc/alertmanager /var/lib/alertmanager
    curl -LO "https://github.com/prometheus/alertmanager/releases/download/v0.25.0/alertmanager-0.25.0.linux-amd64.tar.gz"
    tar xvf alertmanager-*.tar.gz
    cp alertmanager-*/alertmanager /usr/local/bin/
    cp alertmanager-*/amtool /usr/local/bin/
    rm -rf alertmanager-*

    # Copy monitoring configurations
    cp -r deployment/prometheus/ /etc/prometheus/ || echo "Warning: Failed to copy Prometheus configs"
    cp -r deployment/alertmanager/ /etc/alertmanager/ || echo "Warning: Failed to copy AlertManager config"

    # Set permissions
    chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
    chown -R alertmanager:alertmanager /etc/alertmanager /var/lib/alertmanager

    # Copy and enable systemd services
    cp deployment/systemd/prometheus.service /etc/systemd/system/
    cp deployment/systemd/alertmanager.service /etc/systemd/system/
    cp deployment/systemd/node_exporter.service /etc/systemd/system/

    systemctl daemon-reload
    systemctl enable prometheus alertmanager node_exporter
    systemctl start prometheus alertmanager node_exporter
}

# Function to set up system services
setup_services() {
    log "Setting up system services..."
    
    # Copy systemd service files
    cp deployment/systemd/incontrol.service /etc/systemd/system/
    cp deployment/systemd/incontrol-worker.service /etc/systemd/system/
    cp deployment/systemd/incontrol-beat.service /etc/systemd/system/
    cp deployment/systemd/incontrol-ws.service /etc/systemd/system/

    systemctl daemon-reload
    systemctl enable incontrol incontrol-worker incontrol-beat incontrol-ws
    systemctl start incontrol incontrol-worker incontrol-beat incontrol-ws
}

# Function to set up Redis
setup_redis() {
    log "Setting up Redis..."
    
    # Install Redis
    apt-get install -y redis-server
    
    # Generate secure Redis password
    REDIS_PASSWORD=$(openssl rand -base64 32)
    
    # Copy and configure Redis
    cp deployment/redis/redis.conf /etc/redis/redis.conf
    sed -i "s/\${REDIS_PASSWORD}/$REDIS_PASSWORD/" /etc/redis/redis.conf
    
    # Create Redis directories
    mkdir -p /var/lib/redis
    mkdir -p /var/log/redis
    chown -R redis:redis /var/lib/redis /var/log/redis
    
    # Save Redis password to environment file
    echo "REDIS_PASSWORD=${REDIS_PASSWORD}" >> /opt/incontrol/.env
    
    # Start and enable Redis
    systemctl enable redis-server
    systemctl restart redis-server
}

# Function to set up mail server
setup_mail() {
    log "Setting up mail server..."
    
    # Install mail server packages
    apt-get install -y postfix postfix-mysql dovecot-core dovecot-imapd dovecot-pop3d dovecot-mysql
    
    # Create mail directories
    mkdir -p /var/mail/vhosts
    useradd -r -u 150 -g mail -d /var/mail/vhosts -s /sbin/nologin -c "Virtual mail user" vmail
    chown -R vmail:mail /var/mail/vhosts
    
    # Copy configurations
    cp deployment/mail/postfix-main.cf /etc/postfix/main.cf
    cp deployment/mail/dovecot.conf /etc/dovecot/dovecot.conf
    
    # Replace domain placeholder
    sed -i "s/\${DOMAIN}/$DOMAIN/" /etc/postfix/main.cf
    sed -i "s/\${DOMAIN}/$DOMAIN/" /etc/dovecot/dovecot.conf
    
    # Create SSL directories
    mkdir -p /etc/postfix/ssl
    mkdir -p /etc/dovecot/ssl
    chmod -R 0700 /etc/postfix/ssl /etc/dovecot/ssl
    
    # Start and enable services
    systemctl enable postfix dovecot
    systemctl restart postfix dovecot
}

# Function to set up DNS server
setup_dns() {
    log "Setting up DNS server..."
    
    # Install BIND
    apt-get install -y bind9 bind9utils bind9-doc
    
    # Create required directories
    mkdir -p /etc/bind/zones
    
    # Copy configurations
    cp deployment/bind/named.conf /etc/bind/
    cp deployment/bind/named.conf.options /etc/bind/
    cp deployment/bind/named.conf.local /etc/bind/
    cp -r /etc/bind/db.local /etc/bind/named.conf.default-zones
    
    # Set proper permissions
    chown -R bind:bind /etc/bind
    chmod -R 755 /etc/bind
    
    # Start and enable BIND
    systemctl enable bind9
    systemctl restart bind9

    mkdir -p /var/log/named
    chown bind:bind /var/log/named
    chmod 755 /var/log/named
}

# Function to set up UFW firewall
setup_firewall() {
    log "Configuring firewall..."
    
    # Install UFW
    apt-get install -y ufw
    
    # Set default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH (port 22)
    ufw allow ssh
    
    # Allow HTTP/HTTPS (ports 80, 443)
    ufw allow http
    ufw allow https
    
    # Allow mail ports (25, 587, 993, 995)
    ufw allow 25/tcp
    ufw allow 587/tcp
    ufw allow 993/tcp
    ufw allow 995/tcp
    
    # Allow DNS (port 53)
    ufw allow 53/tcp
    ufw allow 53/udp
    
    # Allow monitoring ports
    ufw allow 9090/tcp  # Prometheus
    ufw allow 9093/tcp  # AlertManager
    ufw allow 9100/tcp  # Node Exporter
    ufw allow 3000/tcp  # Grafana
    
    # Enable UFW
    echo "y" | ufw enable
}

# Function to set up Grafana
setup_grafana() {
    log "Setting up Grafana..."
    
    # Add Grafana repository
    apt-get install -y software-properties-common
    wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
    echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" | tee /etc/apt/sources.list.d/grafana.list
    apt-get update
    apt-get install -y grafana
    
    # Start and enable Grafana
    systemctl enable grafana-server
    systemctl start grafana-server
}

# Function to set up security enhancements
setup_security() {
    log "Setting up additional security measures..."
    
    # Install fail2ban
    apt-get install -y fail2ban
    cp deployment/fail2ban/jail.local /etc/fail2ban/jail.local
    systemctl enable fail2ban
    systemctl restart fail2ban
    
    # Install and configure OpenDKIM
    apt-get install -y opendkim opendkim-tools
    mkdir -p /etc/opendkim/keys/${DOMAIN}
    cp deployment/mail/opendkim.conf /etc/opendkim.conf
    
    # Generate DKIM keys
    opendkim-genkey -D /etc/opendkim/keys/${DOMAIN}/ -d ${DOMAIN} -s mail
    chown -R opendkim:opendkim /etc/opendkim
    
    # Install ModSecurity for Nginx
    apt-get install -y nginx-module-modsecurity libmodsecurity3
    mkdir -p /etc/nginx/modsecurity
    cp deployment/nginx/modsecurity.conf /etc/nginx/modsecurity/modsecurity.conf
    
    # Install OWASP Core Rule Set
    apt-get install -y modsecurity-crs
    
    # Update Nginx configuration to enable ModSecurity
    sed -i '/http {/a \    modsecurity on;\n    modsecurity_rules_file /etc/nginx/modsecurity/modsecurity.conf;' /etc/nginx/nginx.conf
    
    systemctl restart nginx
}

# Function to initialize mail database
setup_mail_db() {
    log "Setting up mail database..."
    
    # Generate secure password for mail database
    MAIL_DB_PASSWORD=$(openssl rand -base64 32)
    
    # Create database and tables
    mysql < deployment/mail/schema.sql
    
    # Save mail database password to environment file
    echo "MAIL_DB_PASSWORD=${MAIL_DB_PASSWORD}" >> /opt/incontrol/.env
}

# Function to set up backup and validation
setup_maintenance() {
    log "Setting up backup and validation..."
    
    # Copy maintenance scripts
    cp deployment/scripts/backup.sh /opt/incontrol/backup.sh
    cp deployment/scripts/validate.sh /opt/incontrol/validate.sh
    chmod +x /opt/incontrol/backup.sh /opt/incontrol/validate.sh
    
    # Create backup directories
    mkdir -p /var/lib/incontrol/backups
    chown -R incontrol:incontrol /var/lib/incontrol/backups
    chmod 750 /var/lib/incontrol/backups
    
    # Set up daily backup cron job
    echo "0 2 * * * /opt/incontrol/backup.sh > /var/log/incontrol/backup.log 2>&1" > /etc/cron.d/incontrol-backup
    chmod 644 /etc/cron.d/incontrol-backup
    
    # Set up weekly validation cron job
    echo "0 3 * * 0 /opt/incontrol/validate.sh > /var/log/incontrol/validate.log 2>&1" > /etc/cron.d/incontrol-validate
    chmod 644 /etc/cron.d/incontrol-validate
}

# Function to validate configuration before copying
validate_config() {
    local config_file=$1
    local config_type=$2
    
    case $config_type in
        "nginx")
            nginx -t -c "$config_file" >/dev/null 2>&1
            ;;
        "bind")
            named-checkconf "$config_file" >/dev/null 2>&1
            ;;
        "zone")
            named-checkzone example.com "$config_file" >/dev/null 2>&1
            ;;
        "systemd")
            systemd-analyze verify "$config_file" >/dev/null 2>&1
            ;;
        *)
            return 0
            ;;
    esac
    
    return $?
}

# Function to check service dependencies
check_service_dependencies() {
    local service=$1
    systemctl list-dependencies "$service" >/dev/null 2>&1 || {
        error "Failed to check dependencies for $service"
        return 1
    }
    return 0
}

# Add after creating InControl user
# Create all required directories with proper permissions
create_directories() {
    log "Creating required directories..."
    
    # Base directories
    mkdir -p /opt/incontrol/{venv,static,media,logs}
    mkdir -p /var/log/incontrol
    mkdir -p /var/lib/incontrol/backups
    mkdir -p /etc/incontrol
    
    # Web server directories
    mkdir -p /etc/nginx/{modules-enabled,sites-available,sites-enabled,ssl,modsecurity}
    mkdir -p /var/www/vhosts
    
    # Mail directories
    mkdir -p /var/mail/vhosts
    mkdir -p /etc/postfix/ssl
    mkdir -p /etc/dovecot/ssl
    
    # DNS directories
    mkdir -p /etc/bind/zones
    mkdir -p /var/log/named
    
    # Monitoring directories
    mkdir -p /etc/prometheus
    mkdir -p /var/lib/prometheus
    mkdir -p /etc/alertmanager
    mkdir -p /var/lib/alertmanager
    
    # Set proper permissions
    chown -R incontrol:incontrol /opt/incontrol /var/log/incontrol /var/lib/incontrol /etc/incontrol
    chown -R www-data:www-data /var/www/vhosts
    chown -R bind:bind /var/log/named
    chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
    chown -R alertmanager:alertmanager /etc/alertmanager /var/lib/alertmanager
    
    # Set directory permissions
    chmod 755 /opt/incontrol /var/log/incontrol /var/lib/incontrol /etc/incontrol
    chmod 755 /var/www/vhosts
    chmod 700 /etc/nginx/ssl /etc/postfix/ssl /etc/dovecot/ssl
    chmod 755 /var/log/named
    chmod 755 /etc/prometheus /var/lib/prometheus
    chmod 755 /etc/alertmanager /var/lib/alertmanager
}

# Function to generate secure password
generate_password() {
    openssl rand -base64 32
}

# Function to setup initial configuration
setup_initial_config() {
    log "Setting up initial configuration..."
    
    # Get domain if not set
    if [ -z "$DOMAIN" ]; then
        read -p "Enter your domain name (e.g., example.com): " DOMAIN
        if [ -z "$DOMAIN" ]; then
            error "Domain name is required"
        fi
    fi
    
    # Generate admin credentials
    ADMIN_PASSWORD=$(generate_password)
    
    # Save all credentials to .env file
    {
        echo "DOMAIN=${DOMAIN}"
        echo "ADMIN_EMAIL=admin@${DOMAIN}"
        echo "ADMIN_PASSWORD=${ADMIN_PASSWORD}"
    } > /opt/incontrol/.env
    
    chmod 600 /opt/incontrol/.env
    chown incontrol:incontrol /opt/incontrol/.env
}

# Function to setup frontend
setup_frontend() {
    log "Setting up frontend..."
    cd /opt/incontrol/frontend
    
    # Install dependencies
    npm install
    
    # Build frontend
    npm run build
    
    # Move build to static directory
    cp -r build/* /opt/incontrol/static/
    
    # Set permissions
    chown -R incontrol:incontrol /opt/incontrol/static
}

# Function to create admin user
create_admin_user() {
    log "Creating admin user..."
    source /opt/incontrol/venv/bin/activate
    cd /opt/incontrol
    
    # Create superuser
    python manage.py shell << EOF
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@${DOMAIN}', '${ADMIN_PASSWORD}')
EOF
    
    deactivate
}

# Main installation
main() {
    log "Starting InControl installation..."
    
    # Run pre-installation checks
    log "Running pre-installation checks..."
    if ! bash deployment/scripts/pre_install_check.sh; then
        error "Pre-installation checks failed. Please fix the issues and try again."
        exit 1
    fi
    
    # Setup initial configuration first
    setup_initial_config
    
    # Continue with existing installation steps
    apt-get update
    apt-get upgrade -y
    apt-get install -y curl wget git unzip
    
    # Create InControl user
    useradd -r -s /bin/bash -m -d /opt/incontrol incontrol || true
    
    # Create all required directories
    create_directories
    
    # Continue with rest of installation
    install_nodejs
    setup_database
    setup_python
    setup_nginx
    setup_redis
    setup_mail
    setup_mail_db
    setup_dns
    setup_monitoring
    setup_grafana
    setup_security
    setup_services
    setup_firewall
    setup_maintenance
    
    # Setup frontend and create admin user
    setup_frontend
    create_admin_user
    
    # Run initial validation
    log "Running initial system validation..."
    /opt/incontrol/validate.sh
    
    # Create initial backup
    log "Creating initial backup..."
    /opt/incontrol/backup.sh
    
    log "Installation completed successfully!"
    log "Please check /opt/incontrol/.env for your credentials"
    log "You can now login to the control panel at https://${DOMAIN}"
    log "Username: admin"
    log "Password: ${ADMIN_PASSWORD}"
    log "Daily backups will run at 2 AM and be stored in /var/lib/incontrol/backups"
    log "Weekly validation will run at 3 AM on Sundays"
}

# Run main installation
main 