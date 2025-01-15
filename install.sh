#!/bin/bash

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to print colored messages
print_message() {
    echo -e "${GREEN}[InControl]${NC} $1"
}

print_error() {
    echo -e "${RED}[Error]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[Warning]${NC} $1"
}

# Function to check command status
check_status() {
    if [ $? -ne 0 ]; then
        print_error "$1"
        exit 1
    fi
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check required ports
check_ports() {
    local ports=("80" "443" "3306" "6379" "8000")
    for port in "${ports[@]}"; do
        if netstat -tuln | grep -q ":$port "; then
            print_warning "Port $port is already in use. Please ensure it's not being used by another application."
            read -p "Continue anyway? (y/n) [n]: " continue_install
            continue_install=${continue_install:-n}
            if [ "$continue_install" != "y" ]; then
                exit 1
            fi
        fi
    done
}

# Function to check system resources
check_resources() {
    # Check RAM
    local total_ram=$(free -m | awk '/^Mem:/{print $2}')
    if [ $total_ram -lt 1024 ]; then
        print_warning "System has less than 1GB RAM. This may affect performance."
        read -p "Continue anyway? (y/n) [n]: " continue_install
        continue_install=${continue_install:-n}
        if [ "$continue_install" != "y" ]; then
            exit 1
        fi
    fi

    # Check disk space
    local free_space=$(df -m /opt | awk 'NR==2 {print $4}')
    if [ $free_space -lt 5120 ]; then
        print_warning "Less than 5GB free space available. This may not be sufficient."
        read -p "Continue anyway? (y/n) [n]: " continue_install
        continue_install=${continue_install:-n}
        if [ "$continue_install" != "y" ]; then
            exit 1
        fi
    fi
}

# Function to validate domain name
validate_domain() {
    local domain=$1
    if [[ ! $domain =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$ ]] && [ "$domain" != "localhost" ]; then
        print_error "Invalid domain name format"
        return 1
    fi
    return 0
}

# Function to check and install dependencies
install_dependencies() {
    local deps=("python3" "pip" "nodejs" "npm" "redis-server" "nginx" "mysql-server")
    for dep in "${deps[@]}"; do
        if ! command_exists $dep; then
            print_message "Installing $dep..."
            apt install -y $dep || {
                print_error "Failed to install $dep"
                exit 1
            }
        fi
    done
}

# Function to backup existing installation
backup_existing() {
    if [ -d "$INSTALL_DIR" ]; then
        local backup_dir="/opt/incontrol_backup_$(date +%Y%m%d_%H%M%S)"
        print_warning "Existing installation found. Creating backup at $backup_dir"
        mv "$INSTALL_DIR" "$backup_dir" || {
            print_error "Failed to create backup"
            exit 1
        }
    fi
}

# Trap errors
trap 'print_error "An error occurred during installation. Check the error message above."; exit 1' ERR

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root"
    exit 1
fi

# Welcome message
clear
echo "=================================================="
echo "          InControl Panel Installation"
echo "=================================================="
echo ""

# Check system requirements
print_message "Checking system requirements..."

# Check Ubuntu version
if ! grep -q "Ubuntu" /etc/os-release; then
    print_error "This installer is only for Ubuntu systems"
    exit 1
fi

# Check minimum Ubuntu version
ubuntu_version=$(lsb_release -rs)
if (( $(echo "$ubuntu_version < 20.04" | bc -l) )); then
    print_error "Ubuntu version 20.04 or higher is required"
    exit 1
fi

# Check system resources
check_resources

# Check required ports
check_ports

# Backup existing installation
backup_existing

# Git repository setup
print_message "Setting up Git repository..."
REPO_URL="https://github.com/OnyxReborn/panelmain.git"
INSTALL_DIR="/opt/incontrol"

if [ ! -d "$INSTALL_DIR" ]; then
    git clone $REPO_URL $INSTALL_DIR || {
        print_error "Failed to clone repository"
        exit 1
    }
    cd $INSTALL_DIR
else
    cd $INSTALL_DIR
    if [ ! -d ".git" ]; then
        git init
        git remote add origin $REPO_URL
    fi
    git fetch origin || {
        print_error "Failed to fetch from repository"
        exit 1
    }
    git checkout -B main origin/main || {
        print_error "Failed to checkout main branch"
        exit 1
    }
fi

# Install system dependencies
print_message "Installing system dependencies..."
apt update
apt install -y python3-pip python3-venv redis-server nginx mysql-server curl software-properties-common

# Install Node.js
print_message "Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
apt install -y nodejs

# Database configuration
print_message "Configuring database..."
read -p "Enter database name [incontrol]: " db_name
db_name=${db_name:-incontrol}

read -p "Enter database user [incontrol]: " db_user
db_user=${db_user:-incontrol}

read -s -p "Enter database password: " db_password
echo
read -s -p "Confirm database password: " db_password_confirm
echo

if [ "$db_password" != "$db_password_confirm" ]; then
    print_error "Passwords do not match"
    exit 1
fi

# Create database and user
mysql -e "CREATE DATABASE IF NOT EXISTS ${db_name};"
mysql -e "CREATE USER IF NOT EXISTS '${db_user}'@'localhost' IDENTIFIED BY '${db_password}';"
mysql -e "GRANT ALL PRIVILEGES ON ${db_name}.* TO '${db_user}'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# Web server configuration
print_message "Configuring web server..."
read -p "Enter domain name (e.g., panel.example.com) [localhost]: " domain_name
domain_name=${domain_name:-localhost}

read -p "Enable HTTPS? (y/n) [y]: " enable_https
enable_https=${enable_https:-y}

if [ "$enable_https" = "y" ]; then
    # Install certbot
    apt install -y certbot python3-certbot-nginx
fi

# Email configuration
print_message "Configuring email settings..."
read -p "Configure email settings now? (y/n) [y]: " configure_email
configure_email=${configure_email:-y}

if [ "$configure_email" = "y" ]; then
    read -p "SMTP Host [localhost]: " smtp_host
    smtp_host=${smtp_host:-localhost}
    
    read -p "SMTP Port [587]: " smtp_port
    smtp_port=${smtp_port:-587}
    
    read -p "SMTP User: " smtp_user
    read -s -p "SMTP Password: " smtp_password
    echo
    
    read -p "Use TLS? (y/n) [y]: " use_tls
    use_tls=${use_tls:-y}
fi

# Create installation directory
INSTALL_DIR="/opt/incontrol"
print_message "Creating installation directory..."
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# Set up Python virtual environment
print_message "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
print_message "Installing Python dependencies..."
pip install -r requirements.txt

# Generate Django secret key
SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Create environment file
print_message "Creating environment configuration..."
cat > .env << EOL
DEBUG=False
DJANGO_SECRET_KEY='${SECRET_KEY}'
ALLOWED_HOSTS=${domain_name},localhost,127.0.0.1

DB_NAME=${db_name}
DB_USER=${db_user}
DB_PASSWORD=${db_password}
DB_HOST=localhost
DB_PORT=3306

REDIS_HOST=localhost
REDIS_PORT=6379

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

EMAIL_HOST=${smtp_host}
EMAIL_PORT=${smtp_port}
EMAIL_HOST_USER=${smtp_user}
EMAIL_HOST_PASSWORD=${smtp_password}
EMAIL_USE_TLS=${use_tls}
EOL

# Install and build frontend
print_message "Setting up frontend..."
cd frontend
npm install
npm run build
cd ..

# Create systemd services
print_message "Creating system services..."

# Django service
cat > /etc/systemd/system/incontrol.service << EOL
[Unit]
Description=InControl Panel
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/incontrol
Environment="PATH=/opt/incontrol/venv/bin"
ExecStart=/opt/incontrol/venv/bin/gunicorn incontrol.wsgi:application --bind unix:/run/incontrol.sock
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Celery worker service
cat > /etc/systemd/system/incontrol-worker.service << EOL
[Unit]
Description=InControl Celery Worker
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/incontrol
Environment="PATH=/opt/incontrol/venv/bin"
ExecStart=/opt/incontrol/venv/bin/celery -A incontrol worker -l info
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Celery beat service
cat > /etc/systemd/system/incontrol-beat.service << EOL
[Unit]
Description=InControl Celery Beat
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/incontrol
Environment="PATH=/opt/incontrol/venv/bin"
ExecStart=/opt/incontrol/venv/bin/celery -A incontrol beat -l info
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Configure nginx
print_message "Configuring nginx..."
cat > /etc/nginx/sites-available/incontrol << EOL
server {
    listen 80;
    server_name ${domain_name};

    location / {
        root /opt/incontrol/frontend/build;
        try_files \$uri \$uri/ /index.html;
    }

    location /api {
        proxy_pass http://unix:/run/incontrol.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /ws {
        proxy_pass http://unix:/run/incontrol.sock;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }
}
EOL

ln -sf /etc/nginx/sites-available/incontrol /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Set permissions
print_message "Setting permissions..."
chown -R www-data:www-data $INSTALL_DIR
chmod -R 755 $INSTALL_DIR

# Initialize database
print_message "Initializing database..."
source venv/bin/activate
python manage.py migrate

# Create superuser
print_message "Creating admin user..."
read -p "Enter admin username [admin]: " admin_user
admin_user=${admin_user:-admin}

read -s -p "Enter admin password: " admin_password
echo
read -s -p "Confirm admin password: " admin_password_confirm
echo

if [ "$admin_password" != "$admin_password_confirm" ]; then
    print_error "Passwords do not match"
    exit 1
fi

python manage.py shell << EOF
from django.contrib.auth.models import User
User.objects.create_superuser('${admin_user}', '', '${admin_password}')
EOF

# Start and enable services
print_message "Starting services..."
systemctl daemon-reload
systemctl enable --now redis-server
systemctl enable --now incontrol
systemctl enable --now incontrol-worker
systemctl enable --now incontrol-beat
systemctl enable --now nginx

# Configure HTTPS if requested
if [ "$enable_https" = "y" ]; then
    print_message "Configuring HTTPS..."
    certbot --nginx -d $domain_name --non-interactive --agree-tos --email admin@$domain_name
fi

# Add cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        print_error "Installation failed. Cleaning up..."
        # Stop services
        systemctl stop incontrol incontrol-worker incontrol-beat nginx 2>/dev/null || true
        # Remove services
        rm -f /etc/systemd/system/incontrol*.service 2>/dev/null || true
        # Remove nginx config
        rm -f /etc/nginx/sites-enabled/incontrol 2>/dev/null || true
        rm -f /etc/nginx/sites-available/incontrol 2>/dev/null || true
        # Reload systemd
        systemctl daemon-reload
        # Restart nginx
        systemctl restart nginx
        print_message "Cleanup complete. Please check the error messages above and try again."
    fi
}

# Register cleanup function
trap cleanup EXIT

# Add service health checks at the end
print_message "Performing final health checks..."

# Check if services are running
services=("redis-server" "incontrol" "incontrol-worker" "incontrol-beat" "nginx")
for service in "${services[@]}"; do
    if ! systemctl is-active --quiet $service; then
        print_warning "Service $service is not running"
        systemctl status $service
    fi
done

# Test nginx configuration
nginx -t || {
    print_error "Nginx configuration test failed"
    exit 1
}

# Test database connection
source venv/bin/activate
python manage.py check --database default || {
    print_error "Database connection test failed"
    exit 1
}

print_message "Installation complete!"
echo "=================================================="
echo "You can now access InControl Panel at: http://${domain_name}"
if [ "$enable_https" = "y" ]; then
    echo "or https://${domain_name}"
fi
echo ""
echo "Admin username: ${admin_user}"
echo ""
echo "Important: Please save your credentials in a secure location"
echo "=================================================="

# Add final security recommendations
print_message "Security Recommendations:"
echo "1. Change the default MySQL root password"
echo "2. Configure firewall rules (UFW)"
echo "3. Set up regular backups"
echo "4. Keep the system updated regularly"
echo "5. Monitor the logs in /var/log/incontrol/" 