#!/usr/bin/env bash
hostname=$(cat /etc/hostname)
namespace=$(cat /etc/hostname | tr '-' '_')

docker run --rm --runtime nvidia --net=host --ipc=host --pid=host \
    -v /tmp/argus_socket:/tmp/argus_socket \
    --hostname "${hostname}" \
    cam_driver:latest \
    /bin/bash -c ". install/setup.bash && ros2 run gscam2 gscam_main --ros-args --params-file cam_param_jpg.yaml -r __ns:=/${namespace}/camera_0"
