import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
import serial
import threading

class RCBridgeNode(Node):
    def __init__(self):
        super().__init__('rc_bridge_node')

        self.latest_servo_cmd = 90  # default center angle
        self.arduino_serial = self.initialize_serial('/host_dev/arduino', baud=57600)

        # Subscribe to servo angle command
        self.create_subscription(Int32, 'servo_cmd', self.update_servo_command, 10)

        # Publishers for RC channels from Arduino
        self.publisher_ch1 = self.create_publisher(Int32, 'rc/ch1', 10)
        self.publisher_ch2 = self.create_publisher(Int32, 'rc/ch2', 10)
        self.publisher_ch3 = self.create_publisher(Int32, 'rc/ch3', 10)

        # Periodic sender (50 Hz)
        self.create_timer(0.02, self.send_servo_periodic)

        # Start background thread to read from Arduino
        if self.arduino_serial:
            self.read_thread = threading.Thread(target=self.read_serial)
            self.read_thread.daemon = True
            self.read_thread.start()

    def initialize_serial(self, port, baud):
        try:
            s = serial.Serial(port, baud, timeout=1)
            self.get_logger().info(f"✅ Arduino connected at {port}")
            return s
        except Exception as e:
            self.get_logger().error(f"❌ Arduino connection failed: {e}")
            return None

    def update_servo_command(self, msg: Int32):
        angle = max(0, min(180, msg.data))
        self.latest_servo_cmd = angle

    def send_servo_periodic(self):
        if self.arduino_serial:
            command = f'ANGLE:{self.latest_servo_cmd}\n'
            try:
                self.arduino_serial.write(command.encode())
            except Exception as e:
                self.get_logger().warn(f"⚠️ Failed to send servo command: {e}")

    def read_serial(self):
        while rclpy.ok():
            try:
                line = self.arduino_serial.readline().decode().strip()
                if line.startswith("CH1:"):
                    parts = line.replace("CH1:", "").replace("CH2:", "").replace("CH3:", "").split()
                    ch_values = [int(p) for p in parts if p.isdigit()]
                    if len(ch_values) == 3:
                        self.publisher_ch1.publish(Int32(data=ch_values[0]))
                        self.publisher_ch2.publish(Int32(data=ch_values[1]))
                        self.publisher_ch3.publish(Int32(data=ch_values[2]))
            except Exception as e:
                self.get_logger().warn(f"⚠️ Arduino read error: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = RCBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        if node.arduino_serial:
            try:
                node.arduino_serial.close()
            except:
                pass
        node.destroy_node()
        rclpy.shutdown()
