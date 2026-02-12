from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

# QoS presets
qos_reliable = QoSProfile(depth=10)
qos_reliable.reliability = ReliabilityPolicy.RELIABLE
qos_reliable.durability = DurabilityPolicy.VOLATILE

qos_sensor = QoSProfile(depth=10)
qos_sensor.reliability = ReliabilityPolicy.BEST_EFFORT
qos_sensor.durability = DurabilityPolicy.VOLATILE
