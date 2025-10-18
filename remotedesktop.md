
---

# 🖥️ Headless Remote Desktop on NVIDIA Jetson AGX using Dummy Monitor + NoMachine

This setup allows you to access your **Jetson AGX headlessly** through **NoMachine**, using a virtual (dummy) display so X11 can start without a physical monitor.

---

## 🧩 Steps

### 1. Install Dummy Monitor Package

```bash
sudo apt update
sudo apt install -y xserver-xorg-video-dummy
```

---

### 2. Back Up the Original X11 Configuration

```bash
cd /etc/X11
sudo cp xorg.conf xorg.conf.backup
```

---

### 3. Create Dummy Monitor Config

Create a new file:

```bash
sudo gedit xorg.conf.dummy
```

Paste the following:

```bash
Section "Monitor"
    Identifier "DummyMonitor"
    HorizSync 28.0-80.0
    VertRefresh 48.0-75.0
EndSection

Section "Device"
    Identifier "DummyDevice"
    Driver "dummy"
    VideoRam 256000
EndSection

Section "Screen"
    Identifier "DummyScreen"
    Device "DummyDevice"
    Monitor "DummyMonitor"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080"
    EndSubSection
EndSection
```

Save and close.

---

### 4. Replace the Original Config

```bash
sudo cp xorg.conf.dummy xorg.conf
```

---

### 5. Install NoMachine

Visit [https://www.nomachine.com/download](https://www.nomachine.com/download)
Download the `.deb` package for **ARM64 Linux**, then install:

```bash
sudo dpkg -i nomachine_*.deb
```

---

### 6. Reboot and Connect

```bash
sudo reboot
```

After reboot, connect via NoMachine from your laptop using the AGX’s IP (`hostname -I`).

---

## ✅ Notes

* Works on JetPack 5/6 (Ubuntu 20.04 / 22.04).
* Both **DisplayPort** and **HDMI dummy plugs** work.
* If you later attach a real monitor, you can restore:

  ```bash
  sudo cp /etc/X11/xorg.conf.backup /etc/X11/xorg.conf
  sudo reboot
  ```

---

Would you like me to add a short **troubleshooting section** (e.g., black screen, Xorg log check, or resolution mismatch)? It fits nicely at the end of your README.
