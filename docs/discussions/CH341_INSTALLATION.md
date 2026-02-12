Absolutely. Below is a **clean, copy-paste–ready Markdown guide** you can drop into a repo (`README.md`) or lab wiki.
It documents **exactly** what you did and why, and it is appropriate for Jetson Orin (Nano / AGX).

---

# Installing CH341 USB-Serial Driver on NVIDIA Jetson Orin (JetPack 6 / Kernel 5.15)

## Overview

NVIDIA Jetson Orin platforms (JetPack 6, kernel `5.15.x-tegra`) **do not ship with CH341/CH340 USB-serial support enabled**.
As a result, common Arduino Nano / CH340 devices will **not appear** as `/dev/ttyUSB*` by default.

This guide explains how to install and use the **NVIDIA-recommended out-of-tree CH341 driver**, which registers devices as:

```
/dev/ttyCH341USB0
```

This method is confirmed to work on:

* Jetson Orin Nano
* Jetson AGX Orin
* Ubuntu 22.04
* Kernel `5.15.148-tegra`

---

## Symptoms (Before Installation)

When plugging in a CH340/CH341 device:

* No `/dev/ttyUSB*` appears
* `lsusb` shows:

  ```
  1a86:7523 QinHeng Electronics CH340 serial converter
  ```
* `dmesg` does **not** show a serial attachment

---

## Solution Summary

We install an **out-of-tree kernel module (`ch341.ko`)** provided via NVIDIA Developer Forums.

The driver:

* Is **not** controlled by `CONFIG_USB_SERIAL_CH341`
* Loads independently of kernel config
* Registers device nodes as `ttyCH341USB*`

---

## Step 1 — Verify Kernel Version

```bash
uname -r
```

Expected:

```
5.15.xxx-tegra
```

> ⚠️ The module **must match the exact kernel version**.

---

## Step 2 — Obtain the CH341 Driver

### Option A (Recommended): Copy from a working Jetson

If you already have a Jetson (Nano/AGX) where CH341 works:

```bash
/lib/modules/5.15.148-tegra/extra/ch341.ko
```

Copy it to the target machine.

### Option B: Build from Source (Reference)

NVIDIA forum reference:
[https://forums.developer.nvidia.com/t/notice-of-new-updated-usb-serial-converter-driver-ch341/298186](https://forums.developer.nvidia.com/t/notice-of-new-updated-usb-serial-converter-driver-ch341/298186)

(Compilation instructions vary; copying a known-good module is safer.)

---

## Step 3 — Install the Driver

```bash
sudo mkdir -p /lib/modules/$(uname -r)/extra
sudo cp ch341.ko /lib/modules/$(uname -r)/extra/
```

Register and load:

```bash
sudo depmod -a
sudo modprobe usbserial
sudo modprobe ch341
```

Verify:

```bash
lsmod | grep ch341
```

Expected:

```
ch341  <size>  0
```

---

## Step 4 — Plug in the Device and Verify

Unplug and replug the CH340/CH341 device.

```bash
dmesg | tail -n 40
```

Expected output:

```
usb_ch341 ... ttyCH341USB0: ch341 USB device
```

Verify device node:

```bash
ls -l /dev/ttyCH341USB*
```

Expected:

```
/dev/ttyCH341USB0
```

---

## Step 5 — Make Driver Load Automatically (Recommended)

```bash
echo ch341 | sudo tee /etc/modules-load.d/ch341.conf
```

---

## Step 6 — Create Stable udev Symlink (Recommended)

Create a udev rule:

```bash
sudo nano /etc/udev/rules.d/99-igvc-serial.rules
```

Add:

```udev
# CH341 / CH340 (NVIDIA OOT driver)
SUBSYSTEM=="tty", KERNEL=="ttyCH341USB*", \
  ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", \
  SYMLINK+="arduino_led", MODE="0666"
```

Reload rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Verify:

```bash
ls -l /dev/arduino_led
```

Expected:

```
/dev/arduino_led -> ttyCH341USB0
```

---

## Permissions Note (Docker / ROS)

* `MODE="0666"` avoids:

  * `dialout` group issues
  * Docker user/group mismatch
* This is common and acceptable for **robot development systems**

If stricter security is required later, change to `0660` and manage groups explicitly.

---

## Step 7 — Test with Python

```python
import serial, time

s = serial.Serial("/dev/arduino_led", 115200, timeout=1)
time.sleep(2)
s.write(b"MODE AUTO\n")
print(s.readline())
s.close()
```

If you see a response, the driver is working correctly.

---

## Notes & Limitations

* This is an **out-of-tree driver**
* Kernel updates may require reinstalling the module
* For long-term maintenance, consider wrapping as a **DKMS package**

---

## Summary

✅ CH341 is **not enabled by default** on Jetson Orin
✅ NVIDIA provides a supported out-of-tree driver
✅ Device appears as `ttyCH341USB*`
✅ Use udev to create a stable symlink
✅ Works cleanly with Docker + ROS 2

---

If you want, next I can:

* Convert this into a **DKMS install guide**
* Add **Pixhawk + Arduino combined udev rules**
* Provide a **ROS 2 serial node template**

Just tell me.
