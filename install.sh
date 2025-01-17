#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() {
    printf "${GREEN}[%s] %s${NC}\n" "$(date +'%Y-%m-%d %H:%M:%S')" "$1"
}

error() {
    printf "${RED}[ERROR] %s${NC}\n" "$1" >&2
    exit 1
}

warning() {
    printf "${YELLOW}[WARNING] %s${NC}\n" "$1"
}

# Function to generate secure passwords
generate_password() {
    < /dev/urandom tr -dc 'A-Za-z0-9!#$%&()*+,-./:;<=>?@[\]^_`{|}~' | head -c 32
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
        fail2ban \
        certbot \
        python3-certbot-nginx

    # Install Node Exporter
    log "Installing Node Exporter..."
    NODE_EXPORTER_VERSION="1.7.0"
    wget https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
    tar xvf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
    mv node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter /usr/local/bin/
    rm -rf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64*
    useradd -rs /bin/false node_exporter || true

    # Install Alertmanager
    log "Installing Alertmanager..."
    ALERTMANAGER_VERSION="0.26.0"
    wget https://github.com/prometheus/alertmanager/releases/download/v${ALERTMANAGER_VERSION}/alertmanager-${ALERTMANAGER_VERSION}.linux-amd64.tar.gz
    tar xvf alertmanager-${ALERTMANAGER_VERSION}.linux-amd64.tar.gz
    mv alertmanager-${ALERTMANAGER_VERSION}.linux-amd64/alertmanager /usr/local/bin/
    mv alertmanager-${ALERTMANAGER_VERSION}.linux-amd64/amtool /usr/local/bin/
    rm -rf alertmanager-${ALERTMANAGER_VERSION}.linux-amd64*
    useradd -rs /bin/false alertmanager || true
    mkdir -p /etc/alertmanager
    chown alertmanager:alertmanager /etc/alertmanager
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
            printf "Enter your domain name (e.g., example.com): "
            read -r DOMAIN
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
    cat > /opt/incontrol/.env << 'EOF'
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

# Function to setup Python environment
setup_python() {
    log "Setting up Python environment..."
    python3 -m venv /opt/incontrol/venv
    . /opt/incontrol/venv/bin/activate
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt
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

# Function to setup application
setup_application() {
    log "Setting up application..."
    
    # Copy application files
    cp -r incontrol/* /opt/incontrol/
    
    # Set up virtual environment and install dependencies
    setup_python
    
    # Apply database migrations
    cd /opt/incontrol
    . venv/bin/activate
    python manage.py migrate
    python manage.py collectstatic --noinput
}

# Function to setup services
setup_services() {
    log "Setting up services..."
    
    # Copy and enable systemd services
    cp deployment/systemd/*.service /etc/systemd/system/
    systemctl daemon-reload
    
    # Enable and start services
    systemctl enable --now nginx mariadb redis-server
    systemctl enable --now incontrol incontrol-worker incontrol-beat incontrol-ws
}

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then 
    error "Please run as root (sudo ./install.sh)"
fi

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    error "This script requires Ubuntu OS"
fi

log "Starting InControl installation..."

# Run installation steps
install_dependencies
setup_initial_config
create_directories
setup_database
setup_application
setup_services

log "Installation completed successfully!"
log "You can find your credentials in /opt/incontrol/.env"
