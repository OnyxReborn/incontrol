# InControl Panel

A comprehensive control panel for managing Linux servers, similar to WHM/cPanel.

## Features

- System Monitoring
- Backup Management
- Process Management
- File Management
- Database Management
- Email Server Management
- DNS Management
- Security Management
- Webserver Management
- Real-time Statistics

## Requirements

- Ubuntu Server 22.04 LTS
- Python 3.8+
- MySQL 8.0+
- Redis
- Node.js 16+
- Nginx

## Installation

1. Update your system:
```bash
sudo apt-get update && sudo apt-get upgrade -y
```

2. Download the installation script:
```bash
wget https://raw.githubusercontent.com/yourusername/incontrol/main/install.sh
chmod +x install.sh
```

3. Run the installation script:
```bash
sudo ./install.sh
```

4. During installation, you will be prompted to:
   - Set up MySQL root password
   - Create a database user
   - Create an admin user for the control panel

5. Copy the example environment file and update it with your settings:
```bash
cp .env.example .env
nano .env
```

6. Restart the services:
```bash
sudo supervisorctl restart all
```

## Post-Installation

1. Configure SSL (recommended):
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

2. Update your firewall rules if needed:
```bash
sudo ufw status
sudo ufw allow 'Nginx Full'
```

3. Access the control panel at:
```
http://your-server-ip
```

## Security Recommendations

1. Change default passwords:
   - MySQL root password
   - Control panel admin password
   - Database user password

2. Configure SSL certificate

3. Update the `.env` file with secure settings:
   - Set strong SECRET_KEY
   - Update ALLOWED_HOSTS
   - Enable secure cookie settings

4. Regular system updates:
```bash
sudo apt-get update && sudo apt-get upgrade -y
```

## Troubleshooting

1. Check service status:
```bash
sudo supervisorctl status
sudo systemctl status nginx
sudo systemctl status redis
sudo systemctl status mysql
```

2. View logs:
```bash
sudo tail -f /var/log/incontrol.log
sudo tail -f /var/log/nginx/error.log
```

3. Common issues:
   - Port conflicts: Check if ports 80, 443, 3306, 6379 are available
   - Permission issues: Ensure proper ownership of files
   - Database connection: Verify MySQL credentials
   - Redis connection: Check if Redis is running

## Backup and Recovery

1. Automated backups are configured in the control panel

2. Manual backup:
```bash
cd /opt/incontrol
source venv/bin/activate
python manage.py backup
```

3. To restore from backup, use the control panel interface or:
```bash
python manage.py restore <backup_file>
```

## Support

For issues and feature requests, please create an issue in the GitHub repository.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 