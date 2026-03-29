#!/usr/bin/env bash
# Build the LLM controller Docker image and pull the vLLM server image.
#
# Usage:
#   bash llm_controller/install.bash

set -e

cd "$(dirname "$0")"

echo "=== Building llm_controller Docker image ==="
docker build . -t llm_controller:latest

echo ""
echo "=== Pulling Jetson vLLM image ==="
echo "(this is a large image — skip with Ctrl-C if already pulled)"
docker pull ghcr.io/nvidia-ai-iot/vllm:latest-jetson-orin

echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. Start the vLLM server (in one terminal):"
echo "       bash llm_controller/run_vllm.sh"
echo "  2. Wait for 'Application startup complete' in the vLLM log."
echo "  3. Enter the controller container (in another terminal):"
echo "       bash llm_controller/run_docker.sh"
echo "  4. Inside the container, run the controller:"
echo "       python3 /opt/robot/llm_controller/control.py"
