Here’s an **expanded, team-ready Markdown** that cleanly adds **how CH341 was installed**, while keeping the narrative crisp and actionable. This is suitable for a lab wiki, GitHub README, or internal IGVC handoff.

---

# CH341 USB-Serial (Arduino) on Jetson AGX Orin — Installation & Lessons Learned

## TL;DR

If a **CH341 / CH340 USB-serial device** shows **permission errors, `EIO`, or disappears**, the root cause is often **`brltty` hijacking the device**, sometimes combined with **USB hub instability**.
This is **not a Docker issue** and **not a udev permission issue**.

---

## Hardware / OS Context

* Platform: **Jetson AGX Orin**
* OS: Ubuntu (JetPack)
* USB-Serial: **CH341 / CH340** (Arduino Nano–type boards)
* Pixhawk connected via USB (CDC ACM)
* Docker used later (not root cause)

---

## Step 1 — CH341 Driver Installation

### Important note (Jetson / modern kernels)

Recent JetPack kernels **already include a CH341 driver** (`usb_ch341` or `ch341`).
However, behavior can be inconsistent depending on kernel version, so we explicitly verified and installed support.

---

### 1.1 Check whether CH341 is already supported

Plug in the CH341 device and run:

```bash
lsusb | grep -i 1a86
```

Expected:

```
ID 1a86:7523 QinHeng Electronics CH340 serial converter
```

Then check kernel binding:

```bash
dmesg | grep -i ch34
```

If you see something like:

```
usb_ch341 ... ttyCH341USB0: ch341 USB device
```

then the **driver is already present**.

---

### 1.2 (If needed) Install CH341 driver manually

If no driver binds automatically (older JetPack or custom kernel), install it manually:

```bash
sudo apt update
sudo apt install -y dkms git build-essential
git clone https://github.com/juliagoda/CH341SER.git
cd CH341SER
make
sudo make install
sudo modprobe usb_ch341
```

Verify module load:

```bash
lsmod | grep ch341
```

⚠️ **Do not install multiple CH341 drivers at once.**
If both in-tree and out-of-tree drivers are present, conflicts and instability can occur.

---

### 1.3 Verify driver binding

```bash
udevadm info -n /dev/ttyCH341USB0 | egrep 'ID_VENDOR_ID|ID_MODEL_ID|ID_USB_DRIVER'
```

Expected:

```
ID_VENDOR_ID=1a86
ID_MODEL_ID=7523
ID_USB_DRIVER=usb_ch341
```

---

## Step 2 — Symptoms Observed

* `/dev/ttyCH341USB0` appears and disappears
* `SerialException: [Errno 5] Input/output error`
* `SerialException: [Errno 2] No such file or directory`
* Works intermittently, then fails again
* Docker reports permission errors even when host permissions look correct

---

## Step 3 — Root Causes (Confirmed via `dmesg`)

### 3.1 `brltty` hijacking the CH341

Kernel log repeatedly showed:

```
usbfs: interface 0 claimed by usb_ch341 while 'brltty' sets config #1
```

Explanation:

* `brltty` probes USB-serial devices (many Braille displays use serial)
* CH341 is mistakenly claimed
* Causes:

  * `EIO` on open
  * disconnect / re-enumeration
  * disappearing tty nodes

---

### 3.2 USB hub instability

Also observed:

```
disabled by hub (EMI?), re-enabling...
USB disconnect, device number …
```

Cause:

* CH341 connected deep behind a USB hub chain
* Marginal power / EMI causes resets

---

## Step 4 — Fixes (Required)

### 4.1 Disable / remove `brltty` (mandatory)

For robotics systems, this is safe and recommended.

```bash
sudo systemctl disable --now brltty brltty-udev
sudo apt-get remove -y brltty
sudo apt-get autoremove -y
```

Replug the CH341 device after this.

---

### 4.2 Stabilize USB topology

Best practice:

* **CH341 + Pixhawk** → USB2 or powered low-speed hub
* **Cameras (ZED, RealSense)** → separate USB3 hub
* Avoid deep hub chains
* Use short, good-quality cables

---

## Step 5 — udev Rule (Pixhawk-style, stable naming)

Create `/etc/udev/rules.d/99-ch341.rules`:

```udev
SUBSYSTEM=="tty", \
ATTRS{idVendor}=="1a86", \
ATTRS{idProduct}=="7523", \
SYMLINK+="arduino_led", \
MODE="0666"
```

Reload rules:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Result:

```
/dev/arduino_led  -> stable Arduino port
```

🚫 **Do not hard-code `/dev/ttyCH341USB0`** in applications.

---

## Step 6 — Host-Side Verification

```bash
lsusb | grep 1a86
ls -l /dev/arduino_led
python3 - <<'PY'
import serial
s = serial.Serial('/dev/arduino_led', 115200, timeout=1)
print("OPEN OK")
s.close()
PY
```

If this works on the host, Docker will work too.

---

## Step 7 — Docker Usage (Minimal & Clean)

```bash
docker run -it --rm \
  --device=/dev/arduino_led \
  <image>
```

No `/dev:/dev`, no `--privileged`, no hacks.

---

## Key Takeaways

* **CH341 driver issues are rarely permissions**
* **`brltty` is a silent serial killer on Ubuntu**
* USB stability matters more than software tweaks
* Always use **udev symlinks or `/dev/serial/by-id`**
* Fix host first → Docker becomes trivial

---

## One-Line Reminder

> If a USB-serial device throws `EIO` or disappears on Ubuntu, **check `brltty` before touching Docker or permissions**.

---

If you want next:

* a **short IGVC bring-up checklist**
* a **USB topology diagram**
* or a **ROS 2 Arduino serial node template**

just say the word.
