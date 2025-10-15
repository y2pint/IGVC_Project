Great idea — documenting your **VESC setup** in markdown will make it much easier to maintain and share later (especially if you're working across ROS 2, Teensy, or Orin).

Let’s start by structuring a `VESC_SETUP.md` file. Below is a clean, extensible template you can edit directly or expand as your project grows.

---

### 📄 **VESC_SETUP.md**

````markdown
# VESC Setup Guide

This document explains how to configure and connect a VESC (Vedder Electronic Speed Controller) for use with the autonomous RC truck project.

---

## 1. Hardware Overview

- **Motor:** [Insert model, e.g., 1/8 scale 4-pole BLDC motor]
- **ESC:** Flipsky VESC 6.7 (or specify model)
- **Controller:** Teensy / Arduino
- **Host Computer:** Jetson AGX Orin
- **Battery:** [e.g., 4S LiPo, 14.8 V, 5000 mAh]
- **Communication Interface:** UART / CAN / USB

---

## 2. Software Requirements

### On PC or Jetson
- [VESC Tool](https://vesc-project.com/vesc_tool)
- USB connection to VESC
- Optional: ROS 2 VESC driver (e.g., `vesc_driver` or `vesc_msgs`)

### On Microcontroller
- Serial communication (UART)
- Custom control code for sending target duty, current, or RPM

---

## 3. Initial VESC Configuration

### Step 1: Connect VESC Tool
1. Plug VESC into your computer via USB.
2. Open **VESC Tool** → `Connect`.
3. Confirm firmware version and update if needed.

### Step 2: Motor Detection
1. Go to **Motor Settings → FOC → Motor Detection**.
2. Run detection and verify smooth rotation.
3. Save configuration.

### Step 3: App Settings
- Navigate to **App Settings → General → App to use**:
  - Select **UART** (for serial control) or **PPM** (for RC input).
- Set **UART baud rate** (e.g., `115200`).
- Enable **Send status over UART** if used for telemetry.

### Step 4: Safety & Limits
- **Voltage cutoffs:**
  - Minimum: e.g., `12 V`
  - Maximum: e.g., `25 V`
- **Current limits:**
  - Motor current max: `40 A`
  - Battery current max: `30 A`
- **Temperature limits:** default or adjusted for your setup.

---

## 4. UART / CAN Wiring

| Pin | Signal | Connects To | Notes |
|-----|---------|-------------|-------|
| TX  | UART TX | MCU RX | 3.3 V logic |
| RX  | UART RX | MCU TX | 3.3 V logic |
| GND | Ground  | Common ground | Must be shared |
| 5V  | Power (optional) | Teensy VIN | Only if needed |

⚠️ **Important:** VESC UART uses 3.3 V logic. Do **not** connect to 5 V RX/TX pins directly without level shifting.

---

## 5. Testing UART Commands

Example: send `Get Values` command (0x04) and verify return packet.

You can use Python for quick test:

```python
import serial
ser = serial.Serial('/dev/ttyUSB0', 115200)
ser.write(b'\x02\x04\x00\x00')  # Example request
print(ser.read_all())
````

---

## 6. Integration with ROS 2

If using the [vesc_ros2](https://github.com/f1tenth/vesc) package:

```bash
sudo apt install ros-humble-vesc-msgs ros-humble-vesc-driver
```

Example launch:

```bash
ros2 launch vesc_driver vesc_driver_node.launch.py port:=/dev/ttyUSB0
```

Topics:

* `/commands/motor/current`
* `/commands/motor/speed`
* `/sensors/core`
* `/sensors/imu`

---

## 7. Troubleshooting

| Symptom            | Possible Cause     | Fix                         |
| ------------------ | ------------------ | --------------------------- |
| Motor not spinning | Wrong app mode     | Set to UART or PPM          |
| Jerky motion       | FOC not calibrated | Rerun motor detection       |
| No serial data     | Wrong baud rate    | Match MCU and VESC settings |
| Overvoltage error  | Battery too high   | Adjust cutoff values        |

---

## 8. References

* [Official VESC Project Site](https://vesc-project.com/)
* [VESC UART Protocol](https://github.com/vedderb/bldc/blob/master/comm/commands.c)
* [ROS 2 VESC Driver](https://github.com/f1tenth/vesc)

---

*Last updated: October 2025*

```

---

Would you like me to tailor this for your **1/8 RC truck** setup (with Flipsky VESC + Teensy serial + Jetson Orin + ROS 2 integration)?  
If yes, I can fill in all the model-specific values, exact wiring diagram, and example serial command packet structure.
```
