#!/bin/bash

# Exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root${NC}"
    exit 1
fi

echo -e "${GREEN}Starting InControl installation...${NC}"

# Update system
echo -e "${GREEN}Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

# Install system dependencies
echo -e "${GREEN}Installing system dependencies...${NC}"
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    nodejs \
    npm \
    nginx \
    redis-server \
    mariadb-server \
    supervisor \
    certbot \
    python3-certbot-nginx \
    git \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    default-libmysqlclient-dev

# Create incontrol user and group
echo -e "${GREEN}Creating incontrol user...${NC}"
useradd -r -s /bin/false incontrol || true
usermod -d /opt/incontrol incontrol

# Create installation directory
echo -e "${GREEN}Creating installation directory...${NC}"
mkdir -p /opt/incontrol
chown incontrol:incontrol /opt/incontrol

# Copy project files
echo -e "${GREEN}Copying project files...${NC}"
cp -r . /opt/incontrol/
chown -R incontrol:incontrol /opt/incontrol

# Set up Python virtual environment
echo -e "${GREEN}Setting up Python virtual environment...${NC}"
cd /opt/incontrol
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Set up frontend
echo -e "${GREEN}Setting up frontend...${NC}"
cd frontend
npm install
npm run build
cd ..

# Configure MySQL
echo -e "${GREEN}Configuring MySQL...${NC}"
mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS 'incontrol'@'localhost' IDENTIFIED BY 'temporary-password';"
mysql -e "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# Copy configuration files
echo -e "${GREEN}Setting up configuration files...${NC}"
cp deployment/nginx/incontrol.conf /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/incontrol.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Copy systemd service files
cp deployment/systemd/*.service /etc/systemd/system/
systemctl daemon-reload

# Create required directories
mkdir -p /opt/incontrol/{static,media,backups,logs}
chown -R incontrol:incontrol /opt/incontrol

# Set up environment file
cp .env.example .env
echo -e "${GREEN}Please edit /opt/incontrol/.env with your configuration${NC}"

# Django setup
echo -e "${GREEN}Running Django migrations...${NC}"
source venv/bin/activate
python manage.py collectstatic --noinput
python manage.py migrate

# Start services
echo -e "${GREEN}Starting services...${NC}"
systemctl enable nginx
systemctl enable redis-server
systemctl enable incontrol
systemctl enable incontrol-worker
systemctl enable incontrol-beat
systemctl enable incontrol-daphne

systemctl start nginx
systemctl start redis-server
systemctl start incontrol
systemctl start incontrol-worker
systemctl start incontrol-beat
systemctl start incontrol-daphne

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${GREEN}Please:${NC}"
echo "1. Edit /opt/incontrol/.env with your configuration"
echo "2. Update the MySQL password in .env"
echo "3. Set up SSL certificates using: certbot --nginx -d your-domain.com"
echo "4. Create a superuser using: python manage.py createsuperuser"
echo "5. Access the panel at: https://your-domain.com" 