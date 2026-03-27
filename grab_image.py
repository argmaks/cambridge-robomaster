#!/usr/bin/env python3
"""
Grab a single frame from a ROS 2 image topic and save it to a file.

Usage (inside the ros2_panoptes_control Docker container):
    python3 grab_image.py [topic] [output_path]

Defaults:
    topic       /robomaster_2/camera_0/image_proc   (undistorted, 398x224)
    output_path /opt/Robot/camera_sample.jpg

Examples:
    # Save the processed (undistorted, 398x224) stream
    python3 grab_image.py

    # Save the raw full-resolution stream
    python3 grab_image.py /robomaster_2/camera_0/image_raw /tmp/raw.jpg

Run via docker exec:
    docker exec <control_container> bash -c "
        source /opt/ros/humble/install/setup.bash &&
        source /opt/robomaster/install/setup.bash &&
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp &&
        export ROS_DOMAIN_ID=0 &&
        python3 /path/to/grab_image.py
    "

Note: the subscriber uses qos_profile_sensor_data (best-effort) to match the
camera publisher. Using the default reliable QoS will cause a QoS mismatch
warning and no messages will be received.
"""

import sys
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


class ImageSaver(Node):
    def __init__(self, topic, output_path):
        super().__init__('image_saver')
        self.bridge = CvBridge()
        self.output_path = output_path
        self.saved = False
        self.sub = self.create_subscription(
            Image, topic, self.callback, qos_profile_sensor_data
        )
        self.get_logger().info(f'Waiting for a frame on {topic} ...')

    def callback(self, msg):
        if self.saved:
            return
        self.saved = True
        cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        cv2.imwrite(self.output_path, cv_image)
        self.get_logger().info(
            f'Saved {msg.width}x{msg.height} image to {self.output_path}'
        )
        raise SystemExit


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else '/robomaster_2/camera_0/image_proc'
    output = sys.argv[2] if len(sys.argv) > 2 else '/home/nvidia/Robot/camera_sample.jpg'
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
