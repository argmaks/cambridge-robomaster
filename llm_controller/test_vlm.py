#!/usr/bin/env python3
"""
Test script for VLM (Vision-Language Model) capability.

Grabs a single frame from the robot's camera ROS topic, optionally downscales
it to a size typical of robotic VLA pipelines, sends it together with a
user-supplied prompt to the vLLM-served VLM, and prints/saves the response.

Usage (inside the llm_controller Docker container):
    python3 /opt/robot/llm_controller/test_vlm.py "What do you see?"
    python3 /opt/robot/llm_controller/test_vlm.py "What do you see?" --size 224
    python3 /opt/robot/llm_controller/test_vlm.py "What do you see?" --size 640x480

    # Disable downscaling — send the raw camera frame
    python3 /opt/robot/llm_controller/test_vlm.py "What do you see?" --size native

Common VLA input sizes:
    224x224  — OpenVLA, most ViT / R3M-based policies
    256x256  — Octo, many diffusion policies
    336x336  — LLaVA-1.5, Qwen-VL (default)
    448x448  — higher-res Qwen-VL variants

Environment variables (all optional):
    VLLM_BASE_URL   vLLM API base URL  (default: http://localhost:8000/v1)
    VLM_MODEL       Model to use       (default: Qwen/Qwen3.5-0.8B)
    ROBOT_NS        ROS 2 namespace    (default: hostname with - replaced by _)

Outputs (written to /opt/robot/):
    vlm_test_image.jpg   — the frame that was sent to the VLM (after resizing)
    vlm_test_output.txt  — the VLM's text response
"""

import argparse
import base64
import os
import socket
import struct
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from openai import OpenAI

# ── Configuration ─────────────────────────────────────────────────────────────

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
VLM_MODEL     = os.environ.get("VLM_MODEL",     "Qwen/Qwen3.5-0.8B")
ROBOT_NS      = os.environ.get("ROBOT_NS",      socket.gethostname().replace("-", "_"))

OUTPUT_DIR    = Path("/opt/robot")
IMAGE_PATH    = OUTPUT_DIR / "vlm_test_image.jpg"
RESPONSE_PATH = OUTPUT_DIR / "vlm_test_output.txt"

