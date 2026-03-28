# Cambridge RoboMaster

This is the source repository containing all information necessary to reproduce the Cambridge RoboMaster platform.

<img align="center" src="https://drive.google.com/uc?export=view&id=1GQjxcqhbU3Vyi9NLeHxNajqnFyemjELS">

Paper: TBD

For all further information, please refer the [website](https://proroklab.github.io/cambridge-robomaster/).

---

## Repository Structure

Each subdirectory is a self-contained service, typically running as a Docker container with a systemd unit for autostart on the Jetson.

| Folder | Purpose |
|---|---|
| `robomaster_bridge/` | CAN ↔ ROS 2 bridge. Builds [`robomaster_ros2_can`](https://github.com/janblumenkamp/robomaster_ros2_can) and exposes ROS 2 topics for controlling and reading the DJI RoboMaster over `can0` at 1 Mbps. |
| `cam_driver/` | CSI camera → ROS 2 image pipeline using jetson-utils (legacy, JP5). |
| `cam_driver_gscam2/` | **Active camera service.** GStreamer-based pipeline (`gscam2`) for JP6. Publishes JPEG-compressed frames via Argus. Installed as `camera_stream_0.service`. |
| `camera_utils/` | Shell scripts to tune Jetson BPMP hardware clocks (VI, ISP, NVCSI) for maximum camera throughput. |
| `joycon/` | Dockerized ROS 2 joystick node (`game_controller_node`). Publishes controller input to `/<robot_ns>/joy`. |
| `ui/` | On-robot operator UI: SSD1306 OLED (I2C), GPIO button, battery/wheel state display, emergency stop client. |
| `emergency_stop/` | Central emergency stop controller for a Raspberry Pi. Discovers all `EmergencyStop` services on the ROS graph and fans out stop/resume on physical button press. NeoPixel ring shows per-robot status. |
| `unitree/` | ROS 2 bridge for the Unitree Go1 quadruped. Subscribes to `cmd_vel` and sends UDP commands via `unitree_legged_sdk`. Registered in the fleet as `robomaster_20`. |
| `adhoc/` | Ad-hoc Wi-Fi setup (`wlan1`, SSID `roboAdHoc`, `10.3.2.x`) for robot-to-robot mesh networking. Also contains fleet-wide firewall helpers and a Fast DDS profile. |
| `setup/` | Jetson provisioning: apt packages, user creation, `nmcli` Wi-Fi profile for the `robomaster` network (`10.3.1.x`). |
| `docker/` | Helpers to pull images from the private registry (`10.3.0.22:5000`) and set the NVIDIA container runtime as Docker default. |
| `llm_controller/` | LLM/VLM robot controller. Serves a model via vLLM, calls it in a loop, and publishes velocity commands to `cmd_vel`. |

**Network layout:**
- Infrastructure Wi-Fi: `wlan0`, `10.3.1.x` — robots are `robomaster-1`, `robomaster-2`, etc.
- Ad-hoc mesh: `wlan1`, `10.3.2.x`
- Robot namespaces in ROS 2 match the hostname: `robomaster_1`, `robomaster_max`, etc.

---

## First-Time Setup (per Jetson)

### 0. Install prerequisites and clone the repo

```bash
sudo apt-get update
sudo apt-get install curl tmux
```

Clone this repo and rename `cambridge_robomaster` to `Robot`:

```bash
git clone <repo-url> Robot
cd Robot
```

### 1. Set hostname and passwordless sudo

```bash
sudo ./setup/sudocfg.bash       # allow nvidia user to run sudo without password
sudo vim /etc/hostname           # set to e.g. robomaster-1
sudo reboot
```

### 2. Install and set up Docker

```bash
sudo bash docker/install_docker.sh
```

This script installs Docker CE from the official APT repository, sets the NVIDIA container runtime as the default, copies `docker/daemon.json` (which includes the private registry at `10.3.0.22:5000`), enables Docker at boot, and adds the `nvidia` user to the `docker` group. Log out and back in after it completes.

> See `~/install-docker-jetson-jp6.md` for full installation notes and troubleshooting.

### 3. Switch to headless mode

Disable the desktop environment to free GPU and CPU resources:

```bash
sudo systemctl set-default multi-user.target
sudo reboot
```

### 4. Set power mode to MAXN

MAXN unlocks all CPU/GPU cores and removes power caps:

```bash
sudo nvpmodel -m <power-mode-number>
```

Available power modes are listed in `/etc/nvpmodel.conf`. Mode `0` is typically MAXN (maximum performance).

### 5. Install and start the CAN bridge

```bash
cd robomaster_bridge
sudo bash install.bash
# reboot if prompted for CAN interface changes
bash robomaster_bridge/run_docker.sh
```

### 6. (Optional) Install the camera service

Install the host GStreamer Argus plugin (required — not installed by default on JP6):

```bash
sudo apt-get install nvidia-l4t-gstreamer
```

Then build and install the camera service:

```bash
sudo bash cam_driver_gscam2/install.bash
```

### 7. (Optional) Install and run the UI service

```bash
cd ui
sudo bash install.bash
bash ui/run_docker.sh
```

### 8. Install jetson-containers

[jetson-containers](https://github.com/dusty-nv/jetson-containers) is a community-maintained modular build system providing pre-built and buildable Docker images for AI/ML workloads on Jetson (PyTorch, LLMs, ROS, diffusion models, and more).

Run the following **on the Jetson**:

```bash
git clone https://github.com/dusty-nv/jetson-containers
cd jetson-containers
bash install.sh
```

### 9. Install VLLM

```bash
docker pull ghcr.io/nvidia-ai-iot/vllm:latest-jetson-orin
```

If the pull fails with `connection reset by peer` over IPv6, see [Docker pull fails over IPv6](#docker-pull-fails-over-ipv6-connection-reset-by-peer) in Troubleshooting.

### 10. (Optional) Install the LLM controller

```bash
bash llm_controller/install.bash
```

This builds the `llm_controller:latest` Docker image (ROS 2 Humble + openai) and pulls the vLLM Jetson image.


---

## Controlling a Robot

### Prerequisites

ROS 2 is **not installed natively** on the Jetson host — it lives inside Docker. Use the debug shell:

```bash
bash /home/nvidia/Robot/debug/ros2_shell.bash
```

### Sending velocity commands (`cmd_vel`)

The bridge subscribes to `geometry_msgs/msg/Twist` on `/<robot_ns>/cmd_vel`.

**Always publish at `-r 10` Hz or higher.** Publishing at the default 1 Hz causes the firmware watchdog to cut motor power between messages, resulting in a "twitching" effect.

```bash
# Move forward
ros2 topic pub -r 10 /robomaster_max/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.1, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Strafe right
ros2 topic pub -r 10 /robomaster_max/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.1, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Rotate clockwise (turn right)
ros2 topic pub -r 10 /robomaster_max/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.05}}"

# Stop
ros2 topic pub --once /robomaster_max/cmd_vel geometry_msgs/msg/Twist "{}"
```

### Coordinate system

The robot uses a **right-handed, Z-down** frame (NED-style):

| Axis | Direction | Notes |
|---|---|---|
| X | Forward | `linear.x` positive = forward |
| Y | Right | `linear.y` positive = strafe right |
| Z | Down | `angular.z` positive = **clockwise** (turn right) |

This is the **opposite** of ROS REP-103 (Z-up, CCW positive). Negate `angular.z` when mixing with standard ROS sensors.



### Sending raw wheel RPM commands (`cmd_wheels`)

For direct wheel control, publish `robomaster_msgs/msg/WheelSpeed` to `/<robot_ns>/cmd_wheels`. Use **`-r 50` Hz** — the firmware requires a sustained command stream at this rate.

```bash
ros2 topic pub -r 50 /robomaster_max/cmd_wheels robomaster_msgs/msg/WheelSpeed \
  "{fr: 200, fl: 200, rl: 200, rr: 200}"
```

RPM range is **-1000 to 1000** per wheel (`fl` = front-left, `fr` = front-right, `rl` = rear-left, `rr` = rear-right).

---

## Camera

### Overview

The `cam_driver_gscam2/` service runs a single `gscam2` node under `/<robot_ns>/camera_0/`:

| Topic | Type | Description |
|---|---|---|
| `camera_0/image_raw/compressed` | `sensor_msgs/CompressedImage` | JPEG frames, 1920×1080 @ 20 fps |
| `camera_0/camera_info` | `sensor_msgs/CameraInfo` | Calibration data |

The camera service starts automatically on boot via `camera_stream_0.service` (installed by `sudo bash cam_driver_gscam2/install.bash`).

**Host prerequisite:** `nvidia-l4t-gstreamer` must be installed on the Jetson — this provides the `nvarguscamerasrc` GStreamer plugin that talks to the Argus daemon. The plugin is mounted read-only into the container at runtime.

> **Note:** Cyclone DDS in the camera container is pinned to `wlan0` — you must be on the same Wi-Fi network to receive image topics from another machine.

### Grabbing a sample image

`grab_image.py` (in this repo) subscribes to the compressed image topic and saves one frame to disk. Run it from inside the debug shell:

```bash
# Start the debug shell (Robot/ is mounted at /opt/robot)
bash /home/nvidia/Robot/debug/ros2_shell.bash

# Inside the container — grab one frame (saved to /home/nvidia/Robot/camera_sample.jpg on the host)
python3 /opt/robot/grab_image.py

# Save the full-resolution compressed stream to a custom path
python3 /opt/robot/grab_image.py /robomaster_max/camera_0/image_raw/compressed /opt/robot/raw.jpg
```

> **QoS note:** The camera publishes with `best_effort` reliability (`qos_profile_sensor_data`). Subscribing with the default `reliable` QoS will silently receive nothing — `grab_image.py` already handles this correctly.


---

## LLM Inference using vLLM

### Starting the vLLM container

```bash
docker run --rm -it --runtime nvidia --network host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  ghcr.io/nvidia-ai-iot/vllm:latest-jetson-orin
```

If Docker reports `unknown or invalid runtime name: nvidia`, see [NVIDIA container runtime not recognised](#nvidia-container-runtime-not-recognised) in Troubleshooting.

### Serving a model

Inside the container:

```bash
vllm serve Qwen/Qwen3.5-0.8B --gpu-memory-utilization 0.6 --max-model-len 8656
```

### Benchmarking a model

Find the running container ID:

```bash
docker ps
```

Open an interactive shell inside it:

```bash
docker exec -it <CONTAINER_ID> bash
```

Run the benchmark:

```bash
vllm bench serve \
  --dataset-name random \
  --model Qwen/Qwen3.5-0.8B \
  --num-prompts 50 \
  --percentile-metrics ttft,tpot,itl,e2el \
  --random-input-len 2048 \
  --random-output-len 128 \
  --max-concurrency 1
```

---

## LLM Controller

`llm_controller/` is a minimal pipeline that lets a locally-served LLM drive the robot by publishing to `cmd_vel`.

### Architecture

```
Terminal 1                        Terminal 2
────────────────────────────      ────────────────────────────────────────
bash llm_controller/              bash llm_controller/run_docker.sh
  run_vllm.sh                     # inside container:
                                  python3 /opt/robot/llm_controller/control.py
│                                 │
│  vLLM server :8000              │  ROS 2 node "llm_controller"
│  (Qwen/Qwen3.5-0.8B)           │  ├─ background thread: calls LLM, parses JSON
│                                 │  └─ timer: publishes cmd_vel @ 10 Hz
└── ←── HTTP /v1/chat/completions ┘
```

The 10 Hz publish timer runs independently of inference so the firmware watchdog is always satisfied even when the LLM is mid-inference.

### Running

**Terminal 1 — start the model server:**

```bash
bash llm_controller/run_vllm.sh
```

Wait for `Application startup complete` before proceeding. The model is downloaded on first run and cached in `~/.cache/huggingface`.

**Terminal 2 — enter the controller container:**

```bash
bash llm_controller/run_docker.sh
```

**Inside the container — start the controller:**

```bash
python3 /opt/robot/llm_controller/control.py
```

### Configuration

All tunables are environment variables or constants at the top of `control.py`:

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `Qwen/Qwen3.5-0.8B` | Model served by vLLM |
| `VLLM_BASE_URL` | `http://localhost:8000/v1` | vLLM API endpoint |
| `ROBOT_NS` | hostname with `-` → `_` | ROS 2 namespace |
| `MAX_LINEAR` | `0.1` m/s | Velocity cap applied to LLM output |
| `MAX_ANGULAR` | `0.05` rad/s | Angular rate cap |

To change the robot's behaviour, edit `USER_PROMPT` in `control.py`. The LLM is instructed to reply with a single JSON object:

```json
{"linear_x": 0.1, "linear_y": 0.0, "angular_z": 0.0}
```

which is parsed and clipped to the velocity limits before publishing.

### Visual Question Answering (`test_vlm.py`)

`llm_controller/test_vlm.py` tests VLM visual question answering against a live camera frame. Run it from inside the controller container:

```bash
python3 /opt/robot/llm_controller/test_vlm.py "What obstacles are ahead?"
python3 /opt/robot/llm_controller/test_vlm.py "What do you see?" --size 224  # resize before sending
```

It saves the frame and the response to `/opt/robot/` and prints TTFT and throughput (tok/s).

### Tuning vLLM memory

`gpu_memory_utilization` must be set below `free_gpu / total_gpu`. Check with:

```bash
nvidia-smi --query-gpu=memory.free,memory.total --format=csv,noheader
```

Override the default (`0.55`) at runtime:

```bash
GPU_MEM=0.5 bash llm_controller/run_vllm.sh
```

---

## Emergency stop

The `EmergencyStop` ROS 2 service must not be in the stopped state. If the robot is unresponsive, clear the stop:

```bash
ros2 service call /robomaster_max/emergency_stop emergency_stop_msgs/srv/EmergencyStop "{stop: false}"
```

---

## Troubleshooting

### SSL / certificate errors on `git clone`, `apt-get`, or `docker pull`

**Symptom:** Any of the following:
- `server certificate verification failed. CAfile: none CRLfile: none`
- `The certificate chain uses not yet valid certificate.`
- A Docker image build fails during `apt-get update` inside a container with errors like:
  ```
  E: Release file for http://ports.ubuntu.com/ubuntu-ports/dists/jammy-updates/InRelease is not valid yet (invalid for another 18h 18min 38s). Updates for this repository will not be applied.
  ```
  followed by `The command ... returned a non-zero code: 100` and `jetson-containers build` failing after only a few seconds.

**Cause:** The Jetson has no RTC battery. After a cold boot (or long power-off) the hardware clock resets to 1970-01-01, making all TLS certificates appear to be from the future and therefore invalid.

**Fix:**
```bash
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd
timedatectl status   # "Local time" should show the correct date within ~30 s
```

If no internet is available yet, set the time manually:
```bash
sudo date -s "YYYY-MM-DD HH:MM:SS"
```

To persist the correct time to the hardware clock (survives soft reboots, not cold power-loss):
```bash
sudo hwclock --systohc
```

To make NTP sync happen earlier in the boot sequence (recommended):
```bash
sudo systemctl enable systemd-time-wait-sync
```

### Docker pull fails over IPv6 (`connection reset by peer`)

**Symptom:** `docker pull` starts but fails mid-download with `read: connection reset by peer` and the source/destination addresses are IPv6 (e.g. `[2a00:...]:port->[2606:...]:443`).

**Cause:** The Jetson's IPv6 route to GitHub's container CDN (`pkg-containers.githubusercontent.com`) is unstable.

**Fix:** Force the system to prefer IPv4:
```bash
echo 'precedence ::ffff:0:0/96  100' | sudo tee -a /etc/gai.conf
```

If that is insufficient (Docker daemon may bypass `gai.conf`), disable IPv6 at the kernel level:
```bash
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1
```

To make the kernel-level change permanent:
```bash
echo -e 'net.ipv6.conf.all.disable_ipv6=1\nnet.ipv6.conf.default.disable_ipv6=1' | sudo tee -a /etc/sysctl.conf
```

### NVIDIA container runtime not recognised

**Symptom:** `docker run --runtime nvidia ...` fails with `docker: Error response from daemon: unknown or invalid runtime name: nvidia`.

**Cause:** The Docker daemon's `/etc/docker/daemon.json` does not register the NVIDIA container runtime — typically because Docker was installed before `nvidia-container-runtime` or the config was never written.

**Fix:** Write the runtime config and restart Docker:
```bash
sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia"
}
EOF

sudo systemctl daemon-reload && sudo systemctl restart docker
```

This change is permanent — `/etc/docker/daemon.json` is read on every daemon start and survives reboots. Verify Docker starts automatically on boot with:
```bash
sudo systemctl is-enabled docker   # should print "enabled"
# If not:
sudo systemctl enable docker
```