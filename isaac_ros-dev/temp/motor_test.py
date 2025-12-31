from pyvesc import VESC
import time
import sys

VESC_PORT = '/host_dev/vesc_right'
TARGET_RPM = 1000

MAX_INIT_RETRIES = 5
INIT_DELAY_SEC = 0.3
RETRY_BACKOFF_SEC = 0.5

vesc = None

# -------------------------------------------------------------------
# Robust VESC initialization
# -------------------------------------------------------------------
for attempt in range(1, MAX_INIT_RETRIES + 1):
    try:
        time.sleep(INIT_DELAY_SEC)

        vesc = VESC(serial_port=VESC_PORT)

        # Flush any partial frames
        try:
            vesc.serial_port.reset_input_buffer()
            vesc.serial_port.reset_output_buffer()
        except Exception:
            pass

        print(f"VESC connected on attempt {attempt}")
        break

    except Exception as e:
        print(f"[WARN] VESC init failed (attempt {attempt}/{MAX_INIT_RETRIES}): {e}")
        time.sleep(RETRY_BACKOFF_SEC)

if vesc is None:
    print("[ERROR] Failed to initialize VESC")
    sys.exit(1)

# -------------------------------------------------------------------
# Motor test
# -------------------------------------------------------------------
try:
    print(f"Setting RPM = {TARGET_RPM}")
    vesc.set_rpm(TARGET_RPM)
    time.sleep(5)

finally:
    # --- clean shutdown ---
    try:
        print("Stopping motor")
        vesc.set_rpm(0)
        time.sleep(0.2)
    except Exception:
        pass

    try:
        # Stop heartbeat thread cleanly
        if hasattr(vesc, "_stop_heartbeat"):
            vesc._stop_heartbeat.set()
            time.sleep(0.1)
    except Exception:
        pass

    try:
        vesc.serial_port.close()
    except Exception:
        pass

print("Right VESC OK")
