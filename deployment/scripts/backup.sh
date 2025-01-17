#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() { echo -e "${GREEN}[BACKUP] $1${NC}"; }
error() { echo -e "${RED}[ERROR] $1${NC}" >&2; }
warning() { echo -e "${YELLOW}[WARNING] $1${NC}"; }

# Backup directory structure
BACKUP_ROOT="/var/lib/incontrol/backups"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${BACKUP_DATE}"
RETENTION_DAYS=7

# Create backup directories
mkdir -p "${BACKUP_DIR}"/{db,mail,config}

# Backup databases
backup_databases() {
    log "Backing up databases..."
    
    # Backup InControl database
    mysqldump --single-transaction \
        -u incontrol -p"${DB_PASSWORD}" \
        incontrol > "${BACKUP_DIR}/db/incontrol.sql"
    
    # Backup mail database
    mysqldump --single-transaction \
        -u mail_admin -p"${MAIL_DB_PASSWORD}" \
        mail > "${BACKUP_DIR}/db/mail.sql"
    
    # Compress database backups
    cd "${BACKUP_DIR}/db"
    tar czf databases.tar.gz *.sql
    rm *.sql
}

# Backup mail data
backup_mail() {
    log "Backing up mail data..."
    
    # Backup mail directories
    tar czf "${BACKUP_DIR}/mail/vhosts.tar.gz" /var/mail/vhosts
    
    # Backup mail configurations
    tar czf "${BACKUP_DIR}/mail/config.tar.gz" \
        /etc/postfix \
        /etc/dovecot \
        /etc/opendkim
}

# Backup configurations
backup_configs() {
    log "Backing up configurations..."
    
    # Backup system configurations
    tar czf "${BACKUP_DIR}/config/system.tar.gz" \
        /etc/nginx \
        /etc/redis \
        /etc/bind \
        /etc/fail2ban \
        /etc/prometheus \
        /etc/alertmanager \
        /etc/grafana \
        /opt/incontrol/.env
        
    # Backup SSL certificates
    tar czf "${BACKUP_DIR}/config/ssl.tar.gz" \
        /etc/letsencrypt \
        /etc/nginx/ssl
}

# Clean old backups
cleanup_old_backups() {
    log "Cleaning up old backups..."
    find "${BACKUP_ROOT}" -maxdepth 1 -type d -mtime +${RETENTION_DAYS} -exec rm -rf {} \;
}

# Create backup manifest
create_manifest() {
    log "Creating backup manifest..."
    {
        echo "Backup Date: $(date)"
        echo "Hostname: $(hostname)"
        echo "System Info: $(uname -a)"
        echo "Disk Usage: $(df -h /)"
        echo "Backup Size: $(du -sh ${BACKUP_DIR})"
        echo "Included Files:"
        find "${BACKUP_DIR}" -type f -exec ls -lh {} \;
    } > "${BACKUP_DIR}/manifest.txt"
}

# Main backup function
main() {
    local start_time=$(date +%s)
    log "Starting backup process..."
    
    # Load environment variables
    source /opt/incontrol/.env
    
    # Perform backups
    backup_databases
    backup_mail
    backup_configs
    
    # Create manifest
    create_manifest
    
    # Compress entire backup
    cd "${BACKUP_ROOT}"
    tar czf "${BACKUP_DATE}.tar.gz" "${BACKUP_DATE}"
    rm -rf "${BACKUP_DATE}"
    
    # Cleanup old backups
    cleanup_old_backups
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log "Backup completed in ${duration} seconds"
    log "Backup stored in: ${BACKUP_ROOT}/${BACKUP_DATE}.tar.gz"
}

# Run backup
main 