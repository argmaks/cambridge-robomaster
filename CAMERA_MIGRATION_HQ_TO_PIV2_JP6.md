# JP5 → JP6 Camera Migration Guide

Migrating the Cambridge RoboMaster camera stack from **JetPack 5 (L4T r35.x) + HQ camera**
to **JetPack 6.2.1 (L4T r36.4) + Raspberry Pi v2 (IMX219)**.

The active camera driver after migration is `cam_driver_gscam2/`.
`cam_driver/` (jetson-utils) requires a separately-built custom image and is documented separately below.

---

## 1. Environment differences

| | JP5 | JP6 |
|---|---|---|
| L4T version | r35.3.1 | r36.4.x |
| Base Docker image | `dustynv/ros:humble-pytorch-l4t-r35.3.1` | `dustynv/ros:humble-desktop-l4t-r36.4.0` |
| VPI | 2.x | 3.x |
| Camera | HQ (fisheye, 120° FOV) | Raspberry Pi v2 IMX219 |
| Camera driver | `cam_driver/` (jetson-utils) | `cam_driver_gscam2/` (gscam2) |
| GStreamer NVIDIA plugins | Pre-installed on host | Stubs in container — must be extracted from `nvidia-l4t-gstreamer` |
| `nvvidconv` output formats | RGB, RGBA, I420, … | **No RGB** — use RGBA or I420 |

---

## 2. `cam_driver_gscam2/` — issues and fixes

### 2.1 Expired ROS 2 apt signing key

**Symptom:** `apt-get update` fails inside the container with:
```
EXPKEYSIG F42ED6FBAB17C654 Open Robotics
E: The repository 'http://packages.ros.org/ros2/ubuntu jammy InRelease' is not signed.
```

**Fix:** Refresh the key before the first `apt-get update` in the Dockerfile:
```dockerfile
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    apt-get update && apt-get install -y git nano
```

---

### 2.2 NVIDIA GStreamer plugins are 0-byte stubs

**Symptom:** `gst-plugin-scanner` warns `file too short` for every `libgstnv*.so`.
`gst-inspect-1.0 nvarguscamerasrc` fails. Camera container starts but publishes no frames.

**Root cause:** `dustynv/ros:humble-desktop-l4t-r36.4.0` ships placeholder 0-byte `.so` files for the NVIDIA GStreamer plugins. The real implementations come from the `nvidia-l4t-gstreamer` apt package, but installing it normally fails because its dependency `nvidia-l4t-core` has a preinstall script that checks `/proc/device-tree/compatible`, which does not exist during a Docker build.

**Verify stubs are present:**
```bash
docker run --rm dustynv/ros:humble-desktop-l4t-r36.4.0 \
  ls -la /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvarguscamerasrc.so
# Expected bad output: size 0
```

**Fix:** Add the NVIDIA L4T apt source, then download and *extract* only the plugin `.so` files using `dpkg-deb --extract` (bypasses all pre/post-install scripts):

```dockerfile
RUN echo "deb https://repo.download.nvidia.com/jetson/common r36.4 main" \
        > /etc/apt/sources.list.d/nvidia-l4t.list && \
    echo "deb https://repo.download.nvidia.com/jetson/t234 r36.4 main" \
        >> /etc/apt/sources.list.d/nvidia-l4t.list && \
    apt-key adv --fetch-keys \
        https://repo.download.nvidia.com/jetson/jetson-ota-public.asc && \
    apt-get update && \
    cd /tmp && apt-get download nvidia-l4t-gstreamer && \
    dpkg-deb --extract nvidia-l4t-gstreamer_*.deb /tmp/l4t-gst && \
    cp /tmp/l4t-gst/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv*.so \
       /usr/lib/aarch64-linux-gnu/gstreamer-1.0/ && \
    rm -rf /tmp/l4t-gst /tmp/nvidia-l4t-gstreamer_*.deb
```

**Verify fix:**
```bash
docker run --rm cam_driver:latest \
  ls -lh /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvarguscamerasrc.so
# Expected: non-zero size (~76K)
```

The Argus shared libraries (`libnvargus.so`, etc.) the plugin links against are already present in the base image at `/usr/lib/aarch64-linux-gnu/nvidia/`.

---

### 2.3 gscam2 patch no longer applies

