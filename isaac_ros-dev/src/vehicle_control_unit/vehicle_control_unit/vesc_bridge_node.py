import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
from sensor_msgs.msg import BatteryState
from pyvesc import VESC
import time
import threading
import serial
from serial.serialutil import SerialException
import errno

class VESCBridgeNode(Node):
    def __init__(self):
        super().__init__('vesc_bridge_node')

        # ------------------------------------------------------------
        # Parameters
        # ------------------------------------------------------------
        self.declare_parameter('vesc_port', '/host_dev/vesc')
        self.declare_parameter('cmd_timeout', 0.5)  # Increased timeout
        self.declare_parameter('use_kickstart', True)
        self.declare_parameter('verbose', False)
        self.declare_parameter('reverse', True)

        self.vesc_port = self.get_parameter('vesc_port').value
        self.cmd_timeout = self.get_parameter('cmd_timeout').value
        self.use_kickstart = self.get_parameter('use_kickstart').value
        self.verbose = self.get_parameter('verbose').value
        self.reverse = self.get_parameter('reverse').value

        # ------------------------------------------------------------
        # Internal state
        # ------------------------------------------------------------
        self.latest_rpm_cmd = 0
        self.last_rpm_cmd = 0
        self.last_cmd_time = self.get_clock().now()

        self.kickstart_active = False
        self.kickstart_start_time = None
        self.kickstart_duration = 0.2   # seconds
        self.kickstart_duty = 0.05

        # ------------------------------------------------------------
        # ROS interfaces
        # ------------------------------------------------------------
        self.create_subscription(
            Int32,
            'vesc_rpm_cmd',
            self.update_rpm_command,
            10
        )

        self.battery_pub = self.create_publisher(
            BatteryState,
            'vesc_battery',
            10
        )

        # ------------------------------------------------------------
        # Initialize VESC
        # ------------------------------------------------------------
        self.vesc = self.initialize_vesc(self.vesc_port)

        # ------------------------------------------------------------
        # Timers
        # ------------------------------------------------------------
        self.create_timer(0.1, self.control_loop)  # 50 Hz

        self.log('info', f"VESC port: {self.vesc_port}")
        self.log('info', f"Kickstart: {'enabled' if self.use_kickstart else 'disabled'}")
        self.log('info', f"Reverse: {self.reverse}")

    # ------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------
    def log(self, level, msg):
        if level == 'error':
            self.get_logger().error(msg)
        elif level == 'info':
            self.get_logger().info(msg)
        elif self.verbose:
            {
                'warn': self.get_logger().warn,
                'debug': self.get_logger().debug
            }.get(level, self.get_logger().info)(msg)

    # ------------------------------------------------------------
    # VESC initialization (robust)
    # ------------------------------------------------------------
    def initialize_vesc(self, port, max_retries=5):
        for attempt in range(1, max_retries + 1):
            try:
                self.log('info', f"Connecting to VESC ({port}), attempt {attempt}")
                time.sleep(0.3)  # USB CDC settle

                motor = VESC(serial_port=port)

                # Flush any partial frames
                try:
                    motor.serial_port.reset_input_buffer()
                    motor.serial_port.reset_output_buffer()
                    time.sleep(0.5)  # Give some time for the buffers to clear
                except SerialException as e:
                    self.log('warn', f"Error while resetting serial buffers: {e}")

                # Disable heartbeat
                motor._stop_heartbeat = threading.Event()  # Stop the heartbeat thread

                self.log('info', "VESC connected successfully")
                return motor

            except (OSError, SerialException) as e:
                self.log('warn', f"VESC init failed: {e}")
                time.sleep(0.5)  # wait before retrying
            except Exception as e:
                self.log('error', f"Unexpected error during VESC init: {e}")
                time.sleep(0.5)

        self.log('error', "Failed to initialize VESC after retries")
        return None

    # ------------------------------------------------------------
    # RPM command callback
    # ------------------------------------------------------------
    def update_rpm_command(self, msg: Int32):
        self.latest_rpm_cmd = -msg.data if self.reverse else msg.data
        self.last_cmd_time = self.get_clock().now()

    # ------------------------------------------------------------
    # Control loop (50 Hz)
    # ------------------------------------------------------------
    def control_loop(self):
        if not self.vesc:
            return

        # ---- watchdog first ----
        dt = (self.get_clock().now() - self.last_cmd_time).nanoseconds * 1e-9
        if dt > self.cmd_timeout:
            try:
                self.vesc.set_rpm(0)
            except (SerialException, OSError) as e:
                self.log('warn', f"VESC communication error during watchdog: {e}")
                return  # Don't continue the loop if communication fails
            return

        try:
            if self.use_kickstart:
                if (
                    self.last_rpm_cmd == 0
                    and abs(self.latest_rpm_cmd) > 100
                    and not self.kickstart_active
                ):
                    self.kickstart_active = True
                    self.kickstart_start_time = time.time()
                    duty = self.kickstart_duty if self.latest_rpm_cmd > 0 else -self.kickstart_duty
                    self.vesc.set_duty_cycle(duty)

                elif self.kickstart_active:
                    elapsed = time.time() - self.kickstart_start_time
                    if elapsed >= self.kickstart_duration:
                        self.kickstart_active = False
                        self.vesc.set_rpm(self.latest_rpm_cmd)
                    else:
                        duty = self.kickstart_duty if self.latest_rpm_cmd > 0 else -self.kickstart_duty
                        self.vesc.set_duty_cycle(duty)

                else:
                    self.vesc.set_rpm(self.latest_rpm_cmd)
            else:
                self.vesc.set_rpm(self.latest_rpm_cmd)

        except (SerialException, OSError) as e:
            self.log('warn', f"VESC command error: {e}")

        self.last_rpm_cmd = self.latest_rpm_cmd

    # ------------------------------------------------------------
    # Battery telemetry (1 Hz)
    # ------------------------------------------------------------
    def publish_battery_state(self):
        if not self.vesc:
            return

        try:
            meas = self.vesc.get_measurements()
            msg = BatteryState()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.voltage = meas.v_in
            msg.current = float('nan')
            msg.percentage = float('nan')
            msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
            msg.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_GOOD
            msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LION
            msg.present = True
            self.battery_pub.publish(msg)

        except Exception as e:
            self.log('warn', f"Battery read failed: {e}")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main(args=None):
    rclpy.init(args=args)
    node = VESCBridgeNode()

    try:
        rclpy.spin(node)

    finally:
        if node.vesc:
            try:
                node.vesc.set_rpm(0)
                time.sleep(0.2)

                # Stop PyVESC heartbeat thread cleanly
                if hasattr(node.vesc, "_stop_heartbeat"):
                    node.vesc._stop_heartbeat.set()  # Ensure the thread is stopped cleanly
                    time.sleep(0.1)

                node.vesc.serial_port.close()
            except (SerialException, OSError) as e:
                node.log('warn', f"Error closing serial port: {e}")
            except Exception as e:
                node.log('warn', f"Unexpected error during shutdown: {e}")

        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
