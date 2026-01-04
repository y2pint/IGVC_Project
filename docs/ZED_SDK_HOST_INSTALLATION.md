# ZED SDK Installation (Jetson Orin AGX – Host Native)

This document describes the **host-native installation of the Stereolabs ZED SDK** on **NVIDIA Jetson Orin AGX** running **JetPack 6.x (L4T 36.x)**, followed by required post-installation setup for ROS 2 and navigation.

This setup is validated on:
- Jetson Orin AGX
- Ubuntu 22.04 (JetPack 6.x, L4T 36.4+)
- ZED / ZED2 / ZED2i cameras

---

## 1. Verify JetPack / L4T Version (Required)

```bash
cat /etc/nv_tegra_release
````

Expected output contains:

```
R36 (release), REVISION: 4.x
```

> The ZED SDK **must match the L4T version**.
> Do not proceed if you are not on L4T 36.x.

---

## 2. Install System Dependencies

```bash
sudo apt update
sudo apt install -y \
    lsb-release \
    wget \
    less \
    zstd \
    udev \
    sudo \
    apt-transport-https \
    libusb-1.0-0 \
    libgl1 \
    libegl1
```

---

## 3. Download ZED SDK Installer (Jetson)

For JetPack 6 / L4T 36.4+:

```bash
cd /tmp
wget -O ZED_SDK_Linux.run \
https://stereolabs.sfo2.cdn.digitaloceanspaces.com/zedsdk/4.2/ZED_SDK_Tegra_L4T36.4_v4.2.2.zstd.run
chmod +x ZED_SDK_Linux.run
```

---

## 4. Install ZED SDK (Recommended Method)

On Jetson, CUDA **runtime** is installed by JetPack, but `nvcc` is **not installed by default**.
The ZED SDK does **not** require `nvcc`.

### Recommended (Silent, Safe on Jetson)

```bash
sudo ./ZED_SDK_Linux.run silent skip_python
```

This:

* Uses system-managed CUDA
* Avoids unnecessary CUDA compiler installation
* Is the recommended approach on Jetson

---

## 5. Verify Installation

### Check ZED Explorer

```bash
/usr/local/zed/tools/ZED_Explorer
```

You should see:

* Camera detected
* Live image stream
* IMU data (ZED2i)

A message like below is expected and good:

```
[SVO] Hardware compression (NVENC) available
```

---

## 6. Fix User Permissions (Important)

ZED tools should **not** require `sudo`.

### Add user to required groups

```bash
sudo usermod -aG video,plugdev,render $USER
```

### Reload udev rules

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Replug the camera and log out/in (or reboot)

```bash
sudo reboot
```

After reboot, verify:

```bash
/usr/local/zed/tools/ZED_Explorer
```

> ZED Explorer should now run **without sudo**.

---

## 7. Environment Variables (Usually Auto-Set)

Verify:

```bash
echo $ZED_SDK_ROOT
```

Expected:

```
/usr/local/zed
```

If missing:

```bash
echo 'export ZED_SDK_ROOT=/usr/local/zed' >> ~/.bashrc
source ~/.bashrc
```

---

## 8. CUDA Notes (Jetson-Specific)

* CUDA **is provided by JetPack**
* `nvcc` is **not required** for ZED SDK
* Do **not** install NVIDIA CUDA runfiles manually
* Do **not** downgrade or overwrite system CUDA

If `nvcc` is ever required for development:

```bash
sudo apt install cuda-compiler-12-6
```

---

## 9. Next Steps (Remaining Setup)

After ZED SDK installation:

1. Install `zed-ros2-wrapper` (SDK 4.2 compatible)
2. Launch **ZED VIO only** (no GPS)
3. Verify TF tree: `map → odom → base_link`
4. Fuse GPS later using `robot_localization`
5. Integrate with Nav2

---

## 10. Common Issues

### ZED Explorer works only with sudo

* User not in `video` / `plugdev` groups
* udev rules not reloaded
* Session not restarted

### Installer complains about missing CUDA

* Expected on Jetson
* Use `silent skip_python` install method

---

## References

* [https://www.stereolabs.com/docs](https://www.stereolabs.com/docs)
* [https://github.com/stereolabs/zed-docker](https://github.com/stereolabs/zed-docker)
* [https://developer.nvidia.com/embedded/jetpack](https://developer.nvidia.com/embedded/jetpack)

---