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

For CAN communication on Jetson devices, you will need the following:

* **CAN transceiver** (e.g., **SN65HVD230**) to interface between the Jetson and the CAN bus.
* **Correct pin muxing** for CAN communication. Jetson devices typically require proper pinmux configuration to route GPIO pins for CAN functionality.
* **More setup effort** may be required for custom hardware, but using CAN provides **lower latency** and more robust communication compared to USB or UART.

### 6.2 GPIO Pin Setup for CAN (via `jetson-gpio-pinmux-lookup`)

For Jetson devices using **custom hardware** or if there is a need to adjust pinmux settings for CAN, NVIDIA provides the **`jetson-gpio-pinmux-lookup`** tool as part of **JetPack**. This tool allows you to inspect and verify GPIO pin configurations, ensuring that the pins you plan to use for CAN are correctly routed to the CAN bus.

#### Steps to Use `jetson-gpio-pinmux-lookup`

1. **Install Jetson.GPIO** (if not already installed):

   ```bash
   sudo apt-get install python3-jetson-gpio
   ```

2. **Look Up Pinmux for CAN Pins**:

   The **`jetson-gpio-pinmux-lookup`** tool helps you verify if the CAN pins are correctly assigned. For example, to check the pinmux settings of **GPIO pin 15**, run:

   ```bash
   sudo jetson-gpio-pinmux-lookup 15
   ```

   This command will return information about the pinmux configuration of pin 15 and indicate whether it's routed to CAN or another function.

3. **Configuring CAN Pinmux (Device Tree Overlay)**:

   If the GPIO pins for CAN (CAN_H and CAN_L) are not correctly routed, you will need to modify the device tree by creating a **device tree overlay** to configure the pins for CAN.

   * **Generate Device Tree Overlay**:
     You can use the **NVIDIA pinmux spreadsheet** or manually edit the **device tree** to enable CAN functionality on your custom Jetson hardware.

     * **Pinmux Spreadsheet**: Use the official NVIDIA pinmux spreadsheet to generate and apply a device tree overlay for CAN.
     * **Device Tree Modification**: If you are comfortable editing device trees, you can manually configure the CAN pins and recompile the device tree.

   * **Apply the Device Tree Overlay**:
     After generating or modifying the overlay, apply it with the following commands:

     ```bash
     sudo dtc -I dts -O dtb -o /boot/dtb/your-overlay.dtb /path/to/overlay.dts
     sudo reboot
     ```

4. **Verify CAN Pinmux**:

   Once the overlay is applied, you can recheck the pinmux configuration using **`jetson-gpio-pinmux-lookup`** or verify CAN communication with **`candump`** after bringing up the CAN interface:

   ```bash
   ip -details link show can0
   ```

#### Important Notes

* **Device Tree Overlays**: Be cautious when modifying device tree overlays to ensure that pins are correctly routed for CAN. Incorrect pinmux can lead to communication issues.
* **CAN Transceiver**: For CAN to work, you need a **CAN transceiver** (e.g., SN65HVD230) to interface between the Jetson GPIO and the CAN bus.
* **`jetson-io.py` Tool**: While **`jetson-io.py`** helps configure various interfaces, it does **not** support CAN pin configuration for all Jetson devices. For custom setups, changes to the device tree via overlays are necessary.

---

### 6.3 Bring Up CAN Interface (SocketCAN)

Once your CAN transceiver and pinmux settings are correct, you can bring up the CAN interface (`can0`) using **SocketCAN**.

```bash
# Bring down the CAN interface before configuration
sudo ip link set can0 down

# Set the bitrate (500 kbps is standard for VESC communication)
sudo ip link set can0 type can bitrate 500000

# Bring up the CAN interface
sudo ip link set can0 up
```

#### Verify CAN Interface

Check that the CAN interface is active:

```bash
ip -details link show can0
```

---

### 6.4 Test CAN Traffic

To test CAN communication and monitor traffic, install **can-utils**:

```bash
sudo apt install can-utils
```

Then, monitor the CAN traffic:

```bash
candump can0
```

If your VESCs are powered and correctly configured, you should see periodic **status frames** sent over the CAN bus.

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