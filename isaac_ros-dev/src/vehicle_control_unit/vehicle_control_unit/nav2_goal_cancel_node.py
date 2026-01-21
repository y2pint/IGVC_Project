#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool
from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal

from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy


STATUS_ACCEPTED = 1
STATUS_EXECUTING = 2


class Nav2GoalCancelNode(Node):
    def __init__(self):
        super().__init__('nav2_goal_cancel_node')

        self.declare_parameter('goal_reached_topic', '/goal_reached')
        self.declare_parameter('action_name', '/navigate_to_pose')
        self.declare_parameter('retry_period_sec', 0.10)
        self.declare_parameter('retry_timeout_sec', 2.0)

        goal_reached_topic = self.get_parameter('goal_reached_topic').value
        action_name = self.get_parameter('action_name').value.strip('/')

        self._status_topic = f'/{action_name}/_action/status'
        self._cancel_srv_name = f'/{action_name}/_action/cancel_goal'

        # Humble-compatible QoS for action status
        status_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self._latest_goal_info = None
        self._prev_goal_reached = False

        self._retry_timer = None
        self._retry_deadline = None
        self._cancel_sent_uuid = None

        self.create_subscription(Bool, goal_reached_topic, self._on_goal_reached, 10)
        self.create_subscription(GoalStatusArray, self._status_topic, self._on_status, status_qos)

        self._cancel_cli = self.create_client(CancelGoal, self._cancel_srv_name)

        self.get_logger().info(f'goal_reached_topic: {goal_reached_topic}')
        self.get_logger().info(f'status_topic:       {self._status_topic}')
        self.get_logger().info(f'cancel service:     {self._cancel_srv_name}')

    def _on_status(self, msg: GoalStatusArray):
        chosen = None

        # Prefer EXECUTING
        for st in msg.status_list:
            if st.status == STATUS_EXECUTING:
                chosen = st
                break

        # Fallback to ACCEPTED
        if chosen is None:
            for st in msg.status_list:
                if st.status == STATUS_ACCEPTED:
                    chosen = st
                    break

        self._latest_goal_info = chosen.goal_info if chosen else None

    def _on_goal_reached(self, msg: Bool):
        # Trigger only on rising edge
        rising = msg.data and not self._prev_goal_reached
        self._prev_goal_reached = msg.data

        if not rising:
            return

        now = self.get_clock().now()
        timeout = float(self.get_parameter('retry_timeout_sec').value)
        period = float(self.get_parameter('retry_period_sec').value)
        self._retry_deadline = now + rclpy.duration.Duration(seconds=timeout)

        if self._retry_timer:
            self._retry_timer.cancel()

        self._retry_timer = self.create_timer(period, self._retry_cancel_tick)
        self.get_logger().info('goal_reached rising edge → begin cancel retry window')

    def _retry_cancel_tick(self):
        if self.get_clock().now() > self._retry_deadline:
            self.get_logger().warn('Cancel retry window expired (no active goal).')
            self._retry_timer.cancel()
            self._retry_timer = None
            return

        if self._latest_goal_info is None:
            return

        uuid = bytes(self._latest_goal_info.goal_id.uuid)
        if self._cancel_sent_uuid == uuid:
            self._retry_timer.cancel()
            self._retry_timer = None
            return

        if not self._cancel_cli.wait_for_service(timeout_sec=0.2):
            return

        req = CancelGoal.Request()
        req.goal_info = self._latest_goal_info

        self.get_logger().info('Sending cancel_goal to Nav2')
        future = self._cancel_cli.call_async(req)
        future.add_done_callback(self._on_cancel_response)

        self._cancel_sent_uuid = uuid

        self._retry_timer.cancel()
        self._retry_timer = None

    def _on_cancel_response(self, future):
        try:
            resp = future.result()
        except Exception as e:
            self.get_logger().error(f'Cancel service call failed: {e}')
            return

        self.get_logger().info(
            f'Cancel response: return_code={resp.return_code}, '
            f'goals_canceling={len(resp.goals_canceling)}'
        )


def main():
    rclpy.init()
    node = Nav2GoalCancelNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