**Symptom:** `git apply gscam_failure_exit.patch` fails:
```
error: patch failed: src/gscam_node.cpp:310
error: src/gscam_node.cpp: patch does not apply
```

**Root cause:** The patch was written for the version of gscam2 that uses the blocking `gst_app_sink_pull_sample`. Newer gscam2 switched to `gst_app_sink_try_pull_sample` (with a timeout) and restructured the failure handling — the patch context no longer matches.

**Fix:** Pin the gscam2 clone to commit `7cf5e85` ("Add skip parameter to reduce frame rates"), the last commit that still uses the blocking API:
```dockerfile
RUN git clone https://github.com/clydemcqueen/gscam2.git && \
    cd gscam2 && git checkout 7cf5e85
```

---

### 2.4 Wrong GStreamer caps — `format=RGB` not supported by `nvvidconv` on JP6

**Symptom:** Pipeline starts, Argus reports "Producer has connected", but gscam2 publishes no frames and no error is logged.

**Diagnosis:** Test the pipeline directly inside the container:
```bash
gst-launch-1.0 nvarguscamerasrc sensor-id=0 sensor-mode=2 num-buffers=3 ! \
  'video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1' ! \
  nvvidconv ! 'video/x-raw,format=RGB' ! fakesink
# Output: "could not link nvvconv0 to ..., nvvconv0 can't handle caps video/x-raw, format=(string)RGB"
```

**Fix:** Replace `format=RGB` with a format `nvvidconv` actually supports.
- For JPEG output: use `format=I420` before `jpegenc`
- For raw output: use `format=RGBA` before `videoconvert`

Confirmed working formats for `nvvidconv` output on JP6: `NV12`, `RGBA`, `BGRA`, `I420`.

---

### 2.5 Missing `format=(string)NV12` in nvarguscamerasrc caps

**Symptom:** Pipeline may fail to negotiate or produces garbled frames.

**Root cause:** The carrier board manufacturer specifies `format=(string)NV12` as a required property in the NVMM caps. Without it, GStreamer may pick an incompatible format.

**Fix:** Always include `format=(string)NV12` in the caps filter after `nvarguscamerasrc`:
```
nvarguscamerasrc sensor-id=0 sensor-mode=2 !
  video/x-raw(memory:NVMM),width=(int)1920,height=(int)1080,format=(string)NV12,framerate=(fraction)30/1 !
  nvvidconv ...
```

---

### 2.6 Wrong sensor-mode for Pi v2 at 1920×1080

**Pi v2 (IMX219) sensor modes on JP6:**

| Mode | Resolution | FPS |
|------|-----------|-----|
| 0 | 3280×2464 | 21 |
| 1 | 3280×1848 | 28 |
| **2** | **1920×1080** | **30** |
| 3 | 1640×1232 | 30 |
| 4 | 1280×720 | 60 |

The original config used `sensor-mode=1` (from the HQ camera). For Pi v2 at 1920×1080, use **`sensor-mode=2`**.

---

### 2.7 `videoflip` does not work with NVMM buffers

**Root cause:** The original pipeline used a separate `videoflip method=vertical-flip` element after `nvvidconv`. `videoflip` cannot operate on NVMM (GPU) memory.

**Fix:** Use `nvvidconv`'s built-in `flip-method` property instead:
```
nvvidconv flip-method=6   # 6 = vertical flip
```

---

### 2.8 Stray `'` in original pipeline strings

The original `cam_param_jpg.yaml` and `cam_param_raw.yaml` had a stray `'` inside the pipeline string (after `framerate=20/1'`) which would cause GStreamer to fail parsing. Fixed when rewriting the pipelines.

---

## 3. Final working GStreamer pipelines

**JPEG (default, `cam_param_jpg.yaml`):**
```
nvarguscamerasrc sensor-id=0 sensor-mode=2 !
  video/x-raw(memory:NVMM),width=(int)1920,height=(int)1080,format=(string)NV12,framerate=(fraction)30/1 !
  nvvidconv flip-method=6 !
  video/x-raw,format=I420 !
  jpegenc quality=95
```
Publishes: `/<ns>/camera_0/image_raw/compressed` (`sensor_msgs/CompressedImage`)

**Raw (`cam_param_raw.yaml`):**
```
nvarguscamerasrc sensor-id=0 sensor-mode=2 !
  video/x-raw(memory:NVMM),width=(int)1920,height=(int)1080,format=(string)NV12,framerate=(fraction)30/1 !
  nvvidconv flip-method=6 !
  video/x-raw,format=RGBA !
  videoconvert
```
Publishes: `/<ns>/camera_0/image_raw` (`sensor_msgs/Image`)

