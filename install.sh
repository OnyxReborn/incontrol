#!/bin/bash

# Exit on error
set -e

echo "InControl Panel Installation Script"
echo "================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    nginx \
    redis-server \
    mysql-server \
    mysql-client \
    libmysqlclient-dev \
    python3-dev \
    build-essential \
    nodejs \
    npm \
    git \
    supervisor \
    ufw

# Create application directory
echo "Creating application directory..."
APP_DIR="/opt/incontrol"
mkdir -p $APP_DIR

# Copy current directory contents to APP_DIR
echo "Copying application files..."
cp -r ./* $APP_DIR/
cd $APP_DIR

# Create Python virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install and build frontend
echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

# Configure MySQL
echo "Configuring MySQL..."
mysql_secure_installation

# Create database and user
echo "Creating database..."
read -p "Enter MySQL root password: " MYSQL_ROOT_PASSWORD
read -p "Enter new password for incontrol database user: " INCONTROL_DB_PASSWORD

mysql -u root -p${MYSQL_ROOT_PASSWORD} <<EOF
CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'incontrol'@'localhost' IDENTIFIED BY '${INCONTROL_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';
FLUSH PRIVILEGES;
EOF

# Configure Nginx
echo "Configuring Nginx..."
cat > /etc/nginx/sites-available/incontrol <<EOF
server {
    listen 80;
    server_name _;

    location / {
        root $APP_DIR/frontend/build;
        try_files \$uri \$uri/ /index.html;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
    }

    location /static/ {
        alias $APP_DIR/static/;
    }

    location /media/ {
        alias $APP_DIR/media/;
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/incontrol /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# Configure Supervisor
echo "Configuring Supervisor..."
cat > /etc/supervisor/conf.d/incontrol.conf <<EOF
[program:incontrol]
command=$APP_DIR/venv/bin/daphne -b 127.0.0.1 -p 8000 incontrol.asgi:application
directory=$APP_DIR
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/incontrol.log

[program:incontrol-celery]
command=$APP_DIR/venv/bin/celery -A incontrol worker -l info
directory=$APP_DIR
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/incontrol-celery.log

[program:incontrol-beat]
command=$APP_DIR/venv/bin/celery -A incontrol beat -l info
directory=$APP_DIR
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/incontrol-beat.log
EOF

# Update supervisor
supervisorctl reread
supervisorctl update

# Configure firewall
echo "Configuring firewall..."
ufw allow 'Nginx Full'
ufw allow ssh
ufw --force enable

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p $APP_DIR/static
mkdir -p $APP_DIR/media
mkdir -p $APP_DIR/backups
chown -R www-data:www-data $APP_DIR

# Create environment file
echo "Creating environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    # Update database password in .env
    sed -i "s/your-db-password-here/${INCONTROL_DB_PASSWORD}/g" .env
    # Generate a random secret key
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
    sed -i "s/your-secret-key-here/${SECRET_KEY}/g" .env
    echo "Please review and update the .env file with your configuration"
    echo "Press any key to continue..."
    read -n 1
fi

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser
echo "Creating superuser..."
python manage.py createsuperuser

# Final steps
echo "Installation completed!"
echo "Please complete these final steps:"
echo "1. Review the .env file at $APP_DIR/.env"
echo "2. Restart the services: sudo supervisorctl restart all"
echo "3. Access the control panel at http://your_server_ip"
echo "4. Log in with the superuser credentials you just created"

# Installation complete
echo "InControl Panel has been installed successfully!" 