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

    # Create database and user
    local DB_PASSWORD=$(openssl rand -base64 32)
    mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    mysql -e "CREATE USER IF NOT EXISTS 'incontrol'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';"
    mysql -e "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';"
    mysql -e "FLUSH PRIVILEGES;"

    # Save database credentials
    echo "DB_PASSWORD=${DB_PASSWORD}" >> /opt/incontrol/.env
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

    # Create Nginx configuration
    cat > /etc/nginx/sites-available/incontrol << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias /opt/incontrol/static/;
    }

    location /media/ {
        alias /opt/incontrol/media/;
    }
}
EOF

    # Enable the site
    ln -sf /etc/nginx/sites-available/incontrol /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    systemctl restart nginx
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
    cp -r deployment/prometheus/* /etc/prometheus/
    cp -r deployment/alertmanager/* /etc/alertmanager/

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
    
    # Create systemd services
    cat > /etc/systemd/system/incontrol.service << EOF
[Unit]
Description=InControl Web Panel
After=network.target

[Service]
User=incontrol
Group=incontrol
WorkingDirectory=/opt/incontrol
ExecStart=/opt/incontrol/venv/bin/gunicorn incontrol.wsgi:application -b 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/incontrol-worker.service << EOF
[Unit]
Description=InControl Celery Worker
After=network.target

[Service]
User=incontrol
Group=incontrol
WorkingDirectory=/opt/incontrol
ExecStart=/opt/incontrol/venv/bin/celery -A incontrol worker -l INFO
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/incontrol-beat.service << EOF
[Unit]
Description=InControl Celery Beat
After=network.target

[Service]
User=incontrol
Group=incontrol
WorkingDirectory=/opt/incontrol
ExecStart=/opt/incontrol/venv/bin/celery -A incontrol beat -l INFO
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable incontrol incontrol-worker incontrol-beat
    systemctl start incontrol incontrol-worker incontrol-beat
}

# Main installation
log "Starting InControl installation..."

# Update system
log "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install basic requirements
apt-get install -y curl wget git supervisor redis-server

# Create incontrol user
useradd -r -s /bin/false incontrol || true
usermod -d /opt/incontrol incontrol

# Create installation directory
mkdir -p /opt/incontrol
chown incontrol:incontrol /opt/incontrol

# Clone repository if not already present
if [ ! -d "/opt/incontrol/.git" ]; then
    git clone https://github.com/OnyxReborn/panelmain.git /opt/incontrol
fi

cd /opt/incontrol

# Install components
install_nodejs
setup_database
setup_python
setup_nginx
setup_monitoring
setup_services

# Generate Django secret key
DJANGO_SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
echo "DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}" >> /opt/incontrol/.env

# Set up frontend
cd frontend
npm install
npm run build
cd ..

# Collect static files
source venv/bin/activate
python manage.py collectstatic --noinput
python manage.py migrate

# Create superuser
python manage.py shell << EOF
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
EOF

# Set proper permissions
chown -R incontrol:incontrol /opt/incontrol

# Configure firewall
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# Final message
log "Installation complete!"
log "You can now access:"
log "- Control Panel: http://your-server-ip"
log "- Prometheus: http://your-server-ip:9090"
log "- AlertManager: http://your-server-ip:9093"
log ""
log "Default admin credentials:"
log "Username: admin"
log "Password: admin"
log ""
log "IMPORTANT: Please change the admin password immediately!"
log "Database credentials have been saved to /opt/incontrol/.env" 