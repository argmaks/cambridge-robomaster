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
| `cam_driver/` | CSI camera → ROS 2 image pipeline using jetson-utils. Two nodes: `camera_source` (raw capture) and `camera_proc` (rectify/resize). Installed as `camera_stream_0.service`. |
| `cam_driver_gscam2/` | Alternative GStreamer-based camera pipeline (`gscam2`). Swap-in for `cam_driver/`. |
| `camera_utils/` | Shell scripts to tune Jetson BPMP hardware clocks (VI, ISP, NVCSI) for maximum camera throughput. |
| `joycon/` | Dockerized ROS 2 joystick node (`game_controller_node`). Publishes controller input to `/<robot_ns>/joy`. |
| `ui/` | On-robot operator UI: SSD1306 OLED (I2C), GPIO button, battery/wheel state display, emergency stop client. |
| `emergency_stop/` | Central emergency stop controller for a Raspberry Pi. Discovers all `EmergencyStop` services on the ROS graph and fans out stop/resume on physical button press. NeoPixel ring shows per-robot status. |
| `unitree/` | ROS 2 bridge for the Unitree Go1 quadruped. Subscribes to `cmd_vel` and sends UDP commands via `unitree_legged_sdk`. Registered in the fleet as `robomaster_20`. |
| `adhoc/` | Ad-hoc Wi-Fi setup (`wlan1`, SSID `roboAdHoc`, `10.3.2.x`) for robot-to-robot mesh networking. Also contains fleet-wide firewall helpers and a Fast DDS profile. |
| `setup/` | Jetson provisioning: apt packages, user creation, `nmcli` Wi-Fi profile for the `robomaster` network (`10.3.1.x`). |
| `docker/` | Helpers to pull images from the private registry (`10.3.0.22:5000`) and set the NVIDIA container runtime as Docker default. |

**Network layout:**
- Infrastructure Wi-Fi: `wlan0`, `10.3.1.x` — robots are `robomaster-1`, `robomaster-2`, etc.
- Ad-hoc mesh: `wlan1`, `10.3.2.x`
- Robot namespaces in ROS 2 match the hostname: `robomaster_1`, `robomaster_2`, etc.

---

## First-Time Setup (per Jetson)

### 1. Set hostname and passwordless sudo

```bash
sudo ./setup/sudocfg.bash       # allow nvidia user to run sudo without password
sudo vim /etc/hostname           # set to e.g. robomaster-1
sudo reboot
```

### 2. Set up Docker

```bash
sudo ./docker/add_group.bash
sudo ./docker/setup_docker_compose.bash
sudo cp docker/daemon.json /etc/docker/
sudo service docker restart
```

### 3. Provision the OS

```bash
sudo bash setup/setup.bash
```

### 4. Install and start the CAN bridge

```bash
cd robomaster_bridge
sudo bash install.bash
# reboot if prompted for CAN interface changes
bash robomaster_bridge/run_docker.sh
```

### 5. (Optional) Install the camera service

```bash
cd cam_driver
sudo bash install.bash
```

### 6. (Optional) Install and run the UI service

```bash
cd ui
sudo bash install.bash
bash ui/run_docker.sh
```

---

## Controlling a Robot

### Prerequisites

ROS 2 is **not installed natively** on the Jetson host — it lives inside Docker. Use the `ros2_panoptes_control` container:

```bash
bash /home/nvidia/ros2_panoptes/docker/control/run_docker.sh
```

Inside the container, source the workspace:

```bash
source /opt/ros/humble/install/setup.bash
source /opt/robomaster/install/setup.bash
```

### Sending velocity commands (`cmd_vel`)

The bridge subscribes to `geometry_msgs/msg/Twist` on `/<robot_ns>/cmd_vel`.

**Always publish at `-r 10` Hz or higher.** Publishing at the default 1 Hz causes the firmware watchdog to cut motor power between messages, resulting in a "twitching" effect.

