## 🧩 Setting Up udev Rules and Hotplug Support for Intel RealSense and Pixhawk (Jetson AGX)

When using **Intel RealSense cameras** (e.g., D435, D435i, D455, T265) and a **Pixhawk flight controller** on a Jetson platform—**especially inside Docker containers**—proper **host-side `udev` configuration** is required to allow non-root and containerized access to USB devices.

These host-side rules are essential for enabling:

* **USB hotplug and recovery mechanisms** for RealSense cameras (via NVIDIA’s Docker stack)
* **Stable serial device naming and access** for Pixhawk

Without correct host-side `udev` rules, devices may fail to recover from USB power events or become inaccessible inside containers.

---

## ⚠️ Critical Note on USB Power Sleep / Suspend Issue (RealSense)

The **USB power sleep / suspend issue was a critical problem** in this system.

Before applying the correct host-side `udev` configuration, RealSense cameras could:

* Become unresponsive after low-power or suspend states
* Fail to re-enumerate on USB
* Require a full system reboot to recover

After installing the proper `udev` rules and enabling NVIDIA’s hotplug mechanism, the cameras now **recover reliably** from USB power state changes without manual intervention or reboot.

---

## 🔄 NVIDIA Hotplug Reset Script (Docker-Provided, RealSense)

The USB hotplug and recovery logic for RealSense cameras **is provided by NVIDIA** and is included as part of the **Docker-based RealSense / Isaac ROS setup**.
This mechanism relies on **host-side `udev` events** to function correctly.

In the NVIDIA container environment, this typically includes:

* A hotplug reset script:

  ```text
  /opt/realsense/hotplug-realsense.sh
  ```
* A corresponding `udev` rule installed on the host (or mounted into the container):

  ```text
  99-realsense-libusb-custom.rules
  ```

### How it works

* `udev` runs on the **host**, not inside Docker
* When a RealSense USB device is added or removed, the host `udev` rule:

  * Triggers the NVIDIA hotplug script
  * Recreates the USB device node with correct permissions
  * Makes the device visible and usable inside the container

This hotplug script is automatically invoked when a RealSense camera is:

* Plugged in or re-enumerated
* Recovered from USB suspend or power sleep
* Restarted while a Docker container is running

The script ensures the camera is properly re-initialized for use by `librealsense` and ROS 2 nodes.

---

## 1. Host-Side udev Rules for Intel RealSense Cameras

Create a new rule file **on the Jetson host**:

```bash
sudo nano /etc/udev/rules.d/99-realsense-all.rules
```

Add the following content:

```bash
# Intel RealSense Cameras (D435, D435i, D455, T265)
SUBSYSTEM=="usb", ATTR{idVendor}=="8086", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTRS{idVendor}=="8086", MODE="0666", GROUP="plugdev"
```

This configuration:

* Grants read/write permissions (`0666`)
* Assigns the device to the `plugdev` group
* Applies to all Intel RealSense cameras using vendor ID `8086`
* Enables NVIDIA’s hotplug reset script to function correctly

---

## 2. Reload udev Rules and Apply Changes

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then **unplug and replug** the RealSense camera.

---

## 3. Verify RealSense Permissions

Identify the device using `lsusb`:

```text
Bus 002 Device 004: ID 8086:0b5c Intel Corp. Intel(R) RealSense(TM) Depth Camera D455
```

Check the device permissions:

```bash
ls -l /dev/bus/usb/002/004
```

Expected output:

```text
crw-rw-rw- 1 root plugdev 189,131 ... /dev/bus/usb/002/004
```

---

## Note on RealSense D435 vs D435i

The same `udev` rule applies to **both D435 and D435i**, as they share the same Intel USB vendor ID (`8086`).
No model-specific rules are required.

---

## 🧩 udev Rules for Pixhawk (Serial Device Stability)

When using a **Pixhawk flight controller** (PX4 or ArduPilot) on Jetson—particularly with ROS 2 and Docker—a **host-side udev rule is strongly recommended** to ensure:

* Stable serial device naming
* Non-root access
* Reliable reconnection after USB resets or reboots

Without a dedicated rule, Pixhawk may appear as `/dev/ttyACM0`, `/dev/ttyACM1`, etc., unpredictably.

---

## 4. Host-Side udev Rule for Pixhawk

Create a Pixhawk-specific rule file:

```bash
sudo nano /etc/udev/rules.d/99-pixhawk.rules
```

Add the following content:

```bash
# Pixhawk (PX4 / ArduPilot)
SUBSYSTEM=="tty", ATTRS{idVendor}=="26ac", ATTRS{idProduct}=="0011", \
MODE="0666", GROUP="dialout", SYMLINK+="pixhawk"
```

### Notes

* `GROUP="dialout"` is standard for serial devices
* `SYMLINK+="pixhawk"` creates a persistent device:

  ```text
  /dev/pixhawk
  ```

If your Pixhawk reports a different vendor/product ID, verify with:

```bash
lsusb
```

or:

```bash
udevadm info -a -n /dev/ttyACM0
```

---

## 5. Reload udev Rules (Pixhawk)

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then **unplug and replug** the Pixhawk.

Verify:

```bash
ls -l /dev/pixhawk
```

Expected output:

```text
/dev/pixhawk -> ttyACM0
```

---

## Docker Notes (Pixhawk)

When running inside Docker, pass the device explicitly:

```bash
--device=/dev/pixhawk
```

With the udev rule in place, **no privileged container is required**.

---

## ✅ Final Result

With proper **host-side `udev` configuration**:

### RealSense

* Reliable recovery from USB power sleep and suspend
* Stable operation across Docker restarts
* No reboot required after USB faults

### Pixhawk

* Stable serial device naming
* Non-root access from ROS 2 and Docker
* Reliable reconnection after USB resets

This configuration is **strongly recommended** for production, research, and competition systems (e.g., IGVC) using Jetson AGX with RealSense and Pixhawk.