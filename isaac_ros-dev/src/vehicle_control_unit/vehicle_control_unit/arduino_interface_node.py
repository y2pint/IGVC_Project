#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import serial

class ArduinoNode(Node):
    def __init__(self):
        super().__init__('arduino_interface')
        self.ser = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1)
        self.sub = self.create_subscription(String, 'led_cmd', self.cmd_callback, 10)
        self.pub = self.create_publisher(String, 'arduino_status', 10)
        self.timer = self.create_timer(0.1, self.read_serial)

    def cmd_callback(self, msg):
        cmd = msg.data.strip()
        self.ser.write((cmd + '\n').encode())

    def read_serial(self):
        while self.ser.in_waiting:
            line = self.ser.readline().decode().strip()
            if line:
                self.pub.publish(String(data=line))

def main():
    rclpy.init()
    node = ArduinoNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
