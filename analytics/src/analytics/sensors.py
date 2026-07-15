# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from scene_common import log


def update_environmental_sensor_readings(objects_in_sensor, sensor_id, cur_value, timestamp_str):
  """Track timestamped environmental sensor readings on each object's chain_data.

  Appends a new reading when the value changes; updates the timestamp of the
  last entry when the value is unchanged.

  Args:
    objects_in_sensor: List of AnalyticsObject currently inside this sensor.
    sensor_id:         Sensor identifier string.
    cur_value:         Raw sensor value (must be convertible to float).
    timestamp_str:     ISO-8601 timestamp string for this reading.

  Returns:
    True on success, False if cur_value cannot be converted to float.
  """
  try:
    cur_value_float = float(cur_value)
  except (ValueError, TypeError):
    log.error("Invalid sensor value", sensor_id, cur_value)
    return False

  for obj in objects_in_sensor:
    with obj.chain_data._lock:
      if sensor_id in obj.chain_data.env_sensor_state:
        state = obj.chain_data.env_sensor_state[sensor_id]

        if 'readings' not in state:
          state['readings'] = []
        if state['readings'] and state['readings'][-1][1] == cur_value_float:
          state['readings'][-1] = (timestamp_str, cur_value_float)
        else:
          state['readings'].append((timestamp_str, cur_value_float))
      else:
        obj.chain_data.env_sensor_state[sensor_id] = {
          'readings': [(timestamp_str, cur_value_float)]
        }

  return True


def update_attribute_sensor_events(objects_in_sensor, sensor_id, cur_value, timestamp_str):
  """Append discrete attribute sensor events to each object's chain_data.

  Updates the timestamp of the last event when the value is unchanged.

  Args:
    objects_in_sensor: List of AnalyticsObject currently inside this sensor.
    sensor_id:         Sensor identifier string.
    cur_value:         Raw sensor value (serialised to string for comparison).
    timestamp_str:     ISO-8601 timestamp string for this event.
  """
  cur_value_str = str(cur_value)
  for obj in objects_in_sensor:
    with obj.chain_data._lock:
      if sensor_id not in obj.chain_data.attr_sensor_events:
        obj.chain_data.attr_sensor_events[sensor_id] = []

      events = obj.chain_data.attr_sensor_events[sensor_id]
      if events and events[-1][1] == cur_value_str:
        events[-1] = (timestamp_str, cur_value_str)
      else:
        events.append((timestamp_str, cur_value_str))
