#!/usr/bin/env python3
import time
import serial
import rclpy
from rclpy.node import Node

from action_msgs.msg import GoalStatusArray

# GoalStatus.status values (action_msgs/GoalStatus)
STATUS_UNKNOWN   = 0
STATUS_ACCEPTED  = 1
STATUS_EXECUTING = 2
STATUS_CANCELING = 3
STATUS_SUCCEEDED = 4
STATUS_CANCELED  = 5
STATUS_ABORTED   = 6


class Nav2LedIndicator(Node):
    """
    Sends "MODE AUTO\n" to Arduino while Nav2 NavigateToPose is active,
    otherwise sends "MODE MANUAL\n".
    """

    def __init__(self):
        super().__init__('nav2_led_indicator')

        # ----------------------------
        # Parameters
        # ----------------------------
        self.declare_parameter('port', '/dev/arduino_led')  # stable udev symlink
        self.declare_parameter('baud', 115200)
        self.declare_parameter('startup_delay_sec', 2.0)    # Arduino reset after serial open
        self.declare_parameter('cmd_auto', 'MODE AUTO\n')
        self.declare_parameter('cmd_manual', 'MODE MANUAL\n')
        self.declare_parameter('resend_period_sec', 2.0)    # periodically re-send current mode
        self.declare_parameter('status_topic', '/navigate_to_pose/_action/status')

        self.port = self.get_parameter('port').get_parameter_value().string_value
        self.baud = int(self.get_parameter('baud').value)
        self.startup_delay = float(self.get_parameter('startup_delay_sec').value)
        self.cmd_auto = self.get_parameter('cmd_auto').get_parameter_value().string_value
        self.cmd_manual = self.get_parameter('cmd_manual').get_parameter_value().string_value
        self.resend_period = float(self.get_parameter('resend_period_sec').value)
        self.status_topic = self.get_parameter('status_topic').get_parameter_value().string_value

        # ----------------------------
        # Serial
        # ----------------------------
        self.ser = None
        self._open_serial()

        # ----------------------------
        # Nav2 status subscription
        # ----------------------------
        self.navigating = False
        self.last_mode_sent = None
        self.last_send_time = 0.0

        self.create_subscription(
            GoalStatusArray,
            self.status_topic,
            self._status_cb,
            10
        )

        # Periodic resend (helps if Arduino reboots / cable hiccup)
        self.create_timer(0.2, self._tick)

        self.get_logger().info(
            f"Watching Nav2 status: {self.status_topic} | Serial: {self.port}@{self.baud}"
        )

    def _open_serial(self):
        try:
            self.get_logger().info(f"Opening serial {self.port} @ {self.baud}...")
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=0.2,
            )
            # Arduino resets on serial open
            time.sleep(self.startup_delay)
            self._drain_startup()
        except Exception as e:
            self.ser = None
            self.get_logger().error(f"Failed to open serial: {e}")

    def _drain_startup(self, drain_sec: float = 1.0):
        if not self.ser:
            return
        t0 = time.time()
        while time.time() - t0 < drain_sec:
            try:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if line:
                        self.get_logger().info(f"Arduino: {line}")
                else:
                    time.sleep(0.02)
            except Exception:
                break

    def _status_cb(self, msg: GoalStatusArray):
        # Consider “navigating” if ANY goal is accepted/executing/canceling.
        # (canceling still means Nav2 is actively doing something)
        active = False
        for st in msg.status_list:
            if st.status in (STATUS_ACCEPTED, STATUS_EXECUTING, STATUS_CANCELING):
                active = True
                break

        if active != self.navigating:
            self.navigating = active
            mode = 'AUTO' if self.navigating else 'MANUAL'
            self.get_logger().info(f"Nav2 navigating={self.navigating} -> MODE {mode}")
            self._send_mode(force=True)

    def _send_mode(self, force: bool = False):
        desired = 'AUTO' if self.navigating else 'MANUAL'
        cmd = self.cmd_auto if self.navigating else self.cmd_manual

        now = time.time()
        if (not force) and (self.last_mode_sent == desired) and ((now - self.last_send_time) < self.resend_period):
            return

        if not self.ser:
            # Try to reopen periodically
            self._open_serial()
            if not self.ser:
                return

        try:
            self.ser.write(cmd.encode('utf-8'))
            self.last_mode_sent = desired
            self.last_send_time = now
        except Exception as e:
            self.get_logger().error(f"Serial write failed: {e}")
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def _tick(self):
        # Keep re-sending the current state every resend_period_sec
        self._send_mode(force=False)

    def destroy_node(self):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        super().destroy_node()


def main():
    rclpy.init()
    node = Nav2LedIndicator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
