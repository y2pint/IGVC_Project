import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
from sensor_msgs.msg import BatteryState
from pyvesc import VESC
import time

class VESCBridgeNode(Node):
    def __init__(self):
        super().__init__('vesc_bridge_node')

        # Parameters
        self.declare_parameter('use_kickstart', True)
        self.declare_parameter('verbose', False)
        self.declare_parameter('reverse', True)

        self.use_kickstart = self.get_parameter('use_kickstart').value
        self.verbose = self.get_parameter('verbose').value
        self.reverse = self.get_parameter('reverse').value

        # Internal state
        self.latest_rpm_cmd = 0
        self.last_rpm_cmd = 0
        self.kickstart_active = False
        self.kickstart_start_time = None
        self.kickstart_duration = 0.2  # seconds
        self.kickstart_duty = 0.05      # 0% duty  # After adding hall sensor, we do not need this kick start!

        # ROS interfaces
        self.create_subscription(Int32, 'vesc_rpm_cmd', self.update_rpm_command, 10)
        self.battery_pub = self.create_publisher(BatteryState, 'vesc_battery', 10)

        # Initialize VESC
        self.vesc = self.initialize_vesc('/host_dev/vesc', max_retries=3)

        # Timers
        self.create_timer(0.05, self.control_loop)         # 50 Hz
        self.create_timer(1.0, self.publish_battery_state) # 1 Hz

        self.log('info', f"🛠️ Kickstart mode: {'enabled' if self.use_kickstart else 'disabled'}")
        self.log('info', f"📝 Verbose mode: {'enabled' if self.verbose else 'disabled'}")

    def log(self, level, msg):
        if level == 'error':
            self.get_logger().error(msg)
        elif level == 'info':
            self.get_logger().info(msg)
        elif self.verbose:
            {
                'info': self.get_logger().info,
                'warn': self.get_logger().warn,
                'debug': self.get_logger().debug
            }.get(level, self.get_logger().info)(msg)

    def initialize_vesc(self, port, max_retries=3):
        for attempt in range(1, max_retries + 1):
            try:
                self.log('info', f"⏳ Connecting to VESC (Attempt {attempt})...")
                motor = VESC(serial_port=port)
                self.log('info', "✅ VESC connected.")
                return motor
            except (ValueError, TypeError) as e:
                self.log('warn', f"⚠️ VESC init failed: {e}")
                time.sleep(1)
            except Exception as e:
                self.log('error', f"❌ Unexpected VESC error: {e}")
                break
        self.log('error', "🚨 VESC connection failed after retries.")
        return None

    def update_rpm_command(self, msg: Int32):
        if self.reverse:
            self.latest_rpm_cmd = -msg.data
        else:
            self.latest_rpm_cmd = msg.data

    def control_loop(self):
        if not self.vesc:
            return

        try:
            if self.use_kickstart:
                if self.last_rpm_cmd == 0 and abs(self.latest_rpm_cmd) > 100 and not self.kickstart_active:
                    self.kickstart_active = True
                    self.kickstart_start_time = time.time()
                    duty = self.kickstart_duty if self.latest_rpm_cmd > 0 else -self.kickstart_duty
                    self.vesc.set_duty_cycle(duty)
                    self.log('info', f"⚡ Kickstarting with duty: {duty:.2f}")
                elif self.kickstart_active:
                    elapsed = time.time() - self.kickstart_start_time
                    if elapsed >= self.kickstart_duration:
                        self.kickstart_active = False
                        self.vesc.set_rpm(self.latest_rpm_cmd)
                        self.log('info', f"🔁 Switching to RPM: {self.latest_rpm_cmd}")
                    else:
                        duty = self.kickstart_duty if self.latest_rpm_cmd > 0 else -self.kickstart_duty
                        self.vesc.set_duty_cycle(duty)
                else:
                    self.vesc.set_rpm(self.latest_rpm_cmd)
            else:
                self.vesc.set_rpm(self.latest_rpm_cmd)
        except Exception as e:
            self.log('warn', f"⚠️ VESC command error: {e}")

        self.last_rpm_cmd = self.latest_rpm_cmd

    def publish_battery_state(self):
        if not self.vesc:
            return
        try:
            measurements = self.vesc.get_measurements()
            voltage = measurements.v_in

            msg = BatteryState()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.voltage = voltage
            msg.current = float('nan')
            msg.charge = float('nan')
            msg.capacity = float('nan')
            msg.design_capacity = float('nan')
            msg.percentage = float('nan')
            msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
            msg.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_GOOD
            msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LION
            msg.present = True

            self.battery_pub.publish(msg)
        except Exception as e:
            self.log('warn', f"⚠️ Failed to read VESC voltage: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = VESCBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        if node.vesc:
            try:
                node.vesc.set_rpm(0)
                node.vesc.serial_port.close()
            except:
                pass
        node.destroy_node()
        rclpy.shutdown()
