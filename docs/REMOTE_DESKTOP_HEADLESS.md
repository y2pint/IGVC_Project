# 🖥️ Headless Remote Desktop on NVIDIA Jetson AGX using Dummy Monitor + NoMachine

This guide enables you to access your **Jetson AGX headlessly** through **NoMachine**, by utilizing a virtual (dummy) display. This allows X11 to start without requiring a physical monitor.

**IMPORTANT**: Remember (or mark on the AGX hardware) the **username** and **password** to switch modes. If the WiFi connection is lost, you can use the USB connection with **192.168.55.1** as the IP address. For SSH access and to change the configuration, use the following command:

```bash
$ ssh <username>@192.168.55.1
```

Note: I’ve had to reset multiple Orin devices so far.


## 🧩 Steps

### 1. Install Dummy Monitor Package

Install the necessary package for the dummy monitor:

```bash
sudo apt update
sudo apt install -y xserver-xorg-video-dummy
```

---

### 2. Back Up the Original X11 Configuration

Create a backup of the original X11 configuration:

```bash
cd /etc/X11
sudo cp xorg.conf xorg.conf.backup
```

---

### 3. Create Dummy Monitor Config

Create a new X11 configuration file for the dummy monitor:

```bash
sudo gedit xorg.conf.dummy
```

Then, paste the following configuration:

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

Save and close the file.

---

### 4. Replace the Original Config with the Dummy Config

Replace the original `xorg.conf` with the newly created dummy configuration:

```bash
sudo cp xorg.conf.dummy xorg.conf
```

---

### 5. Install NoMachine

Download and install **NoMachine** by visiting [this link](https://www.nomachine.com/download).

Select the `.deb` package for **ARM64 Linux** and install it using the following command:

```bash
sudo dpkg -i nomachine_*.deb
```

---

### 6. Reboot and Connect

Reboot the Jetson AGX to apply changes:

```bash
sudo reboot
```

After rebooting, connect to the Jetson AGX via NoMachine using the IP address (`hostname -I`).

---

## ✅ Notes

* This setup works on JetPack 5/6 (Ubuntu 20.04 / 22.04).
* Both **DisplayPort** and **HDMI dummy plugs** are compatible.
* If you later attach a physical monitor, you can restore the original configuration by running:

  ```bash
  sudo cp /etc/X11/xorg.conf.backup /etc/X11/xorg.conf
  sudo reboot
  ```

---

### 🛠️ Troubleshooting

If you encounter issues like a black screen or resolution mismatches, try the following:

1. **Check Xorg Logs**: Review the X11 log files for errors or misconfigurations. You can find the logs in `/var/log/Xorg.0.log`.

   To check the logs, run:

   ```bash
   cat /var/log/Xorg.0.log | grep EE
   ```

2. **Resolution Mismatch**: If the resolution doesn't match your display, verify the monitor’s supported resolutions or adjust the dummy monitor config in `xorg.conf.dummy`.

