FROM ubuntu:22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV container docker

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
RUN mkdir -p /var/run/sshd && \
    echo "PermitRootLogin yes" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config && \
    rm -f /run/nologin && \
    rm -f /etc/nologin && \
    systemctl enable ssh

# Create working directory
WORKDIR /home/testuser

# Copy and process installation files
COPY install.sh requirements.txt ./
RUN dos2unix install.sh && \
    dos2unix requirements.txt && \
    chmod +x install.sh && \
    chown -R testuser:testuser /home/testuser

# Create startup script
RUN echo '#!/bin/bash\nrm -f /run/nologin /etc/nologin\nexec /lib/systemd/systemd' > /startup.sh && \
    chmod +x /startup.sh

VOLUME [ "/sys/fs/cgroup" ]

# Expose ports
EXPOSE 22 80 443 8000 9090 9093 9100

STOPSIGNAL SIGRTMIN+3

CMD ["/startup.sh"] 