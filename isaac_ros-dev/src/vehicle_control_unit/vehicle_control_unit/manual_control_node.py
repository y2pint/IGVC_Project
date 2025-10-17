import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
from std_msgs.msg import Bool       # 🔸 NEW


class ManualControlNode(Node):
    def __init__(self):
        super().__init__('manual_control_node')

        # Subscribe to RC input channels
        self.create_subscription(Int32, '/rc/ch1', self.ch1_callback, 10)  # Steering
        self.create_subscription(Int32, '/rc/ch2', self.ch2_callback, 10)  # Throttle
        self.create_subscription(Int32, '/rc/ch3', self.ch3_callback, 10)  # 🔸 NEW: Emergency Stop 스위치

        # Publishers for motor and steering
        self.servo_pub = self.create_publisher(Int32, '/servo_cmd_man', 10)
        self.rpm_pub = self.create_publisher(Int32, '/vesc_rpm_cmd_man', 10)
        self.stop_pub = self.create_publisher(Bool, '/stop_flag', 10)      # 🔸 NEW: stop_flag 퍼블리셔

        self.get_logger().info("🕹️ Manual Control Node started.")

    def ch1_callback(self, msg: Int32):
        pwm = msg.data
        # Map PWM 1000–2000 to 0–180° for steering
        angle = int((pwm - 1000) * (180.0 / 1000.0))
        angle = max(0, min(180, angle))
        self.servo_pub.publish(Int32(data=angle))
        self.get_logger().info(f"CH1 → Steering Angle: {angle}")

    def ch2_callback(self, msg: Int32):
        pwm = msg.data
        # Map PWM 1000–2000 to -2000 to +2000 RPM
        rpm = int((pwm - 1500) * 6)  # Scale factor tuned
        rpm = max(-3000, min(3000, rpm))
        self.rpm_pub.publish(Int32(data=rpm))
        self.get_logger().info(f"CH2 → Throttle RPM: {rpm}")

    def ch3_callback(self, msg: Int32):        # 🔸 NEW
        pwm = msg.data                         # 🔸 NEW
        stop_msg = Bool()                      # 🔸 NEW

        # PWM 값으로 스위치 상태 판단        # 🔸 NEW
        if pwm > 1800:                         # 🔸 NEW
            stop_msg.data = True               # 🔸 NEW
            self.get_logger().warn("🛑 Emergency Stop: Switch UP!")  # 🔸 NEW
        elif pwm < 1200:                       # 🔸 NEW
            stop_msg.data = False              # 🔸 NEW
            self.get_logger().info("▶️ Emergency Stop: Switch DOWN") # 🔸 NEW
        else:                                  # 🔸 NEW
            return                             # 🔸 NEW

        self.stop_pub.publish(stop_msg)        # 🔸 NEW

def main(args=None):
    rclpy.init(args=args)
    node = ManualControlNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
