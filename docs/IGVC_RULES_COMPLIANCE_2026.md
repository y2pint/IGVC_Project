# 🏁 IGVC Rules Compliance (IGVC 2026)

This document summarizes how the **Tennessee Tech IGVC Autonomous Ground Vehicle** complies with the **33rd Annual Intelligent Ground Vehicle Competition (IGVC)** rules for **2026**.

It is intended for:
- Internal compliance tracking
- New student onboarding
- On-site technical inspection and judge discussions

> **Authoritative source:**  
> All requirements below are derived from the official **IGVC 2026 Rules (30 June 2025 version)**.  
> In the event of ambiguity, **judge interpretation prevails**.

---

## 📘 Official Rules Reference

- Official rules website: https://www.igvc.org/rules
- Competition dates: **May 29 – June 1, 2026**
- Location: **Oakland University, Rochester, Michigan**

---

## 🧭 Supported Competition Tracks

This vehicle is designed to support:

- **AutoNav Challenge**
- **Self Drive Challenge**
- **Design Challenge (mandatory)**

The architecture supports both **GPS-denied autonomy** and **GPS-assisted navigation**, with Nav2 retained as the sole navigation authority.

---

## 📐 Vehicle Configuration Compliance

### Dimensions (Rule I.2)

| Parameter | Requirement | Status |
|--------|------------|-------|
| Length | 3 ft – 7 ft | ✅ Compliant |
| Width | 2 ft – 4 ft | ✅ Compliant |
| Height | ≤ 6 ft (excluding E-stop antenna) | 🟡 Final verification |
| Payload | 20 lb, 16×8×8 in | 🟡 Installed during final assembly |

---

## 🛑 Emergency Stop (E‑Stop)

### Mechanical E‑Stop (Rule I.2)

**Requirements**
- Push-to-stop
- Red, ≥ 1 inch diameter
- Center rear of vehicle
- Height: **2–4 ft from ground**
- Hardware-based (not software)

**Implementation**
- Latching mechanical E‑Stop
- Cuts motor power at hardware level
- Independent of ROS / onboard computer

**Status**
✅ **Compliant**

### Wireless E‑Stop

**Requirements**
- Minimum effective range: **100 ft**
- Held by judges during performance events
- Hardware-based

**Status**
🟡 **To be verified during qualification**

---

## 🚦 Safety Light Indicator

**Requirements**
- Solid light when vehicle powered
- Flashing light in autonomous mode
- Returns to solid when exiting autonomy

**Implementation**
- Dedicated hardware indicator tied to autonomy state

**Status**
🟡 **Pending final integration test**

---

## ⚡ Speed Governance

**Rules**
- Minimum speed: **1 mph**
- Speed must be **hardware-limited**
- No changes allowed after qualification

**Implementation**
- Hardware speed limit enforced at motor controller level
- Nav2 velocity constraints aligned with hardware limit

**Status**
✅ **Compliant**

---

## 🧠 Autonomy & Computation

**Rules**
- Fully autonomous
- No human control during runs
- All computation onboard
- No base stations
- No mapping or memorization of course layouts

**Implementation**
- Onboard Jetson AGX Orin only
- Real-time perception and planning
- No pre-recorded maps; perception-only navigation
- NVBlox voxel map reset between runs

**Status**
✅ **Compliant**

---

## 📡 Wireless Communication

**Rules**
- Wireless links may not be used for control during autonomous runs

**Implementation**
- Wi‑Fi used only for:
  - Development
  - Monitoring
  - Debugging
- Disabled during competition runs

**Status**
✅ **Compliant**

---

## 👁️ Perception & Obstacle Avoidance

**Rules**
- Must detect and avoid:
  - Barrels, tires, mannequins, potholes
- Lane boundaries must be detected
- No tactile sensors allowed

**Implementation**
- Stereo vision: **ZED 2i + RealSense D435**
- GPU voxel mapping using **NVBlox**
- Lane detection via vision-based pipelines
- No tactile sensors used

**Status**
✅ **Compliant**

---

## 🧭 Qualification Requirements (AutoNav & Self Drive)

The vehicle is designed to satisfy all **qualification tests**, including:

- Lane following
- Obstacle avoidance
- Minimum/maximum speed verification
- Waypoint navigation (AutoNav)
- Stop sign, pedestrian, and obstacle handling (Self Drive)

**Status**
🟡 **To be validated during official qualification**

---

## 📋 Pre‑Inspection Checklist

- [ ] Vehicle dimensions verified
- [ ] Payload securely mounted (20 lb)
- [ ] Mechanical E‑Stop tested
- [ ] Wireless E‑Stop range verified
- [ ] Safety light verified (solid / flashing)
- [ ] Speed limits verified (1–5 mph)
- [ ] Autonomous run demonstrated
- [ ] Wireless control disabled during autonomy

---

## ⚠️ Important Notes

- Judges may **terminate any run** deemed unsafe
- Vehicle must not:
  - Cross solid boundary lines
  - Displace obstacles
  - Drop payload
- Final authority rests with **IGVC judges**

---

## 👥 Maintainer

**Dr. Hyung‑Jin Yoon**  
Assistant Professor, Mechanical Engineering  
Tennessee Technological University
