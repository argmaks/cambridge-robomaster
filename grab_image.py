#!/usr/bin/env python3
"""
Grab a single frame from a ROS 2 compressed image topic and save it to a file.

Usage (inside a ROS 2 Docker container with network access):
    python3 grab_image.py [topic] [output_path]

Defaults:
    topic       /robomaster_max/camera_0/image_raw/compressed
    output_path /opt/robot/camera_sample.jpg

Examples:
    python3 grab_image.py
    python3 grab_image.py /robomaster_max/camera_0/image_raw/compressed /tmp/out.jpg

Run via docker exec:
    docker exec <container> bash -c "
        source /opt/robomaster/install/setup.bash &&
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp &&
        export ROS_DOMAIN_ID=0 &&
        python3 /opt/Robot/grab_image.py
    "

Note: uses qos_profile_sensor_data (best-effort) to match the camera publisher.
"""

import sys
import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage


class ImageSaver(Node):
    def __init__(self, topic, output_path):
        super().__init__('image_saver')
        self.output_path = output_path
        self.saved = False
        self.sub = self.create_subscription(
            CompressedImage, topic, self.callback, qos_profile_sensor_data
        )
        self.get_logger().info(f'Waiting for a frame on {topic} ...')

    def callback(self, msg):
        if self.saved:
            return
        self.saved = True
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        cv_image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        cv2.imwrite(self.output_path, cv_image)
        h, w = cv_image.shape[:2]
        self.get_logger().info(f'Saved {w}x{h} image to {self.output_path}')
        raise SystemExit


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else '/robomaster_max/camera_0/image_raw/compressed'
    output = sys.argv[2] if len(sys.argv) > 2 else '/opt/robot/camera_sample.jpg'
    rclpy.init()
    node = ImageSaver(topic, output)
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
