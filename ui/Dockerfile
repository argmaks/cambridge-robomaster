FROM dustynv/ros:humble-desktop-l4t-r36.4.0

RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    apt-get update && apt-get install -y git nano

RUN mkdir /opt/robomaster
WORKDIR /opt/robomaster

RUN pip3 install --extra-index-url https://pypi.org/simple luma.oled
RUN pip3 install --extra-index-url https://pypi.org/simple Jetson.GPIO

COPY ui /opt/robomaster/
WORKDIR /opt/robomaster/src
RUN git clone https://github.com/proroklab/ros2_robomaster_msgs.git

WORKDIR /opt/robomaster
RUN . /opt/ros/humble/install/setup.bash && colcon build --symlink-install

ENV ROS_DOMAIN_ID=0
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
