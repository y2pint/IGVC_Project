
---

## 🧩 Setting Up udev Rules for Intel RealSense Cameras (Jetson AGX)

When using Intel RealSense cameras (e.g., D435i, D455, T265) on a Jetson platform—especially inside Docker containers—you need proper `udev` permissions to allow non-root and container access. This is necessary to run reset usb script that is needed with Realsense Camera

### 1. Create udev rule file

Create a new rule file:

```bash
sudo nano /etc/udev/rules.d/99-realsense-all.rules
```

Add the following content:

```bash
# Intel RealSense Cameras (D435i, D455, T265)
SUBSYSTEM=="usb", ATTR{idVendor}=="8086", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTRS{idVendor}=="8086", MODE="0666", GROUP="plugdev"
```

This grants read/write permissions (`0666`) and assigns the device to the `plugdev` group for all Intel USB devices (`8086` vendor ID).

---

### 2. Reload udev rules and apply changes

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Then **unplug and replug** the RealSense camera.

---

### 3. Verify permissions

Find the device path (example from `lsusb`):

```
Bus 002 Device 004: ID 8086:0b5c Intel Corp. Intel(R) RealSense(TM) Depth Camera D455
```

Check permissions:

```bash
ls -l /dev/bus/usb/002/004
```

Expected output:

```
crw-rw-rw- 1 root plugdev 189,131 ... /dev/bus/usb/002/004
```

