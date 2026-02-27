FROM dustynv/ros:humble-ros-base-l4t-r35.3.1
  
RUN apt-get update && apt-get install -y git nano vim libmsgpack*

RUN mkdir -p /opt/unitree/src
WORKDIR /opt/unitree
RUN git clone https://github.com/unitreerobotics/unitree_legged_sdk.git src/unitree_go1_ros2/lib/unitree_legged_sdk
COPY unitree_go1_ros2 src/unitree_go1_ros2

RUN . /opt/ros/humble/install/setup.sh && colcon build

ENV ROS_DOMAIN_ID=0
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
