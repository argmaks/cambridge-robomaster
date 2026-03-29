#!/usr/bin/env bash
# Enter an interactive shell in the LLM controller container.
# The vLLM server must already be running (bash llm_controller/run_vllm.sh).
#
# Usage:
#   bash llm_controller/run_docker.sh
#
# Inside the container, start the controller:
#   python3 /opt/robot/llm_controller/control.py
#
# The container shares --network host so it can reach:
#   - ROS topics published by cam_driver and robomaster_bridge
#   - The vLLM API on http://localhost:8000

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

docker run --rm -it \
    --runtime nvidia \
    --network host \
    --hostname "$(cat /etc/hostname)" \
    -e ROS_DOMAIN_ID=0 \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    -e ROBOT_NS="$(cat /etc/hostname | tr '-' '_')" \
    -e VLLM_BASE_URL="${VLLM_BASE_URL:-http://localhost:8000/v1}" \
    -e VLM_MODEL="${VLM_MODEL:-Qwen/Qwen3.5-0.8B}" \
    -v "$REPO_DIR":/opt/robot \
    llm_controller:latest \
    /bin/bash -c ". /opt/ros/humble/install/setup.bash && exec bash"
