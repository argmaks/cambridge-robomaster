#!/usr/bin/env bash

set -e # Fail script if any command fails

if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo."
    exit 1
fi

# Sync the system clock before building — Docker containers inherit the host clock,
# and a drifted clock causes "Release file not valid yet" failures in apt-get update.
echo "Syncing system clock..."
if command -v ntpdate &>/dev/null; then
    ntpdate -u pool.ntp.org || true
else
    # Force systemd-timesyncd to sync immediately via timedatectl
    timedatectl set-ntp false
    timedatectl set-ntp true
    # Wait up to 30 s for synchronisation
    for i in $(seq 1 30); do
        if timedatectl status | grep -q "synchronized: yes"; then
            break
        fi
        sleep 1
    done
fi
echo "System time: $(date -u)"

if [ -z "$(docker images -q vision_base:latest 2>/dev/null)" ]; then
    echo "Building vision_base with jetson-containers (this may take a while)..."
    if ! command -v jetson-containers &>/dev/null; then
        echo "ERROR: jetson-containers not found."
        echo "Install it from: https://github.com/dusty-nv/jetson-containers"
        exit 1
    fi
    CUDA_VERSION=12.6 jetson-containers build \
        --base=ros-humble-fixed:l4t-r36.4.0 \
        --name=vision_base \
        --build-args WITH_CUDSS:0 \
        l4t-pytorch
fi

if [ -z "$(docker images -q cam_driver_dnv:latest 2> /dev/null)" ]; then
    echo "Build docker container"
    docker build . -t cam_driver_dnv:latest
fi

echo "Prepare systemd service"
hostname=$(hostname)

set +e # read returns 1 by default
IFS='' read -r -d '' camera_service <<EOF
[Unit]
Description=Camera Stream/Encode 0
After=docker.service
Requires=docker.service
After=nvargus-daemon.service
Requires=nvargus-daemon.service

[Service]
Type=simple
TimeoutStopSec=2
# Sleep before start because otherwise camera fails capturing
ExecStartPre=/bin/sleep 30
ExecStart=/usr/bin/docker run --rm --runtime nvidia --net=host --ipc=host -v /tmp/argus_socket:/tmp/argus_socket --hostname ${hostname} cam_driver_dnv:latest /bin/bash -c ". install/setup.bash && while true; do ros2 launch src/camera/launch/camera.launch.py; done"
Restart=always

[Install]
WantedBy=multi-user.target
EOF
set -e

echo "Write systemd service"
echo "${camera_service}" > /etc/systemd/system/camera_stream_0.service

echo "Enable and start service"
systemctl enable camera_stream_0
systemctl start camera_stream_0

echo "Success!"
