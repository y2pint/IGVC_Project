#!/usr/bin/env python3
import math
import numpy as np
import cv2

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PolygonStamped, Point32
from std_msgs.msg import Header

from cv_bridge import CvBridge


def clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


class LaneDetectorNode(Node):
    """
    Lane detection MVP:
      - HSV thresholding (white + optional yellow)
      - ROI cropping
      - morphology cleanup
      - histogram + sliding window to find lane pixels
      - poly fit left/right and compute centerline (pixel space)
    """

    def __init__(self):
        super().__init__('lane_detector_node')

        # -------------------------
        # Parameters (tune live)
        # -------------------------
        self.declare_parameter('image_topic', '/zed/zed_node/rgb/image_rect_color')
        self.declare_parameter('camera_info_topic', '/zed/zed_node/rgb/camera_info')

        # ROI: use bottom fraction of image [roi_y_min_frac, 1.0]
        self.declare_parameter('roi_y_min_frac', 0.30)

        # HSV thresholds for WHITE (default values are a starting point)
        self.declare_parameter('white_h_min', 0)
        self.declare_parameter('white_h_max', 200)
        self.declare_parameter('white_s_min', 0)
        self.declare_parameter('white_s_max', 60)
        self.declare_parameter('white_v_min', 190)
        self.declare_parameter('white_v_max', 255)

        # Optional YELLOW threshold (off by default)
        self.declare_parameter('use_yellow', False)
        self.declare_parameter('yellow_h_min', 15)
        self.declare_parameter('yellow_h_max', 40)
        self.declare_parameter('yellow_s_min', 80)
        self.declare_parameter('yellow_s_max', 255)
        self.declare_parameter('yellow_v_min', 80)
        self.declare_parameter('yellow_v_max', 255)

        # Morphology
        self.declare_parameter('morph_kernel', 5)     # odd int
        self.declare_parameter('morph_iters', 1)

        # Sliding window parameters
        self.declare_parameter('nwindows', 9)
        self.declare_parameter('margin', 60)          # half window width in pixels
        self.declare_parameter('minpix', 50)

        # Lane sanity
        self.declare_parameter('min_lane_width_px', 120)
        self.declare_parameter('max_lane_width_px', 900)

        # Publish cadence
        self.declare_parameter('publish_debug', True)

        self.bridge = CvBridge()
        self.camera_info = None

        image_topic = self.get_parameter('image_topic').get_parameter_value().string_value
        caminfo_topic = self.get_parameter('camera_info_topic').get_parameter_value().string_value

        self.sub_img = self.create_subscription(Image, image_topic, self.on_image, 10)
        self.sub_cam = self.create_subscription(CameraInfo, caminfo_topic, self.on_camera_info, 10)

        self.pub_mask = self.create_publisher(Image, '/lane/mask', 10)
        self.pub_dbg = self.create_publisher(Image, '/lane/debug_image', 10)
        self.pub_center_px = self.create_publisher(PolygonStamped, '/lane/centerline_pixels', 10)

        self.get_logger().info(f'LaneDetectorNode listening on {image_topic}')
        self.get_logger().info('Publishing: /lane/mask, /lane/debug_image, /lane/centerline_pixels')

    def on_camera_info(self, msg: CameraInfo):
        self.camera_info = msg

    def on_image(self, msg: Image):
        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f'cv_bridge error: {e}')
            return

        h, w = bgr.shape[:2]

        roi_y_min_frac = float(self.get_parameter('roi_y_min_frac').value)
        roi_y0 = clamp_int(int(roi_y_min_frac * h), 0, h - 1)

        roi = bgr[roi_y0:h, :, :]

        mask = self._threshold_lane_mask(roi)
        mask = self._morph_cleanup(mask)

        # Sliding window search on binary image
        left_fit, right_fit, lane_ok = self._fit_lanes_sliding_window(mask)

        # Build outputs in full image coordinates
        full_mask = np.zeros((h, w), dtype=np.uint8)
        full_mask[roi_y0:h, :] = mask

        # Debug overlay
        publish_debug = bool(self.get_parameter('publish_debug').value)
        dbg = bgr.copy()

        centerline_poly = None
        if lane_ok and left_fit is not None and right_fit is not None:
            centerline_poly = 0.5 * (left_fit + right_fit)

            # draw detected lane region + centerline
            dbg = self._draw_lane_overlay(dbg, roi_y0, left_fit, right_fit, centerline_poly)

        # Publish mask
        self.pub_mask.publish(self.bridge.cv2_to_imgmsg(full_mask, encoding='mono8'))

        # Publish debug image
        if publish_debug:
            self.pub_dbg.publish(self.bridge.cv2_to_imgmsg(dbg, encoding='bgr8'))

        # Publish centerline pixels (PolygonStamped)
        poly_msg = self._centerline_polygon_msg(
            header=msg.header,
            roi_y0=roi_y0,
            w=w,
            h=h,
            center_fit=centerline_poly,
            lane_ok=lane_ok
        )
        self.pub_center_px.publish(poly_msg)

    def _threshold_lane_mask(self, bgr_roi: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(bgr_roi, cv2.COLOR_BGR2HSV)

        # White mask
        wh = int(self.get_parameter('white_h_min').value), int(self.get_parameter('white_h_max').value)
        ws = int(self.get_parameter('white_s_min').value), int(self.get_parameter('white_s_max').value)
        wv = int(self.get_parameter('white_v_min').value), int(self.get_parameter('white_v_max').value)
        lower_white = np.array([wh[0], ws[0], wv[0]], dtype=np.uint8)
        upper_white = np.array([wh[1], ws[1], wv[1]], dtype=np.uint8)
        mask_white = cv2.inRange(hsv, lower_white, upper_white)

        use_yellow = bool(self.get_parameter('use_yellow').value)
        if not use_yellow:
            return mask_white

        yh = int(self.get_parameter('yellow_h_min').value), int(self.get_parameter('yellow_h_max').value)
        ys = int(self.get_parameter('yellow_s_min').value), int(self.get_parameter('yellow_s_max').value)
        yv = int(self.get_parameter('yellow_v_min').value), int(self.get_parameter('yellow_v_max').value)
        lower_y = np.array([yh[0], ys[0], yv[0]], dtype=np.uint8)
        upper_y = np.array([yh[1], ys[1], yv[1]], dtype=np.uint8)
        mask_yellow = cv2.inRange(hsv, lower_y, upper_y)

        return cv2.bitwise_or(mask_white, mask_yellow)

    def _morph_cleanup(self, mask: np.ndarray) -> np.ndarray:
        k = int(self.get_parameter('morph_kernel').value)
        if k < 1:
            return mask
        if k % 2 == 0:
            k += 1
        iters = int(self.get_parameter('morph_iters').value)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        cleaned = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=iters)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=iters)
        return cleaned

    def _fit_lanes_sliding_window(self, binary: np.ndarray):
        """
        Returns:
          left_fit (np.array shape (3,)) for x(y) = a y^2 + b y + c in ROI coordinates
          right_fit
          lane_ok (bool)
        """
        # Ensure binary is 0/255
        bin_img = (binary > 0).astype(np.uint8)

        height, width = bin_img.shape[:2]
        if height < 10 or width < 10:
            return None, None, False

        # Histogram of bottom half
        histogram = np.sum(bin_img[height // 2:, :], axis=0)

        midpoint = width // 2
        leftx_base = int(np.argmax(histogram[:midpoint]))
        rightx_base = int(np.argmax(histogram[midpoint:]) + midpoint)

        nwindows = int(self.get_parameter('nwindows').value)
        margin = int(self.get_parameter('margin').value)
        minpix = int(self.get_parameter('minpix').value)

        window_height = max(1, height // nwindows)

        # Identify nonzero pixels
        nonzero = bin_img.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])

        leftx_current = leftx_base
        rightx_current = rightx_base

        left_lane_inds = []
        right_lane_inds = []

        for window in range(nwindows):
            win_y_low = height - (window + 1) * window_height
            win_y_high = height - window * window_height

            win_xleft_low = leftx_current - margin
            win_xleft_high = leftx_current + margin
            win_xright_low = rightx_current - margin
            win_xright_high = rightx_current + margin

            good_left = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                         (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
            good_right = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                          (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]

            left_lane_inds.append(good_left)
            right_lane_inds.append(good_right)

            if len(good_left) > minpix:
                leftx_current = int(np.mean(nonzerox[good_left]))
            if len(good_right) > minpix:
                rightx_current = int(np.mean(nonzerox[good_right]))

        left_lane_inds = np.concatenate(left_lane_inds) if left_lane_inds else np.array([], dtype=int)
        right_lane_inds = np.concatenate(right_lane_inds) if right_lane_inds else np.array([], dtype=int)

        if left_lane_inds.size < 200 or right_lane_inds.size < 200:
            return None, None, False

        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds]
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]

        # Fit x = a y^2 + b y + c
        try:
            left_fit = np.polyfit(lefty, leftx, 2)
            right_fit = np.polyfit(righty, rightx, 2)
        except Exception:
            return None, None, False

        # Sanity check lane width near bottom of ROI
        y_eval = height - 1
        left_x = left_fit[0]*y_eval*y_eval + left_fit[1]*y_eval + left_fit[2]
        right_x = right_fit[0]*y_eval*y_eval + right_fit[1]*y_eval + right_fit[2]
        lane_width = float(right_x - left_x)

        min_w = float(self.get_parameter('min_lane_width_px').value)
        max_w = float(self.get_parameter('max_lane_width_px').value)
        lane_ok = (lane_width > min_w) and (lane_width < max_w)

        if not lane_ok:
            return None, None, False

        return left_fit, right_fit, True

    def _draw_lane_overlay(self, bgr: np.ndarray, roi_y0: int, left_fit, right_fit, center_fit):
        h, w = bgr.shape[:2]

        # sample y values in ROI (image coordinates)
        y_vals = np.linspace(roi_y0, h - 1, num=80)
        y_roi = y_vals - roi_y0

        def eval_fit(fit, y):
            return fit[0]*y*y + fit[1]*y + fit[2]

        left_x = eval_fit(left_fit, y_roi)
        right_x = eval_fit(right_fit, y_roi)
        center_x = eval_fit(center_fit, y_roi)

        # clamp and build polyline points
        left_pts = np.stack([np.clip(left_x, 0, w-1), y_vals], axis=1).astype(np.int32)
        right_pts = np.stack([np.clip(right_x, 0, w-1), y_vals], axis=1).astype(np.int32)
        center_pts = np.stack([np.clip(center_x, 0, w-1), y_vals], axis=1).astype(np.int32)

        # draw
        cv2.polylines(bgr, [left_pts], False, (0, 255, 0), 2)
        cv2.polylines(bgr, [right_pts], False, (0, 255, 0), 2)
        cv2.polylines(bgr, [center_pts], False, (255, 0, 0), 2)

        # shade lane area for visual
        lane_poly = np.vstack([left_pts, right_pts[::-1]])
        overlay = bgr.copy()
        cv2.fillPoly(overlay, [lane_poly], (0, 255, 0))
        alpha = 0.15
        bgr = cv2.addWeighted(overlay, alpha, bgr, 1 - alpha, 0)

        return bgr

    def _centerline_polygon_msg(self, header: Header, roi_y0: int, w: int, h: int,
                               center_fit, lane_ok: bool) -> PolygonStamped:
        msg = PolygonStamped()
        msg.header = header
        msg.header.frame_id = header.frame_id if header.frame_id else 'camera_link'

        # If lane not OK, publish empty polygon
        if (not lane_ok) or (center_fit is None):
            msg.polygon.points = []
            return msg

        # Sample centerline pixels from near bottom up to ROI top
        y_vals = np.linspace(roi_y0, h - 1, num=30)
        y_roi = y_vals - roi_y0

        def eval_fit(fit, y):
            return fit[0]*y*y + fit[1]*y + fit[2]

        x_vals = eval_fit(center_fit, y_roi)

        pts = []
        for x, y in zip(x_vals, y_vals):
            u = float(np.clip(x, 0, w - 1))
            v = float(np.clip(y, 0, h - 1))
            pts.append(Point32(x=u, y=v, z=0.0))

        msg.polygon.points = pts
        return msg


def main():
    rclpy.init()
    node = LaneDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
