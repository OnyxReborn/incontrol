FROM ubuntu:22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install minimal requirements for SSH and basic tools
RUN apt-get update && apt-get install -y \
    openssh-server \
    sudo \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a test user with sudo access
RUN useradd -m -s /bin/bash testuser && \
    echo "testuser:password" | chpasswd && \
    adduser testuser sudo && \
    echo "testuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Configure SSH
RUN mkdir /var/run/sshd && \
    echo "PermitRootLogin yes" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config

# Create working directory
WORKDIR /home/testuser

# Copy install script
COPY install.sh .
RUN chmod +x install.sh && \
    chown testuser:testuser install.sh

# Expose SSH port
EXPOSE 22

# Start SSH service
CMD ["/usr/sbin/sshd", "-D"] 