# Default resize target — 336x336 is the standard Qwen-VL / LLaVA-1.5 input
DEFAULT_SIZE  = "336"

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_size(s: str) -> tuple[int, int] | None:
    """
    Parse a size string into (width, height).
    Accepts: "336" → (336, 336)  |  "640x480" → (640, 480)  |  "native" → None
    """
    s = s.strip().lower()
    if s == "native":
        return None
    if "x" in s:
        parts = s.split("x", 1)
        return int(parts[0]), int(parts[1])
    n = int(s)
    return n, n


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Return (width, height) by parsing JPEG SOF markers — no decode needed."""
    i = 0
    while i < len(data) - 1:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        i += 2
        if marker == 0xD8:              # SOI — no length field
            continue
        if marker in (0xD9, 0xDA):     # EOI / SOS
            break
        length = struct.unpack(">H", data[i:i + 2])[0]
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0 / SOF1 / SOF2
            h, w = struct.unpack(">HH", data[i + 3:i + 7])
            return w, h
        i += length
    raise ValueError("Could not find SOF marker — is this a valid JPEG?")


def resize_jpeg(jpeg_bytes: bytes, width: int, height: int, quality: int = 90) -> bytes:
    """
    Decode a JPEG, resize to (width, height) using INTER_AREA (best for
    downscaling), and re-encode to JPEG bytes.
    """
    buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cv2.imdecode failed — invalid JPEG?")
    img_resized = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", img_resized, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return encoded.tobytes()

# ── ROS image grabber ─────────────────────────────────────────────────────────

class _FrameGrabber(Node):
    """Subscribes to a compressed image topic and captures one frame."""

    def __init__(self, topic: str):
        super().__init__("vlm_frame_grabber")
        self.jpeg_bytes: bytes | None = None
        self._sub = self.create_subscription(
            CompressedImage, topic, self._cb, qos_profile_sensor_data
        )
        self.get_logger().info(f"Waiting for a frame on {topic} ...")

    def _cb(self, msg: CompressedImage):
        if self.jpeg_bytes is None:
            self.jpeg_bytes = bytes(msg.data)
            self.get_logger().info(f"Frame received ({len(self.jpeg_bytes) / 1024:.1f} KB)")
            raise SystemExit


def grab_frame(topic: str) -> bytes:
    """Block until one JPEG frame arrives on *topic*, then return the raw bytes."""
    rclpy.init()
    node = _FrameGrabber(topic)
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    jpeg = node.jpeg_bytes
    node.destroy_node()
    rclpy.shutdown()
    if jpeg is None:
        raise RuntimeError("No frame received before node shut down")
    return jpeg

# ── VLM query ─────────────────────────────────────────────────────────────────

def query_vlm(jpeg_bytes: bytes, prompt: str) -> tuple[str, dict[str, float]]:
    """
    Send *jpeg_bytes* and *prompt* to the vLLM server via a streaming request.

    Returns:
        answer   — the full response text
        timing   — dict with keys:
                     'ttft'       time-to-first-token (s)
                     'generation' first-token → last-token (s)
                     'total'      request sent → last-token (s)
                     'tok/s'      completion tokens per second
    """
    client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-needed")

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    chunks_text: list[str] = []
    t_request = time.perf_counter()
    t_first: float | None = None
    t_last: float = t_request
    n_tokens = 0

    stream = client.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text",      "text": prompt},
                ],
            }
        ],
        max_tokens=512,
        temperature=0.2,
        stream=True,
        stream_options={"include_usage": True},
    )

    print("  ", end="", flush=True)
    for chunk in stream:
        now = time.perf_counter()

        # Token usage arrives in the final chunk
        if chunk.usage is not None:
            n_tokens = chunk.usage.completion_tokens

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta.content
        if delta is None:
            continue

        if t_first is None:
            t_first = now
        t_last = now
        chunks_text.append(delta)
        print(delta, end="", flush=True)

    print()  # newline after streamed output

    t_first = t_first or t_last  # guard: empty response
    ttft       = t_first - t_request
    generation = t_last  - t_first
    total      = t_last  - t_request
    toks_per_s = n_tokens / generation if generation > 0 else 0.0

    timing = {
        "ttft":       ttft,
        "generation": generation,
        "total":      total,
        "tok/s":      toks_per_s,
        "tokens":     float(n_tokens),
    }
    return "".join(chunks_text), timing

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test VLM with a live camera frame")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Describe what you see in this image.",
        help="Prompt sent to the VLM alongside the camera frame",
    )
    parser.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        metavar="WxH|N|native",
        help=(
            f"Resize the frame before sending to the VLM. "
            f"'N' → NxN square, 'WxH' → explicit size, 'native' → no resize. "
            f"Default: {DEFAULT_SIZE} (336x336)"
        ),
    )
    parser.add_argument(
        "--topic",
        default=f"/{ROBOT_NS}/camera_0/image_raw/compressed",
        help="ROS 2 compressed image topic to subscribe to",
    )
    parser.add_argument(
        "--image-out",
        default=str(IMAGE_PATH),
        help=f"Where to save the grabbed frame (default: {IMAGE_PATH})",
    )
    parser.add_argument(
        "--response-out",
        default=str(RESPONSE_PATH),
        help=f"Where to save the VLM response (default: {RESPONSE_PATH})",
    )
    args = parser.parse_args()

    try:
        target_size = parse_size(args.size)
    except ValueError:
        print(f"[error] Invalid --size '{args.size}'. Use e.g. '336', '640x480', or 'native'.", file=sys.stderr)
        sys.exit(1)

    print(f"[config] model     : {VLM_MODEL}")
    print(f"[config] vLLM API  : {VLLM_BASE_URL}")
    print(f"[config] topic     : {args.topic}")
    print(f"[config] size      : {'native (no resize)' if target_size is None else f'{target_size[0]}x{target_size[1]}'}")
    print(f"[config] prompt    : {args.prompt}")
    print()

    timings: dict[str, float] = {}
    t_total = time.perf_counter()

    # 1. Grab one camera frame
    print("[step 1] Grabbing camera frame ...")
    t0 = time.perf_counter()
    try:
        jpeg = grab_frame(args.topic)
    except Exception as e:
        print(f"[error] Could not grab frame: {e}", file=sys.stderr)
        sys.exit(1)
    timings["1. frame grab"] = time.perf_counter() - t0

    try:
        orig_w, orig_h = jpeg_dimensions(jpeg)
        orig_info = f"{orig_w}x{orig_h} px, {len(jpeg) / 1024:.1f} KB"
    except ValueError:
        orig_info = f"{len(jpeg) / 1024:.1f} KB"
    print(f"         {orig_info}  ({timings['1. frame grab']:.2f}s)")

    # 2. Optionally downscale
    if target_size is not None:
        tw, th = target_size
        print(f"[step 2] Resizing {orig_info} → {tw}x{th} ...")
        t0 = time.perf_counter()
        try:
            jpeg = resize_jpeg(jpeg, tw, th)
        except Exception as e:
            print(f"[error] Resize failed: {e}", file=sys.stderr)
            sys.exit(1)
        timings["2. resize"] = time.perf_counter() - t0
        print(f"         After resize: {tw}x{th} px, {len(jpeg) / 1024:.1f} KB  ({timings['2. resize']*1000:.1f}ms)")
    else:
        print(f"[step 2] No resize requested. Native size: {orig_info}")

    # 3. Save the frame to disk
    image_path = Path(args.image_out)
    t0 = time.perf_counter()
    image_path.write_bytes(jpeg)
    timings["3. save image"] = time.perf_counter() - t0
    print(f"[step 3] Frame saved to {image_path}  ({timings['3. save image']*1000:.1f}ms)")

    # 4. Query the VLM
    print("[step 4] Querying VLM (streaming) ...")
    print("=" * 60)
    try:
        answer, vlm_timing = query_vlm(jpeg, args.prompt)
    except Exception as e:
        print(f"[error] VLM query failed: {e}", file=sys.stderr)
        sys.exit(1)
    print("=" * 60)
    timings["4. VLM inference"] = vlm_timing["total"]

    print(f"         TTFT:       {vlm_timing['ttft']:.2f}s")
    print(f"         Generation: {vlm_timing['generation']:.2f}s  "
          f"({int(vlm_timing['tokens'])} tokens @ {vlm_timing['tok/s']:.1f} tok/s)")

    # 5. Save the response
    response_path = Path(args.response_out)
    response_path.write_text(answer, encoding="utf-8")
    print(f"[step 5] Response saved to {response_path}")

    # 6. Timing summary
    total = time.perf_counter() - t_total
    print()
    print("── Timing summary ──────────────────────────────────────")
    for label, dt in timings.items():
        bar = "█" * int(dt / total * 30)
        print(f"  {label:<20} {dt:6.2f}s  {bar}")
    print(f"  {'TOTAL':<20} {total:6.2f}s")
    print()
    print("── VLM breakdown ───────────────────────────────────────")
    print(f"  {'TTFT':<20} {vlm_timing['ttft']:6.2f}s")
    print(f"  {'Generation':<20} {vlm_timing['generation']:6.2f}s  "
          f"({int(vlm_timing['tokens'])} tokens @ {vlm_timing['tok/s']:.1f} tok/s)")
    print("────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
