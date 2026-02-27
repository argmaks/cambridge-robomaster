#!/usr/bin/env bash

set -e # Fail script if any command fails

if [[ $UID != 0 ]]; then
    echo "Please run this script with sudo."
    exit 1
fi

echo "Build docker container"
docker build . -t unitree:latest

echo "Prepare system service and config files"
set +e # read returns 1 by default
read -r -d '' unitree_service <<EOF
[Unit]
Description=Go1 ROS2 Driver
After=docker.service
Requires=docker.service
After=systemd-networkd.service
Requires=systemd-networkd

[Service]
Type=simple
TimeoutStopSec=2
ExecStart=/usr/bin/docker run --rm --runtime nvidia --network host --hostname $(hostname) unitree:latest /bin/bash -c ". install/setup.bash && ros2 run unitree_go1_ros2 ros2_twist_sub --ros-args --remap __ns:=/robomaster_20"
Restart=always

[Install]
WantedBy=multi-user.target
EOF

set -e

echo "Write systemd service"
echo "${unitree_service}" > /etc/systemd/system/unitree_bridge.service

echo "Enable and start robomaster bridge service"
systemctl enable unitree_bridge
systemctl start unitree_bridge

echo "Success! Reboot required."

# Not sure if needed

