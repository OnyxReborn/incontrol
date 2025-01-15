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

# Function to check if a service exists
service_exists() {
    systemctl list-unit-files | grep -q "^$1\.service"
}

# Function to safely stop and disable a service
stop_service() {
    if service_exists "$1"; then
        log "Stopping and disabling $1 service..."
        systemctl stop "$1" 2>/dev/null || true
        systemctl disable "$1" 2>/dev/null || true
    fi
}

# Function to clean up previous installation
cleanup_previous_install() {
    log "Cleaning up previous installation..."
    
    # Stop all related services
    local services=(
        "incontrol"
        "incontrol-worker"
        "incontrol-beat"
        "incontrol-daphne"
        "prometheus"
        "alertmanager"
        "node_exporter"
    )
    
    for service in "${services[@]}"; do
        stop_service "$service"
    done

    # Remove service files
    rm -f /etc/systemd/system/incontrol*.service
    rm -f /etc/systemd/system/prometheus.service
    rm -f /etc/systemd/system/alertmanager.service
    rm -f /etc/systemd/system/node_exporter.service
    systemctl daemon-reload

    # Backup existing installation if it exists
    if [ -d "/opt/incontrol" ]; then
        local backup_dir="/opt/incontrol_backup_$(date +%Y%m%d_%H%M%S)"
        log "Backing up existing installation to $backup_dir"
        cp -r /opt/incontrol "$backup_dir"
        
        # Preserve important data
        if [ -d "/opt/incontrol/backups" ]; then
            mv /opt/incontrol/backups "$backup_dir/backups"
        fi
        if [ -d "/opt/incontrol/media" ]; then
            mv /opt/incontrol/media "$backup_dir/media"
        fi
        
        # Remove old installation
        rm -rf /opt/incontrol/*
    fi

    # Clean up Python virtual environment
    if [ -d "/opt/incontrol/venv" ]; then
        rm -rf /opt/incontrol/venv
    fi

    # Clean up Node modules
    if [ -d "/opt/incontrol/frontend/node_modules" ]; then
        rm -rf /opt/incontrol/frontend/node_modules
    fi

    # Remove old Nginx configs
    rm -f /etc/nginx/sites-enabled/incontrol.conf
    rm -f /etc/nginx/sites-available/incontrol.conf

    # Clean up monitoring
    rm -rf /etc/prometheus
    rm -rf /etc/alertmanager
    rm -rf /var/lib/prometheus
    rm -rf /var/lib/alertmanager

    # Clean up logs
    rm -rf /var/log/incontrol/*

    # Remove old logrotate config
    rm -f /etc/logrotate.d/incontrol
}

# Function to check and fix package conflicts
fix_package_conflicts() {
    log "Checking for package conflicts..."
    
    # List of potentially conflicting packages
    local conflict_packages=(
        "python3-django"
        "python3-celery"
        "prometheus"
        "prometheus-node-exporter"
        "prometheus-alertmanager"
    )

    # Remove conflicting packages
    for package in "${conflict_packages[@]}"; do
        if dpkg -l | grep -q "^ii  $package "; then
            log "Removing conflicting package: $package"
            apt-get remove -y "$package" || warning "Failed to remove $package"
        fi
    done

    # Clean up package manager
    apt-get autoremove -y
    apt-get clean
}

# Function to check system requirements
check_system_requirements() {
    log "Checking system requirements..."
    
    # Check available disk space (minimum 5GB)
    local available_space=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$available_space" -lt 5 ]; then
        error "Insufficient disk space. At least 5GB required, $available_space""GB available"
    fi

    # Check available memory (minimum 2GB)
    local total_mem=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$total_mem" -lt 2 ]; then
        error "Insufficient memory. At least 2GB required, $total_mem""GB available"
    fi

    # Check if ports are available
    local required_ports=(80 443 8000 9090 9093 9100 6379 3306)
    for port in "${required_ports[@]}"; do
        if netstat -tuln | grep -q ":$port "; then
            warning "Port $port is already in use. This might cause conflicts."
        fi
    done
}

# Function to handle Python package conflicts
setup_python_environment() {
    log "Setting up Python environment..."
    
    # Create fresh virtual environment
    python3 -m venv venv
    source venv/bin/activate

    # Upgrade pip and setuptools
    pip install --upgrade pip setuptools wheel || error "Failed to upgrade pip and setuptools"

    # Install packages one by one to better handle conflicts
    log "Installing Python dependencies..."
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments and empty lines
        [[ $line =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        
        package_name=$(echo "$line" | cut -d'=' -f1)
        log "Installing $package_name..."
        
        # Try to install the package
        if ! pip install "$line" 2>/dev/null; then
            warning "Failed to install $line with exact version, trying without version..."
            if ! pip install "$package_name" 2>/dev/null; then
                error "Failed to install $package_name"
            fi
        fi
    done < requirements.txt

    # Verify critical packages
    critical_packages=(
        "django"
        "celery"
        "channels"
        "mysqlclient"
        "redis"
    )

    for package in "${critical_packages[@]}"; do
        if ! pip show "$package" >/dev/null 2>&1; then
            error "Critical package $package is not installed"
        fi
    done
}

# Function to handle database migration
handle_database_migration() {
    log "Handling database migration..."
    
    # Check if database exists
    if mysql -e "USE incontrol" 2>/dev/null; then
        log "Database exists, backing up..."
        
        # Create backup directory
        backup_dir="/opt/incontrol/backups/db_backup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        # Backup existing database
        mysqldump incontrol > "$backup_dir/incontrol_backup.sql" || warning "Failed to backup database"
        
        # Check for conflicting migrations
        if python manage.py showmigrations | grep -q "\[ \]"; then
            warning "Found unapplied migrations"
            
            # Try to fix migrations
            log "Attempting to fix migrations..."
            python manage.py migrate --fake-initial || warning "Failed to fake initial migrations"
        fi
    else
        log "Creating new database..."
        mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    fi
    
    # Apply migrations
    log "Applying database migrations..."
    python manage.py migrate || error "Failed to apply migrations"
    
    # Verify database connection
    if ! python manage.py check --database default; then
        error "Database connection check failed"
    fi
}

# Version requirements
REQUIRED_PYTHON_VERSION="3.8.0"
REQUIRED_NODE_VERSION="14.0.0"
REQUIRED_MYSQL_VERSION="8.0.0"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    error "Please run as root"
fi

log "Starting InControl installation..."

# Run cleanup and checks
cleanup_previous_install
fix_package_conflicts
check_system_requirements

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
if ! command -v python3 &> /dev/null; then
    error "Python3 is not installed"
fi
if ! python3 -c "import sys; exit(0) if sys.version_info >= tuple(map(int, '${REQUIRED_PYTHON_VERSION}'.split('.'))) else exit(1)"; then
    error "Python version must be >= ${REQUIRED_PYTHON_VERSION}"
fi

# Check Node.js version
if ! command -v node &> /dev/null; then
    error "Node.js is not installed"
fi
NODE_VERSION=$(node -v | cut -d 'v' -f 2)
if ! node -e "process.exit(process.version.localeCompare('v${REQUIRED_NODE_VERSION}', undefined, { numeric: true }) >= 0 ? 0 : 1)"; then
    error "Node.js version must be >= ${REQUIRED_NODE_VERSION}"
fi

# Backup existing configurations
log "Backing up existing configurations..."
BACKUP_DIR="/root/incontrol_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
[ -f /etc/nginx/nginx.conf ] && cp /etc/nginx/nginx.conf "$BACKUP_DIR/"
[ -d /etc/nginx/sites-available ] && cp -r /etc/nginx/sites-available "$BACKUP_DIR/"

# Update system
log "Updating system packages..."
apt-get update || error "Failed to update package list"
apt-get upgrade -y || error "Failed to upgrade packages"

# Install system dependencies
log "Installing system dependencies..."
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
    default-libmysqlclient-dev \
    logrotate \
    ufw \
    fail2ban || error "Failed to install dependencies"

# Configure firewall
log "Configuring firewall..."
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# Configure fail2ban
log "Configuring fail2ban..."
cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
systemctl enable fail2ban
systemctl start fail2ban

# Create incontrol user and group
log "Creating incontrol user..."
useradd -r -s /bin/false incontrol || true
usermod -d /opt/incontrol incontrol

# Create installation directory
log "Creating installation directory..."
mkdir -p /opt/incontrol
chown incontrol:incontrol /opt/incontrol

# Set up directory structure
log "Setting up directory structure..."
mkdir -p /opt/incontrol/{static,media,backups,logs,ssl,configs}
mkdir -p /var/log/incontrol

# Configure logrotate
cat > /etc/logrotate.d/incontrol << EOF
/var/log/incontrol/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 incontrol incontrol
    sharedscripts
    postrotate
        systemctl reload incontrol >/dev/null 2>&1 || true
    endscript
}
EOF

# Copy project files
log "Copying project files..."
cp -r . /opt/incontrol/
chown -R incontrol:incontrol /opt/incontrol

# Set up Python virtual environment
log "Setting up Python virtual environment..."
cd /opt/incontrol
setup_python_environment || error "Failed to set up Python environment"

# Function to handle Node.js installation
setup_nodejs() {
    log "Setting up Node.js and npm..."
    
    # Remove existing Node.js and npm if installed
    if dpkg -l | grep -q nodejs || dpkg -l | grep -q npm; then
        log "Removing existing Node.js and npm installations..."
        apt-get remove -y nodejs npm || true
        apt-get autoremove -y
    fi

    # Remove nodesource if exists
    rm -f /etc/apt/sources.list.d/nodesource.list*

    # Clean apt cache
    apt-get clean
    rm -rf /var/lib/apt/lists/*
    apt-get update

    # Install curl if not installed
    if ! command -v curl &> /dev/null; then
        apt-get install -y curl
    fi

    # Add NodeSource repository (for Node.js 18.x LTS)
    log "Adding NodeSource repository..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -

    # Add Yarn repository
    log "Adding Yarn repository..."
    curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -
    echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list

    # Update package list
    apt-get update

    # Install Node.js and npm
    log "Installing Node.js and npm..."
    if ! apt-get install -y nodejs; then
        # If installation fails, try alternative approach
        log "Standard installation failed, trying alternative approach..."
        
        # Download and install Node.js manually
        local NODE_VERSION="18.19.0"  # Latest LTS version
        local ARCH=$(dpkg --print-architecture)
        local NODE_DOWNLOAD="node-v${NODE_VERSION}-linux-${ARCH}.tar.xz"
        
        cd /tmp
        curl -O "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_DOWNLOAD}"
        tar -xf "${NODE_DOWNLOAD}"
        
        # Copy Node.js files to system
        cd "node-v${NODE_VERSION}-linux-${ARCH}"
        cp -r bin/* /usr/local/bin/
        cp -r lib/* /usr/local/lib/
        cp -r include/* /usr/local/include/
        cp -r share/* /usr/local/share/
        
        # Clean up
        cd ..
        rm -rf "node-v${NODE_VERSION}-linux-${ARCH}" "${NODE_DOWNLOAD}"
    fi

    # Verify installation
    if ! command -v node &> /dev/null; then
        error "Failed to install Node.js"
    fi
    if ! command -v npm &> /dev/null; then
        error "Failed to install npm"
    fi

    # Update npm to latest version
    log "Updating npm..."
    npm install -g npm@latest

    # Install essential global packages
    log "Installing essential npm packages..."
    npm install -g yarn
    npm install -g n
    
    # Install build tools
    apt-get install -y build-essential python3-dev
    
    log "Node.js setup completed"
    log "Node.js version: $(node -v)"
    log "npm version: $(npm -v)"
}

# Function to handle frontend setup with retry logic
setup_frontend() {
    log "Setting up frontend..."
    cd frontend || error "Frontend directory not found"
    
    # Clear existing node_modules and package-lock.json
    rm -rf node_modules package-lock.json

    # Try yarn first
    log "Attempting to install dependencies with yarn..."
    if command -v yarn &> /dev/null; then
        yarn install --network-timeout 100000 || {
            warning "Yarn install failed, falling back to npm..."
            
            # Try npm with various fallback options
            for attempt in {1..3}; do
                log "npm install attempt $attempt..."
                
                case $attempt in
                    1)
                        # Standard install
                        if npm install; then
                            break
                        fi
                        ;;
                    2)
                        # Try with legacy peer deps
                        if npm install --legacy-peer-deps; then
                            break
                        fi
                        ;;
                    3)
                        # Try with force and clean cache
                        npm cache clean --force
                        if npm install --force; then
                            break
                        fi
                        ;;
                esac
            done
        }
    else
        # If yarn is not available, use npm directly
        npm install || error "Failed to install frontend dependencies"
    fi

    # Build frontend
    log "Building frontend..."
    if [ -f "package.json" ]; then
        if grep -q "\"build\"" package.json; then
            npm run build || error "Failed to build frontend"
        else
            warning "No build script found in package.json"
        fi
    else
        error "package.json not found"
    fi

    cd ..
}

# Set up Node.js
setup_nodejs || error "Failed to set up Node.js"

# Set up frontend
setup_frontend || error "Failed to set up frontend"

# Generate secure MySQL password
MYSQL_PASSWORD=$(openssl rand -base64 32)

# Configure MySQL
log "Configuring MySQL..."
mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS 'incontrol'@'localhost' IDENTIFIED BY '${MYSQL_PASSWORD}';"
mysql -e "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# Configure MySQL security
mysql_secure_installation << EOF
n
y
y
y
y
y
EOF

# Set up SSL directory
mkdir -p /opt/incontrol/ssl
chmod 700 /opt/incontrol/ssl

# Generate strong Django secret key
DJANGO_SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Set up environment file
log "Setting up environment file..."
sed "s/your-secret-key-here/${DJANGO_SECRET_KEY}/g" .env.example > .env
sed -i "s/your-secure-password/${MYSQL_PASSWORD}/g" .env

# Copy and configure Nginx
log "Configuring Nginx..."
cp deployment/nginx/incontrol.conf /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/incontrol.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t || error "Invalid Nginx configuration"

# Copy systemd service files
log "Setting up systemd services..."
cp deployment/systemd/*.service /etc/systemd/system/
systemctl daemon-reload

# Django setup
log "Running Django migrations..."
source venv/bin/activate
handle_database_migration || error "Failed to handle database migration"

# Start services
log "Starting services..."
services=(
    "nginx"
    "redis-server"
    "incontrol"
    "incontrol-worker"
    "incontrol-beat"
    "incontrol-daphne"
)

for service in "${services[@]}"; do
    log "Enabling and starting $service..."
    systemctl enable "$service"
    systemctl start "$service"
    if ! systemctl is-active --quiet "$service"; then
        error "Failed to start $service"
    fi
done

# Final checks
log "Running final checks..."
curl -s -o /dev/null http://localhost || warning "Web server is not responding on HTTP"
redis-cli ping > /dev/null || warning "Redis is not responding"
python manage.py check --deploy || warning "Django deployment checks failed"

# Save installation summary
cat > /opt/incontrol/installation_summary.txt << EOF
InControl Installation Summary
============================
Date: $(date)
Python Version: $PYTHON_VERSION
Node Version: $NODE_VERSION
MySQL Password: $MYSQL_PASSWORD
Installation Directory: /opt/incontrol
Backup Directory: $BACKUP_DIR

Next Steps:
1. Set up SSL certificates: certbot --nginx -d your-domain.com
2. Create a superuser: python manage.py createsuperuser
3. Update allowed hosts in .env
4. Configure email settings in .env
5. Set up monitoring alerts

Important Directories:
- Logs: /var/log/incontrol
- Backups: /opt/incontrol/backups
- Static files: /opt/incontrol/static
- Media files: /opt/incontrol/media
- SSL certificates: /opt/incontrol/ssl

Services:
- Main application: systemctl status incontrol
- Worker: systemctl status incontrol-worker
- Beat: systemctl status incontrol-beat
- WebSocket: systemctl status incontrol-daphne

Monitoring URLs:
- Prometheus: http://localhost:9090
- AlertManager: http://localhost:9093
- Node Exporter: http://localhost:9100

Monitoring Services:
- Prometheus: systemctl status prometheus
- AlertManager: systemctl status alertmanager
- Node Exporter: systemctl status node_exporter

Important Monitoring Directories:
- Prometheus config: /etc/prometheus
- AlertManager config: /etc/alertmanager
- Prometheus data: /var/lib/prometheus
- AlertManager data: /var/lib/alertmanager
EOF

log "Installation complete!"
log "Please check /opt/incontrol/installation_summary.txt for next steps and important information"
log "MySQL password has been saved to .env and installation_summary.txt"
log "Remember to secure these files!" 

# Function to create a rollback point
create_rollback_point() {
    local rollback_dir="/opt/incontrol/rollback_$(date +%Y%m%d_%H%M%S)"
    log "Creating rollback point at $rollback_dir"
    
    mkdir -p "$rollback_dir"
    
    # Save current state
    if [ -d "/opt/incontrol" ]; then
        cp -r /opt/incontrol/* "$rollback_dir/" 2>/dev/null || true
    fi
    
    # Backup database
    if mysql -e "USE incontrol" 2>/dev/null; then
        mysqldump incontrol > "$rollback_dir/database.sql" || warning "Failed to backup database for rollback"
    fi
    
    # Backup configuration files
    mkdir -p "$rollback_dir/configs"
    cp -r /etc/nginx/sites-available/incontrol.conf "$rollback_dir/configs/" 2>/dev/null || true
    cp -r /etc/systemd/system/incontrol*.service "$rollback_dir/configs/" 2>/dev/null || true
    cp -r /etc/prometheus "$rollback_dir/configs/" 2>/dev/null || true
    cp -r /etc/alertmanager "$rollback_dir/configs/" 2>/dev/null || true
    
    # Save package state
    dpkg -l > "$rollback_dir/package_state.txt"
    pip freeze > "$rollback_dir/python_packages.txt"
    
    echo "$rollback_dir"
}

# Function to perform rollback
perform_rollback() {
    local rollback_dir="$1"
    log "Performing rollback to $rollback_dir"
    
    if [ ! -d "$rollback_dir" ]; then
        error "Rollback directory does not exist"
    fi
    
    # Stop services
    stop_all_services
    
    # Restore database if backup exists
    if [ -f "$rollback_dir/database.sql" ]; then
        log "Restoring database..."
        mysql -e "DROP DATABASE IF EXISTS incontrol"
        mysql -e "CREATE DATABASE incontrol"
        mysql incontrol < "$rollback_dir/database.sql" || error "Failed to restore database"
    fi
    
    # Restore configuration files
    if [ -d "$rollback_dir/configs" ]; then
        log "Restoring configuration files..."
        cp -r "$rollback_dir/configs/incontrol.conf" /etc/nginx/sites-available/ 2>/dev/null || true
        cp -r "$rollback_dir/configs/incontrol*.service" /etc/systemd/system/ 2>/dev/null || true
        cp -r "$rollback_dir/configs/prometheus" /etc/ 2>/dev/null || true
        cp -r "$rollback_dir/configs/alertmanager" /etc/ 2>/dev/null || true
        systemctl daemon-reload
    fi
    
    # Restore application files
    log "Restoring application files..."
    rm -rf /opt/incontrol/*
    cp -r "$rollback_dir"/* /opt/incontrol/ 2>/dev/null || true
    
    # Restart services
    start_all_services
    
    log "Rollback completed"
}

# Function to stop all services
stop_all_services() {
    log "Stopping all services..."
    local services=(
        "nginx"
        "redis-server"
        "incontrol"
        "incontrol-worker"
        "incontrol-beat"
        "incontrol-daphne"
        "prometheus"
        "alertmanager"
        "node_exporter"
    )
    
    for service in "${services[@]}"; do
        stop_service "$service"
    done
}

# Function to start all services
start_all_services() {
    log "Starting all services..."
    local services=(
        "nginx"
        "redis-server"
        "incontrol"
        "incontrol-worker"
        "incontrol-beat"
        "incontrol-daphne"
        "prometheus"
        "alertmanager"
        "node_exporter"
    )
    
    for service in "${services[@]}"; do
        systemctl start "$service" || warning "Failed to start $service"
    done
}

# Enhanced system checks
enhanced_system_checks() {
    log "Running enhanced system checks..."
    
    # Check system load
    local load_average=$(uptime | awk -F'load average:' '{ print $2 }' | cut -d, -f1)
    if (( $(echo "$load_average > 2.0" | bc -l) )); then
        warning "High system load detected: $load_average"
    fi
    
    # Check disk I/O
    if ! iostat >/dev/null 2>&1; then
        apt-get install -y sysstat >/dev/null 2>&1
    fi
    local disk_busy=$(iostat -d -x 1 2 | tail -n 2 | head -n 1 | awk '{ print $14 }')
    if (( $(echo "$disk_busy > 80.0" | bc -l) )); then
        warning "High disk I/O detected: $disk_busy%"
    fi
    
    # Check open files limit
    local open_files_limit=$(ulimit -n)
    if [ "$open_files_limit" -lt 65535 ]; then
        warning "Low open files limit: $open_files_limit (recommended: 65535)"
        # Try to increase the limit
        ulimit -n 65535 2>/dev/null || true
    fi
    
    # Check swap usage
    local swap_used=$(free | awk '/^Swap:/ { printf("%.2f", $3/$2 * 100) }')
    if (( $(echo "$swap_used > 80.0" | bc -l) )); then
        warning "High swap usage: $swap_used%"
    fi
    
    # Check for required services
    local required_services=(
        "mysql"
        "redis-server"
        "nginx"
    )
    
    for service in "${required_services[@]}"; do
        if ! systemctl is-active --quiet "$service"; then
            warning "Required service $service is not running"
        fi
    done
    
    # Check MySQL performance
    local mysql_max_connections=$(mysql -N -e "SHOW VARIABLES LIKE 'max_connections';" | awk '{ print $2 }')
    if [ "$mysql_max_connections" -lt 100 ]; then
        warning "Low MySQL max_connections: $mysql_max_connections (recommended: >= 100)"
    fi
    
    # Check Redis memory
    local redis_memory=$(redis-cli info memory | grep "used_memory_human:" | cut -d: -f2 | tr -d '[:space:]')
    local redis_maxmemory=$(redis-cli info memory | grep "maxmemory_human:" | cut -d: -f2 | tr -d '[:space:]')
    if [ "$redis_maxmemory" = "0B" ]; then
        warning "Redis maxmemory not set"
    fi
    
    # Check SSL certificates
    if [ -d "/opt/incontrol/ssl" ]; then
        for cert in /opt/incontrol/ssl/*.crt; do
            if [ -f "$cert" ]; then
                local expiry_date=$(openssl x509 -enddate -noout -in "$cert" | cut -d= -f2)
                local expiry_epoch=$(date -d "$expiry_date" +%s)
                local current_epoch=$(date +%s)
                local days_until_expiry=$(( ($expiry_epoch - $current_epoch) / 86400 ))
                if [ "$days_until_expiry" -lt 30 ]; then
                    warning "SSL certificate $cert will expire in $days_until_expiry days"
                fi
            fi
        done
    fi
    
    # Check SELinux status if available
    if command -v getenforce >/dev/null 2>&1; then
        local selinux_status=$(getenforce)
        if [ "$selinux_status" = "Enforcing" ]; then
            warning "SELinux is enforcing, might need configuration"
        fi
    fi
    
    log "System checks completed"
}

# Add trap for cleanup on script failure
cleanup_on_error() {
    local exit_code=$?
    local rollback_point="$1"
    
    if [ $exit_code -ne 0 ]; then
        warning "Installation failed with exit code $exit_code"
        if [ -n "$rollback_point" ]; then
            log "Rolling back to previous state..."
            perform_rollback "$rollback_point"
        fi
    fi
}

# Create rollback point and set trap
ROLLBACK_POINT=$(create_rollback_point)
trap "cleanup_on_error '$ROLLBACK_POINT'" EXIT

# Run enhanced system checks
enhanced_system_checks

# Function to create installation checkpoint
create_checkpoint() {
    local step_name="$1"
    local checkpoint_dir="/opt/incontrol/checkpoints/${step_name}_$(date +%Y%m%d_%H%M%S)"
    log "Creating checkpoint for step: $step_name"
    create_rollback_point > "$checkpoint_dir"
}

# Function to verify installation step
verify_step() {
    local step_name="$1"
    local verification_failed=false
    
    case "$step_name" in
        "system_dependencies")
            # Verify system dependencies
            local required_packages=(
                "python3"
                "nodejs"
                "nginx"
                "redis-server"
                "mariadb-server"
                "supervisor"
            )
            for package in "${required_packages[@]}"; do
                if ! dpkg -l | grep -q "^ii  $package "; then
                    warning "Package $package is not installed properly"
                    verification_failed=true
                fi
            done
            ;;
            
        "python_environment")
            # Verify Python environment
            if [ ! -d "venv" ] || ! source venv/bin/activate; then
                warning "Python virtual environment is not set up properly"
                verification_failed=true
            fi
            # Verify critical packages
            for package in "${critical_packages[@]}"; do
                if ! pip show "$package" >/dev/null 2>&1; then
                    warning "Python package $package is not installed"
                    verification_failed=true
                fi
            done
            ;;
            
        "database")
            # Verify database
            if ! mysql -e "USE incontrol" 2>/dev/null; then
                warning "Database 'incontrol' does not exist"
                verification_failed=true
            fi
            if ! python manage.py showmigrations | grep -q "\[X\]"; then
                warning "Database migrations are not applied"
                verification_failed=true
            fi
            ;;
            
        "services")
            # Verify services
            for service in "${services[@]}"; do
                if ! systemctl is-active --quiet "$service"; then
                    warning "Service $service is not running"
                    verification_failed=true
                fi
            done
            ;;
            
        "monitoring")
            # Verify monitoring setup
            local monitoring_services=(
                "prometheus"
                "alertmanager"
                "node_exporter"
            )
            for service in "${monitoring_services[@]}"; do
                if ! systemctl is-active --quiet "$service"; then
                    warning "Monitoring service $service is not running"
                    verification_failed=true
                fi
            done
            ;;
    esac
    
    if [ "$verification_failed" = true ]; then
        error "Verification failed for step: $step_name"
    fi
}

# Function to fix repository issues
fix_repository_issues() {
    log "Fixing repository issues..."
    
    # Backup existing sources
    cp /etc/apt/sources.list /etc/apt/sources.list.backup
    
    # Add main Ubuntu repositories
    cat > /etc/apt/sources.list << EOF
deb http://archive.ubuntu.com/ubuntu/ $(lsb_release -cs) main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu/ $(lsb_release -cs)-updates main restricted universe multiverse
deb http://archive.ubuntu.com/ubuntu/ $(lsb_release -cs)-security main restricted universe multiverse
EOF

    # Update package lists
    apt-get update -y || error "Failed to update package lists"
    
    # Fix any broken packages
    apt-get --fix-broken install -y
    dpkg --configure -a
    
    # Clean package manager state
    apt-get clean
    apt-get autoclean
    apt-get autoremove -y
}

# Function to install packages with fallback options
install_package_with_fallback() {
    local package_name="$1"
    log "Installing package: $package_name"
    
    # Try standard installation first
    if apt-get install -y "$package_name" 2>/dev/null; then
        return 0
    fi
    
    warning "Standard installation failed for $package_name, trying alternatives..."
    
    # Try with --fix-missing
    if apt-get install --fix-missing -y "$package_name" 2>/dev/null; then
        return 0
    fi
    
    # Try with different repository
    if apt-get install -y --no-install-recommends "$package_name" 2>/dev/null; then
        return 0
    fi
    
    # Try installing from specific repository version
    local ubuntu_version=$(lsb_release -cs)
    if apt-get install -y "$package_name/$ubuntu_version" 2>/dev/null; then
        return 0
    fi
    
    return 1
}

# Function to handle system dependencies with better error handling
install_system_dependencies() {
    log "Installing system dependencies..."
    
    # Fix any repository issues first
    fix_repository_issues
    
    # Essential packages that must be installed
    local essential_packages=(
        "python3"
        "python3-pip"
        "python3-venv"
        "build-essential"
        "libssl-dev"
        "libffi-dev"
        "python3-dev"
    )
    
    # Optional packages that can be skipped if installation fails
    local optional_packages=(
        "git"
        "supervisor"
        "logrotate"
        "ufw"
        "fail2ban"
    )
    
    # Install essential packages
    log "Installing essential packages..."
    for package in "${essential_packages[@]}"; do
        if ! install_package_with_fallback "$package"; then
            error "Failed to install essential package: $package"
        fi
    done
    
    # Install optional packages
    log "Installing optional packages..."
    for package in "${optional_packages[@]}"; do
        if ! install_package_with_fallback "$package"; then
            warning "Failed to install optional package: $package"
        fi
    done
    
    # Special handling for database
    log "Installing database server..."
    if ! install_package_with_fallback "mariadb-server"; then
        if ! install_package_with_fallback "mysql-server"; then
            error "Failed to install database server"
        fi
    fi
    
    # Special handling for web server
    log "Installing web server..."
    if ! install_package_with_fallback "nginx"; then
        warning "Failed to install nginx, will try alternative web server"
        if ! install_package_with_fallback "apache2"; then
            error "Failed to install web server"
        else
            log "Installed Apache2 as alternative web server"
        fi
    fi
    
    # Special handling for Redis
    log "Installing Redis..."
    if ! install_package_with_fallback "redis-server"; then
        warning "Failed to install Redis from package manager"
        # Try installing Redis from source
        install_redis_from_source
    fi
}

# Function to install Redis from source if package installation fails
install_redis_from_source() {
    log "Installing Redis from source..."
    
    local REDIS_VERSION="6.2.6"
    cd /tmp
    
    # Download and extract Redis
    curl -O http://download.redis.io/releases/redis-${REDIS_VERSION}.tar.gz
    tar xzf redis-${REDIS_VERSION}.tar.gz
    cd redis-${REDIS_VERSION}
    
    # Build Redis
    make distclean
    make
    make install
    
    # Create Redis user
    useradd -r -s /bin/false redis || true
    
    # Create Redis directories
    mkdir -p /var/lib/redis
    mkdir -p /var/log/redis
    chown redis:redis /var/lib/redis
    chown redis:redis /var/log/redis
    
    # Create Redis configuration
    mkdir -p /etc/redis
    cp redis.conf /etc/redis/
    
    # Create systemd service
    cat > /etc/systemd/system/redis.service << EOF
[Unit]
Description=Redis In-Memory Data Store
After=network.target

[Service]
User=redis
Group=redis
ExecStart=/usr/local/bin/redis-server /etc/redis/redis.conf
ExecStop=/usr/local/bin/redis-cli shutdown
Restart=always

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and start Redis
    systemctl daemon-reload
    systemctl enable redis
    systemctl start redis
    
    # Clean up
    cd /tmp
    rm -rf redis-${REDIS_VERSION}*
}

# Update the main installation flow to use the new functions
main_install() {
    log "Starting installation with improved package management..."
    
    # System dependencies checkpoint
    create_checkpoint "system_dependencies"
    install_system_dependencies
    verify_step "system_dependencies"
    
    # Rest of the installation process...
    # ... existing code ...
}

# Function to set up services
setup_services() {
    log "Setting up services..."
    
    # Configure Nginx
    log "Configuring Nginx..."
    cp deployment/nginx/incontrol.conf /etc/nginx/sites-available/
    ln -sf /etc/nginx/sites-available/incontrol.conf /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t || error "Invalid Nginx configuration"
    
    # Configure systemd services
    log "Setting up systemd services..."
    cp deployment/systemd/*.service /etc/systemd/system/
    systemctl daemon-reload
    
    # Start services with dependency order
    local service_order=(
        "redis-server"
        "mysql"
        "nginx"
        "incontrol-daphne"
        "incontrol-worker"
        "incontrol-beat"
        "incontrol"
    )
    
    for service in "${service_order[@]}"; do
        log "Starting $service..."
        systemctl enable "$service"
        systemctl start "$service"
        sleep 2  # Wait for service to stabilize
        if ! systemctl is-active --quiet "$service"; then
            error "Failed to start $service"
        fi
    done
}

# Function to set up monitoring
setup_monitoring() {
    log "Setting up monitoring..."
    
    # Install monitoring tools
    install_prometheus
    install_node_exporter
    install_alertmanager
    
    # Configure monitoring
    setup_prometheus_config
    setup_alertmanager_config
    
    # Start monitoring services
    local monitoring_services=(
        "prometheus"
        "alertmanager"
        "node_exporter"
    )
    
    for service in "${monitoring_services[@]}"; do
        log "Starting $service..."
        systemctl enable "$service"
        systemctl start "$service"
        if ! systemctl is-active --quiet "$service"; then
            error "Failed to start $service"
        fi
    done
}

# Update the main script to use the new installation flow
if [ "$EUID" -ne 0 ]; then 
    error "Please run as root"
fi

# Create rollback point and set trap
ROLLBACK_POINT=$(create_rollback_point)
trap "cleanup_on_error '$ROLLBACK_POINT'" EXIT

# Run enhanced system checks
enhanced_system_checks

# Start installation with checkpoints
main_install

# Final verification
log "Running final verification..."
verify_step "system_dependencies"
verify_step "python_environment"
verify_step "database"
verify_step "services"
verify_step "monitoring"

# Remove trap if everything succeeded
trap - EXIT

log "Installation completed successfully!" 