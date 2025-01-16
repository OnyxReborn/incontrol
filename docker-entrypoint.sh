#!/bin/bash

# Start required services
service mysql start
service redis-server start
service nginx start

# Initialize database if it doesn't exist
mysql -e "CREATE DATABASE IF NOT EXISTS incontrol CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS 'incontrol'@'localhost' IDENTIFIED BY 'development_password';"
mysql -e "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# Activate virtual environment
source venv/bin/activate

# Apply migrations
python manage.py migrate

# Create superuser if it doesn't exist
python manage.py shell << EOF
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
EOF

# Start development server
python manage.py runserver 0.0.0.0:8000 