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

```bash
# 1. Provision the OS
sudo bash setup/setup.bash

# 2. Install and start the CAN bridge (requires reboot)
cd robomaster_bridge
sudo bash install.bash
# reboot

# 3. (Optional) Install the camera service
cd cam_driver
sudo bash install.bash

# 4. (Optional) Install the UI service
cd ui
sudo bash install.bash
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



### Emergency stop

The `EmergencyStop` ROS 2 service must not be in the stopped state. If the robot is unresponsive, clear the stop:

```bash
ros2 service call /robomaster_2/emergency_stop emergency_stop_msgs/srv/EmergencyStop "{stop: false}"
```
