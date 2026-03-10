#!/usr/bin/env python3

import math
import os
from typing import List, Optional, Tuple

import yaml
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Int32, Bool

import matplotlib.pyplot as plt
from matplotlib.patches import Circle


class MissionPlotterNode(Node):
    def __init__(self) -> None:
        super().__init__('mission_plotter_node')

        # -----------------------------
        # Parameters
        # -----------------------------
        self.declare_parameter('waypoints_file', '')
        self.declare_parameter('pose_topic', '/mission/global_pose_xy')
        self.declare_parameter('target_topic', '/mission/current_waypoint_xy')
        self.declare_parameter('carrot_topic', '/mission/carrot_target')
        self.declare_parameter('index_topic', '/mission/waypoint_index')
        self.declare_parameter('complete_topic', '/mission/mission_complete')
        self.declare_parameter('acceptance_radius_m', 2.5)
        self.declare_parameter('update_rate_hz', 5.0)
        self.declare_parameter('figure_title', 'Mission Plotter')
        self.declare_parameter('show_trail', True)
        self.declare_parameter('trail_length', 200)
        self.declare_parameter('axis_margin_m', 5.0)
        self.declare_parameter('equal_axis', True)
        self.declare_parameter('robot_radius_m', 2.0)
        self.declare_parameter('target_radius_m', 2.0)
        self.declare_parameter('carrot_radius_m', 1.0)
        self.declare_parameter('draw_robot_radius', True)
        self.declare_parameter('draw_target_radius', True)
        self.declare_parameter('draw_carrot_radius', True)

        self.waypoints_file = str(self.get_parameter('waypoints_file').value)
        self.pose_topic = str(self.get_parameter('pose_topic').value)
        self.target_topic = str(self.get_parameter('target_topic').value)
        self.carrot_topic = str(self.get_parameter('carrot_topic').value)
        self.index_topic = str(self.get_parameter('index_topic').value)
        self.complete_topic = str(self.get_parameter('complete_topic').value)
        self.acceptance_radius_m = float(self.get_parameter('acceptance_radius_m').value)
        self.update_rate_hz = float(self.get_parameter('update_rate_hz').value)
        self.figure_title = str(self.get_parameter('figure_title').value)
        self.show_trail = bool(self.get_parameter('show_trail').value)
        self.trail_length = int(self.get_parameter('trail_length').value)
        self.axis_margin_m = float(self.get_parameter('axis_margin_m').value)
        self.equal_axis = bool(self.get_parameter('equal_axis').value)
        self.robot_radius_m = float(self.get_parameter('robot_radius_m').value)
        self.target_radius_m = float(self.get_parameter('target_radius_m').value)
        self.carrot_radius_m = float(self.get_parameter('carrot_radius_m').value)
        self.draw_robot_radius = bool(self.get_parameter('draw_robot_radius').value)
        self.draw_target_radius = bool(self.get_parameter('draw_target_radius').value)
        self.draw_carrot_radius = bool(self.get_parameter('draw_carrot_radius').value)

        # -----------------------------
        # Internal state
        # -----------------------------
        self.robot_pose: Optional[PoseStamped] = None
        self.current_target: Optional[PoseStamped] = None
        self.carrot_target: Optional[PoseStamped] = None
        self.current_index: Optional[int] = None
        self.mission_complete: bool = False

        self.pose_trail: List[Tuple[float, float]] = []
        self.waypoints_xy: List[Tuple[float, float]] = []

        # -----------------------------
        # Load waypoints from YAML
        # -----------------------------
        self._load_waypoints()

        # -----------------------------
        # Subscribers
        # -----------------------------
        self.pose_sub = self.create_subscription(
            PoseStamped,
            self.pose_topic,
            self._pose_cb,
            10
        )

        self.target_sub = self.create_subscription(
            PoseStamped,
            self.target_topic,
            self._target_cb,
            10
        )

        self.carrot_sub = self.create_subscription(
            PoseStamped,
            self.carrot_topic,
            self._carrot_cb,
            10
        )

        self.index_sub = self.create_subscription(
            Int32,
            self.index_topic,
            self._index_cb,
            10
        )

        self.complete_sub = self.create_subscription(
            Bool,
            self.complete_topic,
            self._complete_cb,
            10
        )

        # -----------------------------
        # Matplotlib setup
        # -----------------------------
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(9, 7))
        try:
            self.fig.canvas.manager.set_window_title(self.figure_title)
        except Exception:
            pass

        self.fig.suptitle(self.figure_title)

        # Timer for redraw
        timer_period = 1.0 / max(self.update_rate_hz, 0.5)
        self.timer = self.create_timer(timer_period, self._update_plot)

        self.get_logger().info('MissionPlotterNode started')
        self.get_logger().info(f'pose_topic      : {self.pose_topic}')
        self.get_logger().info(f'target_topic    : {self.target_topic}')
        self.get_logger().info(f'carrot_topic    : {self.carrot_topic}')
        self.get_logger().info(f'index_topic     : {self.index_topic}')
        self.get_logger().info(f'complete_topic  : {self.complete_topic}')
        self.get_logger().info(f'waypoints_file  : {self.waypoints_file}')
        self.get_logger().info(f'loaded waypoints: {len(self.waypoints_xy)}')

    # ------------------------------------------------------------------
    # YAML loading
    # ------------------------------------------------------------------
    def _load_waypoints(self) -> None:
        self.waypoints_xy = []

        if not self.waypoints_file:
            self.get_logger().warn('No waypoints_file parameter set')
            return

        if not os.path.exists(self.waypoints_file):
            self.get_logger().error(f'Waypoints file does not exist: {self.waypoints_file}')
            return

        try:
            with open(self.waypoints_file, 'r') as f:
                data = yaml.safe_load(f)
        except Exception as e:
            self.get_logger().error(f'Failed to load YAML: {e}')
            return

        raw_list = None
        if isinstance(data, dict):
            if 'waypoints' in data and isinstance(data['waypoints'], list):
                raw_list = data['waypoints']
            else:
                for k, v in data.items():
                    if isinstance(v, list):
                        raw_list = v
                        self.get_logger().warn(
                            f'Using list under key "{k}" as waypoint list'
                        )
                        break
        elif isinstance(data, list):
            raw_list = data

        if raw_list is None:
            self.get_logger().error('Could not find a waypoint list in YAML')
            return

        for i, wp in enumerate(raw_list):
            xy = self._extract_xy_from_waypoint(wp)
            if xy is None:
                self.get_logger().warn(f'Skipping waypoint {i}: could not parse x/y')
                continue
            self.waypoints_xy.append(xy)

        if not self.waypoints_xy:
            self.get_logger().warn('No valid waypoints parsed from YAML')

    def _extract_xy_from_waypoint(self, wp) -> Optional[Tuple[float, float]]:
        if not isinstance(wp, dict):
            return None

        if 'x' in wp and 'y' in wp:
            try:
                return float(wp['x']), float(wp['y'])
            except Exception:
                return None

        if 'position' in wp and isinstance(wp['position'], dict):
            pos = wp['position']
            if 'x' in pos and 'y' in pos:
                try:
                    return float(pos['x']), float(pos['y'])
                except Exception:
                    return None

        if 'pose' in wp and isinstance(wp['pose'], dict):
            pose = wp['pose']
            if 'position' in pose and isinstance(pose['position'], dict):
                pos = pose['position']
                if 'x' in pos and 'y' in pos:
                    try:
                        return float(pos['x']), float(pos['y'])
                    except Exception:
                        return None

        return None

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------
    def _pose_cb(self, msg: PoseStamped) -> None:
        self.robot_pose = msg

        x = msg.pose.position.x
        y = msg.pose.position.y

        if self.show_trail:
            self.pose_trail.append((x, y))
            if len(self.pose_trail) > self.trail_length:
                self.pose_trail = self.pose_trail[-self.trail_length:]

    def _target_cb(self, msg: PoseStamped) -> None:
        self.current_target = msg

    def _carrot_cb(self, msg: PoseStamped) -> None:
        self.carrot_target = msg

    def _index_cb(self, msg: Int32) -> None:
        self.current_index = int(msg.data)

    def _complete_cb(self, msg: Bool) -> None:
        self.mission_complete = bool(msg.data)

    # ------------------------------------------------------------------
    # Plot update
    # ------------------------------------------------------------------
    def _update_plot(self) -> None:
        if not plt.fignum_exists(self.fig.number):
            self.get_logger().warn('Plot window closed; shutting down node.')
            rclpy.shutdown()
            return

        self.ax.clear()
        self.ax.set_title(self.figure_title)
        self.ax.set_xlabel('X [m]')
        self.ax.set_ylabel('Y [m]')
        self.ax.grid(True)

        # Draw all waypoints
        if self.waypoints_xy:
            wx = [p[0] for p in self.waypoints_xy]
            wy = [p[1] for p in self.waypoints_xy]
            self.ax.plot(wx, wy, '--', marker='o', label='Waypoints')

            for i, (x, y) in enumerate(self.waypoints_xy):
                self.ax.text(x, y, f' {i}', fontsize=9)

        # Active waypoint
        active_wp_xy = None
        if self.current_index is not None and 0 <= self.current_index < len(self.waypoints_xy):
            active_wp_xy = self.waypoints_xy[self.current_index]
            self.ax.plot(
                active_wp_xy[0],
                active_wp_xy[1],
                marker='*',
                markersize=16,
                linestyle='None',
                label='Active waypoint'
            )

            acc_circle = Circle(
                active_wp_xy,
                self.acceptance_radius_m,
                fill=False,
                linestyle=':',
                linewidth=2
            )
            self.ax.add_patch(acc_circle)

        # Current target topic
        target_xy = None
        if self.current_target is not None:
            tx = self.current_target.pose.position.x
            ty = self.current_target.pose.position.y
            target_xy = (tx, ty)
            self.ax.plot(
                tx,
                ty,
                marker='x',
                markersize=10,
                linestyle='None',
                label='Current target topic'
            )
            if self.draw_target_radius:
                target_circle = Circle(
                    (tx, ty),
                    self.target_radius_m,
                    fill=False,
                    linestyle='--',
                    linewidth=2
                )
                self.ax.add_patch(target_circle)

        # Carrot target topic
        carrot_xy = None
        if self.carrot_target is not None:
            cx = self.carrot_target.pose.position.x
            cy = self.carrot_target.pose.position.y
            carrot_xy = (cx, cy)
            self.ax.plot(
                cx,
                cy,
                marker='D',
                markersize=9,
                linestyle='None',
                label='Carrot target'
            )
            if self.draw_carrot_radius:
                carrot_circle = Circle(
                    (cx, cy),
                    self.carrot_radius_m,
                    fill=False,
                    linestyle='--',
                    linewidth=2
                )
                self.ax.add_patch(carrot_circle)

        # Robot trail
        if self.show_trail and len(self.pose_trail) >= 2:
            txs = [p[0] for p in self.pose_trail]
            tys = [p[1] for p in self.pose_trail]
            self.ax.plot(txs, tys, linewidth=1.5, label='Robot trail')

        # Robot pose
        robot_xy = None
        robot_yaw = None
        if self.robot_pose is not None:
            rx = self.robot_pose.pose.position.x
            ry = self.robot_pose.pose.position.y
            robot_xy = (rx, ry)
            robot_yaw = self._yaw_from_quaternion(
                self.robot_pose.pose.orientation.x,
                self.robot_pose.pose.orientation.y,
                self.robot_pose.pose.orientation.z,
                self.robot_pose.pose.orientation.w,
            )

            self.ax.plot(
                rx,
                ry,
                marker='o',
                markersize=10,
                linestyle='None',
                label='Robot'
            )

            if self.draw_robot_radius:
                robot_circle = Circle(
                    (rx, ry),
                    self.robot_radius_m,
                    fill=False,
                    linestyle='-.',
                    linewidth=2
                )
                self.ax.add_patch(robot_circle)

            arrow_len = max(1.0, 0.08 * self._plot_scale_estimate())
            dx = arrow_len * math.cos(robot_yaw)
            dy = arrow_len * math.sin(robot_yaw)
            self.ax.arrow(
                rx, ry, dx, dy,
                head_width=0.4 * arrow_len,
                head_length=0.5 * arrow_len,
                length_includes_head=True
            )

        # Axis scaling
        self._set_axes(robot_xy, active_wp_xy, target_xy, carrot_xy)

        # Status text
        status_lines = []
        status_lines.append(f'index: {self.current_index}')
        status_lines.append(f'complete: {self.mission_complete}')

        if robot_xy is not None:
            status_lines.append(f'robot: ({robot_xy[0]:.2f}, {robot_xy[1]:.2f})')

        if target_xy is not None:
            status_lines.append(f'target: ({target_xy[0]:.2f}, {target_xy[1]:.2f})')

        if carrot_xy is not None:
            status_lines.append(f'carrot: ({carrot_xy[0]:.2f}, {carrot_xy[1]:.2f})')

        dist_to_target = self._distance_to_target(
            robot_xy,
            target_xy if target_xy is not None else active_wp_xy
        )
        if dist_to_target is not None:
            status_lines.append(f'dist_to_target: {dist_to_target:.2f} m')

        dist_to_carrot = self._distance_to_target(robot_xy, carrot_xy)
        if dist_to_carrot is not None:
            status_lines.append(f'dist_to_carrot: {dist_to_carrot:.2f} m')

        self.ax.text(
            0.02,
            0.98,
            '\n'.join(status_lines),
            transform=self.ax.transAxes,
            verticalalignment='top',
            bbox=dict(boxstyle='round', alpha=0.85)
        )

        self.ax.legend(loc='best')
        self.fig.tight_layout()
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        plt.pause(0.001)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _distance_to_target(
        self,
        robot_xy: Optional[Tuple[float, float]],
        target_xy: Optional[Tuple[float, float]]
    ) -> Optional[float]:
        if robot_xy is None or target_xy is None:
            return None
        dx = target_xy[0] - robot_xy[0]
        dy = target_xy[1] - robot_xy[1]
        return math.hypot(dx, dy)

    def _yaw_from_quaternion(self, x: float, y: float, z: float, w: float) -> float:
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return math.atan2(siny_cosp, cosy_cosp)

    def _plot_scale_estimate(self) -> float:
        if self.waypoints_xy:
            xs = [p[0] for p in self.waypoints_xy]
            ys = [p[1] for p in self.waypoints_xy]
            dx = max(xs) - min(xs) if len(xs) > 1 else 5.0
            dy = max(ys) - min(ys) if len(ys) > 1 else 5.0
            return max(dx, dy, 5.0)
        return 10.0

    def _set_axes(
        self,
        robot_xy: Optional[Tuple[float, float]],
        active_wp_xy: Optional[Tuple[float, float]],
        target_xy: Optional[Tuple[float, float]],
        carrot_xy: Optional[Tuple[float, float]]
    ) -> None:
        xs = []
        ys = []

        for p in self.waypoints_xy:
            xs.append(p[0])
            ys.append(p[1])

        for p in [robot_xy, active_wp_xy, target_xy, carrot_xy]:
            if p is not None:
                xs.append(p[0])
                ys.append(p[1])

        if not xs or not ys:
            self.ax.set_xlim(-10, 10)
            self.ax.set_ylim(-10, 10)
            return

        xmin = min(xs) - self.axis_margin_m
        xmax = max(xs) + self.axis_margin_m
        ymin = min(ys) - self.axis_margin_m
        ymax = max(ys) + self.axis_margin_m

        if abs(xmax - xmin) < 1.0:
            cx = 0.5 * (xmin + xmax)
            xmin = cx - 5.0
            xmax = cx + 5.0

        if abs(ymax - ymin) < 1.0:
            cy = 0.5 * (ymin + ymax)
            ymin = cy - 5.0
            ymax = cy + 5.0

        self.ax.set_xlim(xmin, xmax)
        self.ax.set_ylim(ymin, ymax)

        if self.equal_axis:
            self.ax.set_aspect('equal', adjustable='box')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionPlotterNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            plt.close('all')
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()