#!/usr/bin/env python3
import time
import serial
import sys

PORT = "/dev/arduino_led"   # change if needed
BAUD = 115200

def main():
    try:
        print(f"Opening {PORT} @ {BAUD}")
        ser = serial.Serial(PORT, BAUD, timeout=0.1)
    except Exception as e:
        print(f"Failed to open serial: {e}")
        sys.exit(1)

    # Arduino resets on open
    print("Waiting for Arduino reset...")
    time.sleep(2.0)

    mode = False  # False = MANUAL, True = AUTO

    while True:
        try:
            # Toggle mode
            mode = not mode
            cmd = "MODE AUTO\n" if mode else "MODE MANUAL\n"
            print(f"Sending: {cmd.strip()}")
            ser.write(cmd.encode())

            t0 = time.time()

            # Read responses for 3 seconds
            while time.time() - t0 < 3.0:
                if ser.in_waiting:
                    line = ser.readline().decode(errors="ignore").strip()
                    if line:
                        print(f"Arduino: {line}")
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

    ser.close()


if __name__ == "__main__":
    main()
