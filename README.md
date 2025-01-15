# InControl - Server Management Panel

A comprehensive web-based control panel for managing Linux servers, built with Django and React.

## Features

- Real-time system monitoring (CPU, Memory, Disk usage)
- Process management
- Service management
- Database administration
- Mail server management
- DNS management
- File management
- Backup management
- User management
- Security monitoring and firewall management
- Log monitoring and analysis

## Prerequisites

- Python 3.8+
- Node.js 16+
- MySQL/MariaDB
- Redis
- Linux server (Ubuntu 20.04+ recommended)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/OnyxReborn/panelmain.git
cd panelmain
```

2. Run the installation script:
```bash
chmod +x install.sh
sudo ./install.sh
```

The installation script will:
- Install system dependencies
- Set up Python virtual environment
- Install Python packages
- Install Node.js packages
- Configure the database
- Set up Redis
- Configure Nginx
- Set up SSL certificates
- Create systemd services

## Development Setup

1. Backend setup:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

2. Frontend setup:
```bash
cd frontend
npm install
npm start
```

3. Start development servers:
```bash
# Terminal 1 - Django
python manage.py runserver

# Terminal 2 - Celery worker
celery -A incontrol worker -l info

# Terminal 3 - Celery beat
celery -A incontrol beat -l info

# Terminal 4 - Daphne (WebSocket)
daphne incontrol.asgi:application
```

## Production Deployment

1. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your production settings
```

2. Configure Nginx:
```bash
sudo cp deployment/nginx/incontrol.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/incontrol.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

3. Start services:
```bash
sudo systemctl start incontrol
sudo systemctl start incontrol-worker
sudo systemctl start incontrol-beat
```

## API Documentation

API documentation is available at `/api/docs/` when running the server.

## Security Considerations

- Always change default credentials
- Use strong passwords
- Keep the system updated
- Enable SSL/TLS
- Configure firewall rules
- Regular security audits
- Monitor logs for suspicious activity

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 