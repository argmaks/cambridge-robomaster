# vision_base is built via jetson-containers for JP6 (L4T r36.x):
#   WITH_CUDSS=0 CUDA_VERSION=12.6 jetson-containers build --base=ros-humble-fixed:l4t-r36.4.0 --name=vision_base l4t-pytorch
FROM vision_base:latest

RUN apt-get update && apt-get install -y git vim cmake

RUN mkdir -p /opt/robomaster/src
WORKDIR /opt/robomaster/src
COPY camera /opt/robomaster/src/camera
WORKDIR /opt/robomaster

RUN . /opt/ros/humble/install/setup.sh && colcon build --symlink-install

COPY cyclone_dds_profile_base.xml /opt/robomaster

ENV ROS_DOMAIN_ID=0
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ENV CYCLONEDDS_URI=cyclone_dds_profile_base.xml