```bash
# Move forward
ros2 topic pub -r 10 /robomaster_2/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.1, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Strafe right
ros2 topic pub -r 10 /robomaster_2/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.1, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Rotate clockwise (turn right)
ros2 topic pub -r 10 /robomaster_2/cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.5}}"

# Stop
ros2 topic pub --once /robomaster_2/cmd_vel geometry_msgs/msg/Twist "{}"
```

### Coordinate system

The robot uses a **right-handed, Z-down** frame (NED-style):

| Axis | Direction | Notes |
|---|---|---|
| X | Forward | `linear.x` positive = forward |
| Y | Right | `linear.y` positive = strafe right |
| Z | Down | `angular.z` positive = **clockwise** (turn right) |

This is the **opposite** of ROS REP-103 (Z-up, CCW positive). Negate `angular.z` when mixing with standard ROS sensors.



### Velocity limits (simulator reference)

The values below are the clamp limits defined in `ros2_panoptes/src/simple_simulator/simple_simulator/simple_robomaster.py` and likely reflect DJI's documented hardware limits. They are **not enforced by the real bridge** — treat them as a safe operating guideline until verified on hardware.

| Field | Max |
|---|---|
| `linear.x` | ±3.5 m/s |
| `linear.y` | ±2.8 m/s |
| `angular.z` | ±10.5 rad/s |

### Sending raw wheel RPM commands (`cmd_wheels`)

For direct wheel control, publish `robomaster_msgs/msg/WheelSpeed` to `/<robot_ns>/cmd_wheels`. Use **`-r 50` Hz** — the firmware requires a sustained command stream at this rate.

```bash
ros2 topic pub -r 50 /robomaster_2/cmd_wheels robomaster_msgs/msg/WheelSpeed \
  "{fr: 200, fl: 200, rl: 200, rr: 200}"
```

RPM range is **-1000 to 1000** per wheel (`fl` = front-left, `fr` = front-right, `rl` = rear-left, `rr` = rear-right).

---

## Camera

### Overview

The `cam_driver/` service runs two nodes under `/<robot_ns>/camera_0/`:

| Node | Subscribes | Publishes | Description |
|---|---|---|---|
| `camera_source` | — | `image_raw`, `camera_info` | Captures from CSI camera at 1920×1080 @ 15 fps via NVIDIA Argus |
| `camera_proc` | `image_raw`, `camera_info` | `image_proc` | Fisheye undistortion + downscale to 224px height, 120° FOV |

`image_proc` is the ML-ready output (≈398×224). Use `image_raw` for full resolution.

The camera service starts automatically on boot via `camera_stream_0.service` (installed by `sudo bash cam_driver/install.bash`). It has a 30-second pre-start delay to wait for the Argus daemon.

> **Note:** Cyclone DDS in the camera container is pinned to `wlan0` — you must be on the same Wi-Fi network to receive image topics from another machine.

### Grabbing a sample image

`grab_image.py` (in this repo) subscribes to an image topic and saves one frame to disk. Run it from inside the `ros2_panoptes_control` container:

```bash
# Start the container (Robot/ is mounted at /opt/Robot)
bash /home/nvidia/ros2_panoptes/docker/control/run_docker.sh

# Inside the container — save the processed stream (398x224, default)
python3 /opt/Robot/grab_image.py

# Save the raw full-resolution stream (1920x1080)
python3 /opt/Robot/grab_image.py /robomaster_2/camera_0/image_raw /opt/Robot/raw.jpg
```

The image is written to `/home/nvidia/Robot/camera_sample.jpg` on the host.

> **QoS note:** The camera publishes with `best_effort` reliability (`qos_profile_sensor_data`). Subscribing with the default `reliable` QoS will silently receive nothing — `grab_image.py` already handles this correctly.

---

### Emergency stop

The `EmergencyStop` ROS 2 service must not be in the stopped state. If the robot is unresponsive, clear the stop:

```bash
ros2 service call /robomaster_2/emergency_stop emergency_stop_msgs/srv/EmergencyStop "{stop: false}"
```