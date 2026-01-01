#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Int32
import can
import struct

# ----------------------------
# VESC CAN packet IDs
# ----------------------------
CAN_PACKET_SET_DUTY = 0
CAN_PACKET_SET_RPM  = 3

CAN_PACKET_STATUS   = 9
CAN_PACKET_STATUS_2 = 14
CAN_PACKET_STATUS_3 = 15
CAN_PACKET_STATUS_4 = 16
CAN_PACKET_STATUS_5 = 27


class VescCanNode(Node):

    def __init__(self):
        super().__init__('vesc_can_node')

        # ----------------------------
        # Parameters
        # ----------------------------
        self.declare_parameter('vesc_id', 8)
        self.declare_parameter('vesc_name', 'vesc')
        self.declare_parameter('can_interface', 'can0')
        self.declare_parameter('max_abs_duty', 0.3)

        self.vesc_id = self.get_parameter('vesc_id').value
        self.ns = self.get_parameter('vesc_name').value
        self.can_if = self.get_parameter('can_interface').value
        self.max_abs_duty = self.get_parameter('max_abs_duty').value

        # ----------------------------
        # CAN interface
        # ----------------------------
        self.bus = can.interface.Bus(
            channel=self.can_if,
            bustype='socketcan'
        )

        # ----------------------------
        # Subscribers (TX)
        # ----------------------------
        self.create_subscription(
            Float32, f'{self.ns}/cmd_duty', self.duty_cb, 10
        )

        self.create_subscription(
            Int32, f'{self.ns}/cmd_rpm', self.rpm_cb, 10
        )

        # ----------------------------
        # Publishers (RX state)
        # ----------------------------
        self.pub_erpm   = self.create_publisher(Int32,   f'{self.ns}/state/erpm', 10)
        self.pub_duty   = self.create_publisher(Float32, f'{self.ns}/state/duty', 10)
        self.pub_iq     = self.create_publisher(Float32, f'{self.ns}/state/motor_current_a', 10)

        self.pub_vin    = self.create_publisher(Float32, f'{self.ns}/state/input_voltage_v', 10)
        self.pub_iin    = self.create_publisher(Float32, f'{self.ns}/state/input_current_a', 10)  # <-- DC current

        self.pub_temp_fet   = self.create_publisher(Float32, f'{self.ns}/state/temp_fet_c', 10)
        self.pub_temp_motor = self.create_publisher(Float32, f'{self.ns}/state/temp_motor_c', 10)
        self.pub_fault  = self.create_publisher(Int32,   f'{self.ns}/state/fault_code', 10)

        # ----------------------------
        # RX notifier
        # ----------------------------
        self.notifier = can.Notifier(self.bus, [self._can_rx])

        self.get_logger().info(
            f'VESC CAN node started (id={self.vesc_id}, ns={self.ns})'
        )

    # ==========================================================
    # CAN TX helpers
    # ==========================================================
    def _send_int32(self, packet_id: int, value: int):
        can_id = (packet_id << 8) | self.vesc_id
        msg = can.Message(
            arbitration_id=can_id,
            is_extended_id=True,
            data=struct.pack('>i', value)
        )
        try:
            self.bus.send(msg)
        except can.CanError as e:
            self.get_logger().error(f'CAN TX failed: {e}')

    def duty_cb(self, msg: Float32):
        duty = max(min(msg.data, self.max_abs_duty), -self.max_abs_duty)
        self._send_int32(CAN_PACKET_SET_DUTY, int(duty * 100000))

    def rpm_cb(self, msg: Int32):
        self._send_int32(CAN_PACKET_SET_RPM, msg.data)

    # ==========================================================
    # CAN RX callback
    # ==========================================================
    def _can_rx(self, msg: can.Message):
        if not msg.is_extended_id:
            return

        packet_id = (msg.arbitration_id >> 8) & 0xFF
        vesc_id   = msg.arbitration_id & 0xFF

        if vesc_id != self.vesc_id:
            return

        d = msg.data

        # -------- STATUS (9) --------
        if packet_id == CAN_PACKET_STATUS:
            erpm, i_dA, duty_m = struct.unpack('>ihh', d)
            self.pub_erpm.publish(Int32(data=erpm))
            self.pub_iq.publish(Float32(data=i_dA / 10.0))
            self.pub_duty.publish(Float32(data=duty_m / 1000.0))

        # -------- STATUS_4 (16) -----
        elif packet_id == CAN_PACKET_STATUS_4:
            t_fet, t_motor, i_in_dA, _ = struct.unpack('>hhhh', d)
            self.pub_temp_fet.publish(Float32(data=t_fet / 10.0))
            self.pub_temp_motor.publish(Float32(data=t_motor / 10.0))
            self.pub_iin.publish(Float32(data=i_in_dA / 10.0))  # <-- publish DC/input current

        # -------- STATUS_5 (27) -----
        elif packet_id == CAN_PACKET_STATUS_5:
            # Legacy layout you observed: tacho, tacho_abs, vin*10, fault
            _, _, vin_dV, fault = struct.unpack('>hhhh', d)
            self.pub_vin.publish(Float32(data=vin_dV / 10.0))
            self.pub_fault.publish(Int32(data=fault))


def main():
    rclpy.init()
    node = VescCanNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
