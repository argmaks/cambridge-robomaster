#!/usr/bin/env bash
# Serve a VLM via the Jetson-optimised vLLM container.
# The model is downloaded on first run and cached in ~/.cache/huggingface.
#
# Usage:
#   bash llm_controller/run_vllm.sh [MODEL]
#
# Defaults:
#   MODEL   Qwen/Qwen2.5-VL-3B-Instruct   (3B vision-language model)
#
# The server listens on http://localhost:8000 (OpenAI-compatible API).
# Keep this terminal open while running control.py.

MODEL="${1:-Qwen/Qwen3.5-0.8B}"
GPU_MEM="${GPU_MEM:-0.55}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"

echo "Starting vLLM server with model: $MODEL"
echo "  GPU memory utilisation: $GPU_MEM"
echo "  Max model length:       $MAX_MODEL_LEN"
echo "  torch.compile:          disabled (--enforce-eager)"
echo ""

docker run --rm -it \
    --runtime nvidia \
    --network host \
    --name vllm_server \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    ghcr.io/nvidia-ai-iot/vllm:latest-jetson-orin \
    vllm serve "$MODEL" \
        --gpu-memory-utilization "$GPU_MEM" \
        --max-model-len "$MAX_MODEL_LEN" \
        --enforce-eager \
        --host 0.0.0.0 \
        --port 8000
