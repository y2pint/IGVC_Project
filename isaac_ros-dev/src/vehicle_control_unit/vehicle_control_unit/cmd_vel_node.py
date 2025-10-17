#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32, Bool
from sensor_msgs.msg import BatteryState
import math

# === 차량 파라미터 ===
WHEELBASE = 0.38
STEERING_LEFT = 123
STEERING_RIGHT = 55
STEERING_CENTER = 95
STEERING_K = 0.75
K = 0.001109
SCALE = 0.275

class CmdVelToMotorNode(Node):
    def __init__(self):
        super().__init__('cmd_vel_to_motor')

        # Publisher
        self.rpm_pub = self.create_publisher(Int32, '/vesc_rpm_cmd', 10)
        self.servo_pub = self.create_publisher(Int32, '/servo_cmd', 10)

        # Subscribers
        self.create_subscription(Twist, '/cmd_vel', self.cmd_vel_listener, 10)
        self.create_subscription(Bool, '/stop_flag', self.stop_flag_callback, 10)
        self.create_subscription(BatteryState, '/vesc_battery', self.battery_callback, 10)
        self.create_subscription(Int32, '/vesc_rpm_cmd_man', self.man_rpm_callback, 10)
        self.create_subscription(Int32, '/servo_cmd_man', self.man_servo_callback, 10)

        # States
        self.stop_flag = False
        self.latest_cmd_vel = Twist()
        self.latest_voltage = None

        self.prev_v = 0.0
        self.prev_omega = 0.0
        self.prev_pwm = STEERING_CENTER

        # Manual Cmd States:
        self.man_rpm = 0
        self.man_servo = 90

        # Parameters
        self.max_accel = 6
        self.max_angular_accel = 3
        self.max_pwm_rate = 300.0
        self.dt = 0.001 # 주기 = 20Hz
        self.min_erpm = 500

        self.loop_timer = self.create_timer(self.dt, self.control_loop)

        self.get_logger().info("✅ CmdVelToMotorNode with battery voltage monitoring initialized.")

    def man_rpm_callback(self, msg):
        self.man_rpm = msg.data
    
    def man_servo_callback(self, msg):
        self.man_servo = msg.data

    def cmd_vel_listener(self, msg):
        self.latest_cmd_vel = msg

    def battery_callback(self, msg: BatteryState):
        self.latest_voltage = msg.voltage
        self.get_logger().info(f"🔋 VESC Battery Voltage: {self.latest_voltage:.2f} V")

    def control_loop(self):
        if self.stop_flag:
            self.get_logger().warn("🛑 STOP due to stop_flag → Sending 0 commands")
            self.rpm_pub.publish(Int32(data=self.man_rpm))
            self.servo_pub.publish(Int32(data=self.man_servo))
            return

        # === 속도 및 조향 계산 ===
        target_v = self.latest_cmd_vel.linear.x
        target_omega = self.latest_cmd_vel.angular.z

        delta_v = target_v - self.prev_v
        max_delta_v = self.max_accel * self.dt
        if abs(delta_v) > max_delta_v:
            delta_v = math.copysign(max_delta_v, delta_v)
        v = self.prev_v + delta_v
        self.prev_v = v

        delta_omega = target_omega - self.prev_omega
        max_delta_omega = self.max_angular_accel * self.dt
        if abs(delta_omega) > max_delta_omega:
            delta_omega = math.copysign(max_delta_omega, delta_omega)
        omega = self.prev_omega + delta_omega
        self.prev_omega = omega

        # === 선속도 → eRPM 변환 ===
        if v == 0.0:
            erpm = 0
        else:
            erpm = int(v / (K * SCALE))
            # Clamp to minimum absolute value if not zero
            if abs(erpm) < 500:
                erpm = int(math.copysign(500, erpm))

        erpm = max(min(erpm, 10000), -10000)


        # === 조향각 → PWM 변환 ===
        if omega == 0 or v == 0:
            steering_deg = 0.0
        else:
            turning_radius = v / omega
            steering_angle_rad = math.atan(WHEELBASE / turning_radius)
            steering_deg = math.degrees(steering_angle_rad) / STEERING_K

        target_pwm = self.angle_to_pwm(steering_deg)

        # === PWM 변화 제한 없이 즉시 반영 === 🔸 NEW
        steering_pwm = target_pwm
        self.prev_pwm = steering_pwm

        # === 퍼블리시 ===
        self.rpm_pub.publish(Int32(data=erpm))
        self.servo_pub.publish(Int32(data=steering_pwm))
        self.get_logger().info(f"Published eRPM: {erpm}, PWM: {steering_pwm}")

    

    def angle_to_pwm(self, angle_deg):
        normalized = angle_deg / 30.0
        normalized = max(min(normalized, 1.0), -1.0)
        pwm = round(STEERING_CENTER + normalized * (STEERING_LEFT - STEERING_CENTER))
        return max(min(pwm, STEERING_LEFT), STEERING_RIGHT)

    def stop_flag_callback(self, msg: Bool):
        self.stop_flag = msg.data
        self.get_logger().info(f"🛑 stop_flag updated: {self.stop_flag}")

def main(args=None):
    rclpy.init(args=args)
    node = CmdVelToMotorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
