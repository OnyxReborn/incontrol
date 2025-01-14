#!/usr/bin/env python
import os
import sys
import subprocess
import getpass
from django.core.management import execute_from_command_line

def setup_mysql():
    """Set up MySQL database and user."""
    try:
        # Create database
        subprocess.run(['mysql', '-e', 'CREATE DATABASE IF NOT EXISTS incontrol;'])
        
        # Create user and grant privileges
        subprocess.run(['mysql', '-e', 
                      "GRANT ALL PRIVILEGES ON incontrol.* TO 'incontrol_user'@'localhost' "
                      "IDENTIFIED BY 'CHANGE_THIS_PASSWORD';"])
        subprocess.run(['mysql', '-e', 'FLUSH PRIVILEGES;'])
        
        return True
    except Exception as e:
        print(f"Error setting up MySQL: {str(e)}")
        return False

def setup_directories():
    """Create necessary directories with proper permissions."""
    directories = [
        '/var/log/incontrol',
        '/var/lib/incontrol',
        '/var/lib/incontrol/backups',
        '/etc/incontrol',
    ]
    
    try:
        for directory in directories:
            os.makedirs(directory, mode=0o755, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error creating directories: {str(e)}")
        return False

def setup_services():
    """Set up system services."""
    try:
        # Create systemd service files
        with open('/etc/systemd/system/incontrol.service', 'w') as f:
            f.write("""[Unit]
Description=InControl Web Panel
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/incontrol
ExecStart=/opt/incontrol/venv/bin/gunicorn incontrol.wsgi:application -b 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
""")

        with open('/etc/systemd/system/incontrol-celery.service', 'w') as f:
            f.write("""[Unit]
Description=InControl Celery Worker
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/incontrol
ExecStart=/opt/incontrol/venv/bin/celery -A incontrol worker -l INFO
Restart=always

[Install]
WantedBy=multi-user.target
""")

        with open('/etc/systemd/system/incontrol-beat.service', 'w') as f:
            f.write("""[Unit]
Description=InControl Celery Beat
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=/opt/incontrol
ExecStart=/opt/incontrol/venv/bin/celery -A incontrol beat -l INFO
Restart=always

[Install]
WantedBy=multi-user.target
""")

        # Reload systemd
        subprocess.run(['systemctl', 'daemon-reload'])
        
        return True
    except Exception as e:
        print(f"Error setting up services: {str(e)}")
        return False

def main():
    """Main setup function."""
    print("InControl Setup Script")
    print("=====================")
    
    # Check if running as root
    if os.geteuid() != 0:
        print("This script must be run as root!")
        sys.exit(1)
    
    # Setup steps
    steps = [
        ("Setting up MySQL", setup_mysql),
        ("Creating directories", setup_directories),
        ("Setting up services", setup_services),
    ]
    
    # Execute setup steps
    for step_name, step_func in steps:
        print(f"\n{step_name}...")
        if step_func():
            print("Success!")
        else:
            print("Failed!")
            sys.exit(1)
    
    # Initialize Django database
    print("\nInitializing Django database...")
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'incontrol.settings')
    execute_from_command_line(['manage.py', 'migrate'])
    
    # Create superuser
    print("\nCreating admin user...")
    username = input("Enter admin username [admin]: ") or "admin"
    email = input("Enter admin email: ")
    while True:
        password = getpass.getpass("Enter admin password: ")
        password2 = getpass.getpass("Confirm admin password: ")
        if password == password2:
            break
        print("Passwords don't match! Try again.")
    
    from django.contrib.auth.models import User
    User.objects.create_superuser(username, email, password)
    
    print("\nSetup completed successfully!")
    print("\nNext steps:")
    print("1. Edit /opt/incontrol/incontrol/settings.py and update SECRET_KEY and other settings")
    print("2. Start the services:")
    print("   systemctl start incontrol")
    print("   systemctl start incontrol-celery")
    print("   systemctl start incontrol-beat")
    print("3. Enable the services to start on boot:")
    print("   systemctl enable incontrol")
    print("   systemctl enable incontrol-celery")
    print("   systemctl enable incontrol-beat")
    print("\nAccess the control panel at: http://your-server-ip:8000/")

if __name__ == '__main__':
    main() 