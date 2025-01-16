FROM ubuntu:22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install systemd and other requirements
RUN apt-get update && apt-get install -y \
    systemd \
    systemd-sysv \
    openssh-server \
    sudo \
    curl \
    wget \
    git \
    dos2unix \
    && rm -rf /var/lib/apt/lists/* \
    && cd /lib/systemd/system/sysinit.target.wants/ \
    && ls | grep -v systemd-tmpfiles-setup | xargs rm -f $1 \
    && rm -f /lib/systemd/system/multi-user.target.wants/* \
    && rm -f /etc/systemd/system/*.wants/* \
    && rm -f /lib/systemd/system/local-fs.target.wants/* \
    && rm -f /lib/systemd/system/sockets.target.wants/*udev* \
    && rm -f /lib/systemd/system/sockets.target.wants/*initctl* \
    && rm -f /lib/systemd/system/basic.target.wants/* \
    && rm -f /lib/systemd/system/anaconda.target.wants/* \
    && rm -f /lib/systemd/system/plymouth* \
    && rm -f /lib/systemd/system/systemd-update-utmp*

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

# Copy installation files
COPY install.sh requirements.txt ./
RUN dos2unix install.sh && \
    chmod +x install.sh && \
    chown testuser:testuser install.sh requirements.txt

# Enable SSH service
RUN systemctl enable ssh

VOLUME [ "/sys/fs/cgroup" ]

# Expose ports
EXPOSE 22 80 443 8000 9090 9093 9100

# Start systemd
CMD ["/lib/systemd/systemd"] 