FROM dustynv/ros:humble-desktop-l4t-r36.4.0

RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    apt-get update && apt-get install -y git nano

RUN mkdir /opt/robomaster
WORKDIR /opt/robomaster

RUN git clone https://github.com/janblumenkamp/robomaster_ros2_can.git --recurse
WORKDIR /opt/robomaster/robomaster_ros2_can
RUN . /opt/ros/humble/install/setup.sh && colcon build

ENV ROS_DOMAIN_ID=0
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
