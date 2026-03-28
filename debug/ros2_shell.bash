#!/usr/bin/env bash
# Drops into an interactive ROS2 shell that can see topics from all other
# running containers (they all share --network host + same ROS_DOMAIN_ID).

docker run --runtime nvidia -it --rm \
    --network host \
    --hostname $(cat /etc/hostname) \
    -e ROS_DOMAIN_ID=0 \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    -v /home/nvidia/Robot:/opt/robot \
    dustynv/ros:humble-desktop-l4t-r36.4.0 \
    /bin/bash -c ". /opt/ros/humble/install/setup.bash && exec bash"
