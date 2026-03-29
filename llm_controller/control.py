#!/usr/bin/env python3
"""
LLM-based robot controller for the RoboMaster platform.

Calls a locally-served LLM via vLLM's OpenAI-compatible API with a text
prompt, parses the velocity command from the response, and publishes it to
/<robot_ns>/cmd_vel at 10 Hz.

Run from inside the llm_controller Docker container:
    python3 /opt/robot/llm_controller/control.py

Environment variables (all optional):
    VLLM_BASE_URL   vLLM API base URL  (default: http://localhost:8000/v1)
    LLM_MODEL       Model to use       (default: Qwen/Qwen3.5-0.8B)
    ROBOT_NS        ROS 2 namespace    (default: hostname with - replaced by _)
"""

import json
import os
import re
import signal
import socket
import threading

import rclpy
from geometry_msgs.msg import Twist
from openai import OpenAI
from rclpy.node import Node

# ── Configuration ─────────────────────────────────────────────────────────────

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL     = os.environ.get("LLM_MODEL",     "Qwen/Qwen3.5-0.8B")
ROBOT_NS      = os.environ.get("ROBOT_NS",      socket.gethostname().replace("-", "_"))

CMD_VEL_TOPIC = f"/{ROBOT_NS}/cmd_vel"

# Robot velocity limits (conservative for LLM-driven control)
MAX_LINEAR  = 0.1   # m/s
MAX_ANGULAR = 0.05  # rad/s

# Publish the current command at this rate to satisfy the firmware watchdog
PUBLISH_HZ = 10

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""\
You are the controller of a ground robot. Output movement commands as a JSON object.

Coordinate frame (Z-down, right-handed):
  linear_x  — forward/backward, positive = forward   (range: -{MAX_LINEAR} to +{MAX_LINEAR} m/s)
  linear_y  — strafe left/right, positive = right     (range: -{MAX_LINEAR} to +{MAX_LINEAR} m/s)
  angular_z — rotation, positive = clockwise/right    (range: -{MAX_ANGULAR} to +{MAX_ANGULAR} rad/s)

Output ONLY a single JSON object on one line, no other text. Example:
{{"linear_x": 0.1, "linear_y": 0.0, "angular_z": 0.0}}"""

DEFAULT_USER_PROMPT = "Move the robot forward."

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_twist(text: str) -> Twist:
    """Extract a Twist from the LLM's JSON output. Returns zero-velocity on failure."""
    msg = Twist()
    try:
        m = re.search(r'\{[^}]+\}', text)
        if m:
            data = json.loads(m.group())
            msg.linear.x  = float(max(-MAX_LINEAR,  min(MAX_LINEAR,  data.get("linear_x",  0.0))))
            msg.linear.y  = float(max(-MAX_LINEAR,  min(MAX_LINEAR,  data.get("linear_y",  0.0))))
            msg.angular.z = float(max(-MAX_ANGULAR, min(MAX_ANGULAR, data.get("angular_z", 0.0))))
    except Exception as e:
        print(f"[parse_twist] could not parse '{text}': {e}", flush=True)
    return msg

# ── ROS 2 Node ────────────────────────────────────────────────────────────────

class LLMController(Node):
    def __init__(self, user_prompt: str):
        super().__init__("llm_controller")

        self._client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-needed")
        self._user_prompt = user_prompt

        self._current_cmd = Twist()
        self._cmd_lock = threading.Lock()
        self._running = True

        # Publisher: cmd_vel
        self._pub = self.create_publisher(Twist, CMD_VEL_TOPIC, 10)

        # Timer: push the current command to the robot at PUBLISH_HZ
        self.create_timer(1.0 / PUBLISH_HZ, self._publish_cb)

        # Background thread: call the LLM and update the command
        self._infer_thread = threading.Thread(
            target=self._inference_loop, daemon=True, name="llm_infer"
        )
        self._infer_thread.start()

        self.get_logger().info("LLM controller ready")
        self.get_logger().info(f"  namespace : {ROBOT_NS}")
        self.get_logger().info(f"  model     : {LLM_MODEL}")
        self.get_logger().info(f"  cmd_vel   : {CMD_VEL_TOPIC}")
        self.get_logger().info(f"  vLLM API  : {VLLM_BASE_URL}")
        self.get_logger().info(f"  prompt    : {user_prompt}")

    def _publish_cb(self):
        with self._cmd_lock:
            cmd = self._current_cmd
        self._pub.publish(cmd)

    def _inference_loop(self):
        wait = threading.Event()
        while self._running:
            try:
                response = self._client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": self._user_prompt},
                    ],
                    max_tokens=32,
                    temperature=0.0,
                )
                text = response.choices[0].message.content or ""
                self.get_logger().info(f"LLM: {text.strip()}")
                cmd = parse_twist(text)
            except Exception as exc:
                self.get_logger().error(f"Inference error: {exc}")
                cmd = Twist()   # stop on error

            with self._cmd_lock:
                self._current_cmd = cmd

            # Brief pause between inference calls — the LLM is the bottleneck,
            # the 10 Hz publish timer keeps the firmware watchdog happy in between
            wait.wait(timeout=0.1)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM robot controller")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=DEFAULT_USER_PROMPT,
        help=f'Instruction sent to the LLM each inference step (default: "{DEFAULT_USER_PROMPT}")',
    )
    args = parser.parse_args()

    rclpy.init()
    node = LLMController(user_prompt=args.prompt)

    # Install SIGINT handler before rclpy's own handler runs.
    # This ensures a zero-velocity command is published while the context
    # is still valid, then tears down cleanly.
    def _sigint_handler(sig, frame):
        node._running = False
        node._pub.publish(Twist())
        rclpy.shutdown()

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        rclpy.spin(node)
    except Exception:
        pass
    finally:
        node.destroy_node()


if __name__ == "__main__":
    main()
