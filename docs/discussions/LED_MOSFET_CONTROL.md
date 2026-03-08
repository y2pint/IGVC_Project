Below is a **repository-ready Markdown document** you can drop directly into your repo (for example: `docs/led_signal_driver.md`). It is written in a **technical documentation style**, not conversational, and includes rationale, wiring, validation, and operational notes.

---

```markdown
# 12V Signal LED Driver Design (Orin AGX Safe)

## Overview

This document describes the design and validation of a **12 V signal LED driver circuit** used in the vehicle system.  
The design goal is to provide a reliable LED status indicator while **protecting Jetson Orin AGX GPIO pins** from direct hardware switching loads.

Key design principles:

- Jetson Orin AGX remains **high-level control only**
- No direct power switching from Orin GPIO
- Use a **logic-level MOSFET low-side switch**
- Allow both **Arduino Nano** and **external PWM generator** to drive the gate safely
- Provide deterministic OFF behavior during system boot

The LED blink frequency requirement is **≤ 10 Hz**, therefore switching speed is not critical.

---

# System Architecture

```

Jetson Orin AGX
(ROS / CAN / High-Level Control)
|
| Serial / CAN
v
Arduino Nano
(5 V logic output)
|
v
MOSFET Gate Network
|
v
P30N06LE N-MOSFET (Low-Side Switch)
|
v
12 V Signal LED

```

For validation and debugging, an external **5 V PWM signal generator** can also drive the MOSFET gate.

---

# Hardware Components

| Component | Description |
|--------|-------------|
| MOSFET | P30N06LE logic-level N-channel MOSFET |
| Gate series resistors | 1 kΩ (one per driver input) |
| Gate pulldown resistor | 39 kΩ |
| LED supply | 12 V |
| Controller | Arduino Nano (5 V logic) |
| Optional driver | External 5 V PWM signal generator |

---

# MOSFET Selection

The **P30N06LE** was selected because:

- Logic-level gate (fully enhanced at ~4–5 V)
- Suitable for direct microcontroller gate drive
- Large current margin for signal LED loads
- Robust TO-220 package

Typical operating conditions in this design:

```

Gate voltage: 5 V
Switching frequency: ≤ 10 Hz
Load: 12 V signal LED

```

---

# MOSFET Pinout

TO-220 package (front view, text facing forward, pins down):

| Pin | Function |
|----|---------|
| Left | Gate (G) |
| Middle | Drain (D) |
| Right | Source (S) |

Important:

- The **metal tab is connected to Drain**.
- Confirm with a multimeter before installation.

---

# Power Switching Configuration

The LED is controlled using a **low-side switch**.

```

+12 V
|
|
LED
|
+---- Drain (MOSFET)
|
MOSFET
|
Source
|
GND

```

Advantages of low-side switching:

- Simplifies gate drive
- Compatible with logic-level MOSFETs
- Keeps control circuitry referenced to system ground

---

# Gate Drive Network (Option 2 – Dual Driver)

To allow both an **Arduino Nano** and a **PWM generator** to control the MOSFET safely, each driver connects to the gate through a **series resistor**.

```

Arduino Pin ── 1kΩ ──┐
├── Gate (MOSFET)
PWM Generator ─ 1kΩ ─┘
|
39kΩ
|
GND

```

### Purpose of each resistor

#### 1 kΩ series resistors

- Prevent direct output-to-output contention
- Limit fault current if drivers disagree
- Protect microcontroller outputs

Worst case contention:

```

5V / (1kΩ + 1kΩ) ≈ 2.5 mA

```

Which is safe for microcontroller outputs.

---

#### 39 kΩ pulldown resistor

Ensures the MOSFET gate defaults to **OFF** when no driver is active.

Why necessary:

- MOSFET gates are **capacitive**
- During boot/reset microcontroller pins are **high-impedance**
- Without pulldown the gate can float and randomly turn ON

Pulldown current:

```

I = 5V / 39kΩ ≈ 0.13 mA

```

Negligible power loss.

---

# Gate Drive Voltage

The MOSFET gate is driven by **5 V logic from the Arduino Nano**.

Important constraints:

- Gate drive **must not exceed ~20 V**
- Driving the gate with **12 V is unnecessary and discouraged**
- Logic-level MOSFETs are designed for 4–5 V gate drive

---

# Grounding Requirements

All system grounds must be common:

- 12 V power supply GND
- Arduino Nano GND
- PWM generator GND
- MOSFET Source

Failure to share ground will prevent proper switching.

---

# System Operation

Typical LED behaviors:

| Mode | Description |
|-----|-------------|
| OFF | Gate = 0 V |
| ON | Gate = 5 V |
| BLINK | 10 Hz PWM |

Because the switching frequency is low, switching losses are negligible.

---

# Validation Procedure

### Step 1 – Power test

With gate pulldown connected and no gate drive:

Expected behavior:

```

LED = OFF

```

---

### Step 2 – Static gate test

Apply 5 V to gate through series resistor.

Expected behavior:

```

LED = ON
MOSFET remains cool

```

---

### Step 3 – Blink test

Drive gate with PWM generator:

```

Frequency: 10 Hz
Duty cycle: 50%

```

Expected behavior:

```

Clean blinking
No flicker
No heating

```

---

# MOSFET Health Check

Quick multimeter checks:

| Measurement | Expected |
|-------------|---------|
| Gate-Source | Very high resistance |
| Gate-Drain | Very high resistance |
| Drain-Source (diode mode) | Conducts one direction only |

If MOSFET switches LED cleanly and remains cool, the device is functional.

---

# Safety Considerations

- Never drive the MOSFET gate directly with **12 V**
- Always include a **gate pulldown resistor**
- Always include **series resistors for multiple drivers**
- Confirm MOSFET pinout before wiring
- Ensure **common ground** across all control electronics

---

# Design Summary

The implemented LED driver architecture provides:

- Electrical protection for **Jetson Orin AGX GPIO**
- Safe dual-driver capability (Arduino + PWM generator)
- Deterministic OFF behavior during boot
- Reliable 12 V signal control at low frequency
- Simple and robust hardware implementation

This design is suitable for vehicle state indicators such as:

- System armed
- Autonomous mode
- Fault condition
- Navigation status
```

---

If you'd like, I can also help you add two things that make repo docs much stronger:

1. **A simple schematic diagram (PNG/SVG)** you can include in the MD.
2. **A ROS2 node interface section** showing how Orin commands the Arduino LED modes.
