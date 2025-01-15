#!/bin/bash

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

print_message "Installation complete!"
echo "=================================================="
echo "You can now access InControl Panel at: http://${domain_name}"
if [ "$enable_https" = "y" ]; then
    echo "or https://${domain_name}"
fi
echo ""
echo "Admin username: ${admin_user}"
echo "==================================================" 