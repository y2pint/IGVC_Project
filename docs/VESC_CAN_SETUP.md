# VESC Setup Guide (CAN-Based)

This document explains how to configure and connect **VESC motor controllers using CAN** for a mobile robot / autonomous RC truck platform.  
**USB is used only for configuration and debugging. All runtime command and telemetry are handled via CAN.**

This design choice was made to ensure **robustness, scalability, and electrical reliability** on a mobile platform.

---

## 1. Hardware Overview

- **Motor:** 14-pole BLDC motor (with reduction gear)
- **ESC:** Flipsky VESC (e.g., 6.7 / 75V series)
- **Drive:** Differential drive (two independent VESCs)
- **Host Computer:**  
  - Jetson **AGX Orin**  
  - Jetson **Orin Nano**
- **Battery:** e.g., 12S LiPo (verify limits)
- **Primary Communication Interface:** **CAN (Controller Area Network)**
- **Secondary / Debug Interface:** USB or BT (VESC Tool only)

---

## 2. Why CAN Instead of USB or UART

**CAN was chosen as the primary interface for motor command and monitoring** for the following reasons:

- USB showed intermittent disconnects and I/O errors on Jetson
- CAN provides deterministic, real-time communication
- Native multi-ESC support on a shared bus
- Higher electrical robustness (twisted pair, termination)
- Clean integration with ROS 2 via SocketCAN
- Easier scaling (future motors, sensors, ESC telemetry)

**Design rule:**
> USB is never required for runtime operation.

---

## 3. Software Requirements

### On Jetson (AGX Orin / Orin Nano)

- Ubuntu 22.04 (JetPack 6.x)
- ROS 2 Humble
- SocketCAN (built into Linux kernel)
- Custom ROS 2 CAN → VESC node (or equivalent)

### For Configuration Only

- **VESC Tool**
- Temporary USB cable to each VESC
- Bluetooth

---

## 4. Initial VESC Configuration (via USB)

> Perform this **once per VESC** before switching to CAN-only operation.

### Step 1: Connect with VESC Tool
1. Connect VESC to PC
2. Open **VESC Tool**
3. Update firmware if required

### Step 2: Motor Detection
- `Motor Settings → FOC → Motor Detection`
- Verify smooth rotation
- Save configuration

### Step 3: Enable CAN and Set ID
- `App Settings → General`
  - **Enable CAN**
  - Assign **unique CAN ID** to each VESC  
    - Example:  
      - Left motor: CAN ID `8`  
      - Right motor: CAN ID `9`
- Save configuration

### Step 4: Disable USB Dependency
- App selection does **not** matter for CAN operation
- USB is no longer needed after this step
- BT is convient for PID tuning with the vehicle performance.

---

## 5. CAN Wiring (Critical)

### CAN Bus Wiring (All VESCs in Parallel)

| Signal | VESC Pin | Notes |
|------|---------|------|
| CAN_H | CANH | Twisted pair |
| CAN_L | CANL | Twisted pair |
| GND | GND | Common ground required |

### Termination
- **120 Ω resistor** at **each end of the CAN bus**
- Most VESCs do **not** include onboard termination
- Add external terminators as needed

⚠️ Incorrect termination is the most common CAN issue.

---

## 6. CAN Setup on Jetson Orin (AGX & Nano)

### 6.1 Hardware Interface Options

- Requires:
  - CAN transceiver (e.g., SN65HVD230)
  - Correct pin muxing
- More setup effort, but lower latency

---

### 6.2 Bring Up CAN Interface (SocketCAN)

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
````

Verify:

```bash
ip -details link show can0
```

---

### 6.3 Test CAN Traffic

Install tools:

```bash
sudo apt install can-utils
```

Monitor traffic:

```bash
candump can0
```

If VESCs are powered and configured correctly, you should see periodic status frames.

---

## 7. VESC CAN Protocol (Runtime)

VESC supports standard CAN packet IDs, including:

| Command                   | Packet ID                  |
| ------------------------- | -------------------------- |
| Set Duty                  | `CAN_PACKET_SET_DUTY` (0)  |
| Set RPM                   | `CAN_PACKET_SET_RPM` (3)   |
| Status                    | `CAN_PACKET_STATUS` (9)    |
| Status 4 (current, temps) | `CAN_PACKET_STATUS_4` (16) |

Each message is addressed using:

```
CAN_ID = (VESC_CAN_ID | (PACKET_ID << 8))
```

This allows **broadcast + individual addressing** on the same bus.

---

## 8. ROS 2 Integration (CAN-Based)

Typical architecture:

```
Nav2 / Teleop
     ↓ cmd_vel
ROS 2 CAN Node
     ↓
SocketCAN (can0)
     ↓
VESCs (CAN)
```

### Published Telemetry (Examples)

* Motor RPM
* Input (DC) current
* Motor current
* MOSFET temperature
* Fault flags

### Subscribed Commands

* Target RPM
* Duty cycle
* Current control

---

## 9. Troubleshooting

| Symptom                 | Likely Cause            | Fix               |
| ----------------------- | ----------------------- | ----------------- |
| No CAN messages         | CAN not enabled in VESC | Enable + save     |
| No traffic in `candump` | Wrong bitrate           | Use 500k          |
| Intermittent data       | Missing termination     | Add 120 Ω         |
| Only one motor responds | Duplicate CAN IDs       | Assign unique IDs |
| USB disconnects         | Expected                | USB not used      |

---

## 10. References

* VESC Project: [https://vesc-project.com/](https://vesc-project.com/)
* VESC CAN Protocol:
  [https://github.com/vedderb/bldc/blob/master/comm/commands.c](https://github.com/vedderb/bldc/blob/master/comm/commands.c)
* Linux SocketCAN:
  [https://www.kernel.org/doc/Documentation/networking/can.txt](https://www.kernel.org/doc/Documentation/networking/can.txt)

---

**Design decision summary:**

> CAN is the only supported runtime interface for this project.
> USB is configuration-only.

*Last updated: January 2026*