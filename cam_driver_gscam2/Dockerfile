FROM dustynv/ros:humble-desktop-l4t-r36.4.0

RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    apt-get update && apt-get install -y git nano

# Install real NVIDIA GStreamer plugins (the container base has 0-byte stubs).
# We extract only the plugin .so files using dpkg-deb to bypass the nvidia-l4t-core
# preinst script that checks /proc/device-tree/compatible (unavailable in Docker build).
RUN echo "deb https://repo.download.nvidia.com/jetson/common r36.4 main" > /etc/apt/sources.list.d/nvidia-l4t.list && \
    echo "deb https://repo.download.nvidia.com/jetson/t234 r36.4 main" >> /etc/apt/sources.list.d/nvidia-l4t.list && \
    apt-key adv --fetch-keys https://repo.download.nvidia.com/jetson/jetson-ota-public.asc && \
    apt-get update && \
    cd /tmp && apt-get download nvidia-l4t-gstreamer && \
    dpkg-deb --extract nvidia-l4t-gstreamer_*.deb /tmp/l4t-gst && \
    cp /tmp/l4t-gst/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv*.so \
       /usr/lib/aarch64-linux-gnu/gstreamer-1.0/ && \
    rm -rf /tmp/l4t-gst /tmp/nvidia-l4t-gstreamer_*.deb

RUN apt-get install -y libgstreamer1.0-0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
 gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools \
 gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio \
 libgstreamer-plugins-base1.0-dev

RUN mkdir -p /opt/robomaster/src
WORKDIR /opt/robomaster/src

RUN git clone https://github.com/clydemcqueen/gscam2.git && \
    cd gscam2 && git checkout 7cf5e85
###
COPY gscam_failure_exit.patch /opt/robomaster/src/gscam2
WORKDIR /opt/robomaster/src/gscam2
RUN git apply gscam_failure_exit.patch
WORKDIR /opt/robomaster/src
###
RUN git clone https://github.com/ptrmu/ros2_shared.git -b master
WORKDIR /opt/robomaster

RUN . /opt/ros/humble/install/setup.sh && rosdep install -y --from-paths . --ignore-src
RUN . /opt/ros/humble/install/setup.sh && colcon build

COPY cyclone_dds_profile_base.xml /opt/robomaster
COPY cam_param_jpg.yaml /opt/robomaster
COPY cam_param_raw.yaml /opt/robomaster
COPY front_camera.yaml /opt/robomaster

ENV ROS_DOMAIN_ID=0
#ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
#ENV CYCLONEDDS_URI=cyclone_dds_profile_base.xml