---

## 4. `cam_driver/` (jetson-utils) — JP6 changes ⚠️ UNPROVEN

> **Status: proposed changes only — not yet verified.**
> Migration stalled at the `vision_base` build step (see §4.1).
> The code changes described here have been applied to the repo but have not been built or tested end-to-end.
> Use `cam_driver_gscam2/` (§2–3) for a working camera on JP6.

`cam_driver/` is not used on JP6 by default. The following changes are required to make it buildable:

### 4.1 New base image via jetson-containers

`dustynv/ros:humble-pytorch-l4t-r35.3.1` does not exist for r36.x. A replacement `vision_base` image must be built first via jetson-containers.

**`cam_driver/install.bash` automates this:** it checks whether `vision_base:latest` exists and, if not, runs the jetson-containers build before building `cam_driver_dnv:latest`. Concretely it runs:

```bash
WITH_CUDSS=0 CUDA_VERSION=12.6 jetson-containers build \
    --base=ros-humble-fixed:l4t-r36.4.0 \
    --name=vision_base \
    l4t-pytorch
```

So in principle, `sudo bash cam_driver/install.bash` should be sufficient. **This is where progress stalled** — the `vision_base` build had not successfully completed at the time of writing.

**Prerequisite:** `jetson-containers` must be installed on the host (`pip install jetson-containers` or clone from [github.com/dusty-nv/jetson-containers](https://github.com/dusty-nv/jetson-containers)).

**Note on the base image:** `dustynv/ros:humble-desktop-l4t-r36.4.0` ships an expired ROS 2 GPG key (expired ~May 2025), which causes `apt-get update` to fail during the jetson-containers build. `Dockerfile.ros-base-fixed` (in the repo root) patches the key. The `install.bash` build command uses `ros-humble-fixed:l4t-r36.4.0` as its base, so build that first if it doesn't already exist:

```bash
cd /home/nvidia/Robot
docker build -t ros-humble-fixed:l4t-r36.4.0 -f Dockerfile.ros-base-fixed .
```

### 4.2 VPI version

`find_package(VPI 2.0)` → `find_package(VPI)` in `CMakeLists.txt`.
JP6 ships VPI 3.x; removing the version constraint lets CMake find whichever version is present.
VPI is only found but not actually linked, so this is a safe no-op change.

### 4.3 Camera calibration and FOV (Pi v2 vs HQ fisheye)

`camera_proc` parameters updated in `camera.launch.py`:

| Parameter | HQ fisheye | Pi v2 IMX219 |
|---|---|---|
| `fov` | 120.0° | 54.0° |
| `aperture_width` | 6.287 mm | 3.68 mm |
| `aperture_height` | 4.712 mm | 2.07 mm |

Calibration files (`front_camera.yaml`) updated with approximate Pi v2 values:
- `fx = fy ≈ 617.0` px, `cx ≈ 960`, `cy ≈ 540`
- Distortion: `k1 ≈ 0.158, k2 ≈ -0.254, p1 = p2 ≈ 0.0`

**These are nominal values.** Run `ros2 run camera_calibration cameracalibrator` with a checkerboard for accurate intrinsics.

---

## 5. `camera_utils/` — JP6 compatibility

The BPMP sysfs clock names differ between Jetson generations. Both scripts now check whether a path exists before reading/writing and also try the JP6/Orin names (`vi0`, `vi1`) alongside the JP5 name (`vi`).

---

## 6. Debugging checklist

When a camera container starts but publishes no frames:

1. **Check plugin sizes** — `ls -lh /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv*.so` — all should be non-zero.
2. **Test pipeline directly** inside the container with `gst-launch-1.0 ... ! fakesink` — this isolates GStreamer from ROS.
3. **Check caps negotiation** — add `-v` to `gst-launch-1.0`; look for `could not link` or `caps … not compatible`.
4. **Check topic list** — `ros2 topic list` shows publisher exists but `ros2 topic echo --once` returns nothing → QoS mismatch or pipeline not producing frames.
5. **Check Argus daemon** — `systemctl status nvargus-daemon` must be `active`; `/tmp/argus_socket` must exist and be bind-mounted into the container.
