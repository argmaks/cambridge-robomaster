FROM dustynv/ros:humble-desktop-l4t-r36.4.0

# Install Python dependencies for LLM control.
# Force PyPI as the index — the base image overrides PIP_INDEX_URL to a
# Jetson-local mirror that does not carry general packages like openai.
RUN pip3 install --no-cache-dir --index-url https://pypi.org/simple \
    openai

ENV ROS_DOMAIN_ID=0
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

WORKDIR /opt/robot
