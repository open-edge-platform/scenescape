# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""MQTT to V2X PSM (Personal Safety Message) Bridge.

This module subscribes to SceneScape MQTT topics and publishes pedestrian
detection data to V2X infrastructure as Personal Safety Messages.
"""

import json
import logging
import os
import ssl
import time
import xml.etree.ElementTree as ET
from typing import Dict, Any, List

import numpy as np
import paho.mqtt.client as mqtt
import requests

logging.basicConfig(
  level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MQTT_SERVER = os.getenv('MQTT_SERVER', 'broker.scenescape.intel.com')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USERNAME = os.getenv('MQTT_USERNAME', 'admin')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
MQTT_USE_TLS = os.getenv('MQTT_USE_TLS', 'true').lower() in ('true', '1', 'yes')
MQTT_TLS_INSECURE = os.getenv('MQTT_TLS_INSECURE', 'true').lower() in ('true', '1', 'yes')
MQTT_CA_CERT = os.getenv('MQTT_CA_CERT', '')  # Path to CA certificate file

# Subscribe to all regions using wildcard
MQTT_SUB_TOPIC = 'scenescape/data/region/+/#'

V2X_API_URL = os.getenv('V2X_API_URL', 'http://127.0.0.1:9000')
V2X_API_TIMEOUT = int(os.getenv('V2X_API_TIMEOUT', '5'))

# PSM message counter (wraps at 128)
message_counter = 0

# PSM XML default values
PSM_ACCURACY_SEMI_MAJOR = "255"  # 255 means unavailable
PSM_ACCURACY_SEMI_MINOR = "255"  # 255 means unavailable
PSM_ACCURACY_ORIENTATION = "65535"  # 65535 means unavailable

# ASN.1 conversion constants
MAX_TEMP_ID = 0x100000000  # 4-byte unsigned integer for ID generation
MICRODEGREE_MULTIPLIER = 10000000  # Convert degrees to 1/10th microdegrees (10^7)
ELEVATION_MULTIPLIER = 10  # Convert meters to decimeters (10 cm units)
SPEED_UNIT_M_S = 0.02  # ASN.1 speed unit (0.02 m/s per unit)
MAX_SPEED_ASN1 = 8191  # Maximum speed value, 8191 indicates unavailable
HEADING_UNIT_DEG = 0.0125  # ASN.1 heading unit (0.0125 degrees per unit)
MAX_HEADING_ASN1 = 28800  # Maximum heading value (corresponds to 360 degrees)

# ASN.1 valid ranges
LAT_MIN = -900000000  # -90 degrees in 1/10th microdegrees
LAT_MAX = 900000000   # +90 degrees in 1/10th microdegrees
LON_MIN = -1800000000  # -180 degrees in 1/10th microdegrees
LON_MAX = 1800000000   # +180 degrees in 1/10th microdegrees
ELEVATION_MIN = -4096  # Minimum elevation in decimeters
ELEVATION_MAX = 61439  # Maximum elevation in decimeters


def create_psm_xml() -> ET.Element:
  """Create PSM XML structure template.

  Returns:
    ET.Element: Root element of PSM XML structure
  """
  root = ET.Element("PersonalSafetyMessage")
  basic_type = ET.SubElement(root, "basicType")
  ET.SubElement(basic_type, "aPEDESTRIAN")

  ET.SubElement(root, "secMark")
  ET.SubElement(root, "msgCnt")
  ET.SubElement(root, "id")

  position = ET.SubElement(root, "position")
  ET.SubElement(position, "lat")
  ET.SubElement(position, "long")
  ET.SubElement(position, "elevation")

  accuracy = ET.SubElement(root, "accuracy")
  ET.SubElement(accuracy, "semiMajor")
  ET.SubElement(accuracy, "semiMinor")
  ET.SubElement(accuracy, "orientation")

  ET.SubElement(root, "speed")
  ET.SubElement(root, "heading")

  return root


def populate_psm_xml(root: ET.Element, obj: Dict[str, Any], lla: List[float]) -> bool:
  """Populate PSM XML with pedestrian data.

  Args:
    root: XML root element
    obj: Pedestrian object data
    lla: [latitude, longitude, altitude] array

  Returns:
    bool: True if successfully populated, False otherwise
  """

  lat_microdegrees = int(lla[0] * MICRODEGREE_MULTIPLIER)
  lon_microdegrees = int(lla[1] * MICRODEGREE_MULTIPLIER)

  if not (LAT_MIN <= lat_microdegrees <= LAT_MAX):
    logger.warning("Invalid latitude: %s", lla[0])
    return False
  if not (LON_MIN <= lon_microdegrees <= LON_MAX):
    logger.warning("Invalid longitude: %s", lla[1])
    return False

  # Validate and convert elevation to decimeters
  elevation_dm = int(lla[2] * ELEVATION_MULTIPLIER)
  if not (ELEVATION_MIN <= elevation_dm <= ELEVATION_MAX):
    logger.warning("Elevation out of range: %s dm (%.1f m)", elevation_dm, lla[2])
    return False

  # Generate 4-byte hex ID from pedestrian UUID
  temp_id = abs(hash(obj['id'])) % MAX_TEMP_ID

  # Calculate secMark (milliseconds within the current minute, 0-59999)
  current_time = time.time()
  sec_mark = int((current_time % 60) * 1000)

  # Increment message counter (wraps at 128)
  global message_counter
  message_counter = (message_counter + 1) % 128

  # Populate all fields (all elements are guaranteed to exist from create_psm_xml)
  root.find("secMark").text = str(sec_mark)
  root.find("msgCnt").text = str(message_counter)

  root.find("id").text = format(temp_id, '08x')

  root.find("position/lat").text = str(lat_microdegrees)
  root.find("position/long").text = str(lon_microdegrees)
  root.find("position/elevation").text = str(elevation_dm)

  root.find("accuracy/semiMajor").text = PSM_ACCURACY_SEMI_MAJOR
  root.find("accuracy/semiMinor").text = PSM_ACCURACY_SEMI_MINOR
  root.find("accuracy/orientation").text = PSM_ACCURACY_ORIENTATION

  # Calculate speed from velocity vector and convert to ASN.1 units
  velocity = obj.get('velocity', [0, 0, 0])
  speed_m_s = float(np.linalg.norm(velocity))
  speed_asn1 = min(int(speed_m_s / SPEED_UNIT_M_S), MAX_SPEED_ASN1)
  root.find("speed").text = str(speed_asn1)

  heading_asn1 = int(obj['heading'] / HEADING_UNIT_DEG) % MAX_HEADING_ASN1
  root.find("heading").text = str(heading_asn1)

  return True


def post_to_v2x_api(xml_data: bytes) -> bool:
  """Post PSM XML to V2X Hub API.

  Args:
    xml_data: XML data as bytes

  Returns:
    bool: True if successful, False otherwise
  """
  headers = {"Content-Type": "application/xml"}
  try:
    logger.debug("Posting PSM to V2X API")
    response = requests.post(
      V2X_API_URL, data=xml_data, headers=headers, timeout=V2X_API_TIMEOUT)
    if response.status_code >= 400:
      logger.error("V2X API error: %d - %s", response.status_code, response.text)
      return False
    logger.debug("PSM posted successfully")
    return True
  except requests.exceptions.RequestException as e:
    logger.error("Failed to post to V2X API: %s", e)
    return False


def on_message(client, _userdata, message):
  """Handle incoming MQTT messages.

  Args:
    client: MQTT client instance
    _userdata: User data (unused)
    message: MQTT message
  """
  try:
    msg = json.loads(message.payload.decode("utf-8"))
  except (json.JSONDecodeError, UnicodeDecodeError) as e:
    logger.error("Failed to decode MQTT message: %s", e)
    return

  objects = msg.get('objects', [])

  for obj in objects:
    if obj.get('category') != "pedestrian":
      continue

    # Extract geospatial data (already provided by backend)
    lla = obj.get('lat_long_alt')  # [lat, lon, alt]
    if not lla:
      logger.warning("Pedestrian %s missing lat_long_alt data", obj.get('id'))
      continue

    psm_root = create_psm_xml()
    if not populate_psm_xml(psm_root, obj, lla):
      logger.warning("Failed to populate PSM XML for pedestrian %s, skipping", obj.get('id'))
      logger.warning("Pedestrian data: %s", obj)
      continue

    xml_str = ET.tostring(psm_root, encoding='unicode', method='xml')
    logger.debug("Generated PSM XML: %s", xml_str)
    post_to_v2x_api(xml_str.encode('utf-8'))


def on_connect(client, _userdata, _flags, rc):
  """Handle MQTT connection event.

  Args:
    client: MQTT client instance
    _userdata: User data (unused)
    _flags: Connection flags (unused)
    rc: Connection result code
  """
  if rc == 0:
    logger.info("Connected to MQTT broker successfully")
    client.subscribe(MQTT_SUB_TOPIC, qos=0)
    logger.info("Subscribed to topic: %s", MQTT_SUB_TOPIC)
  else:
    logger.error("MQTT connection failed with code %d", rc)


def on_disconnect(_client, _userdata, rc):
  """Handle MQTT disconnection event.

  Args:
    _client: MQTT client instance (unused)
    _userdata: User data (unused)
    rc: Disconnection result code
  """
  if rc != 0:
    logger.warning("Unexpected MQTT disconnection. Code: %d", rc)


def main():
  """Main entry point for MQTT-V2X bridge."""
  client = mqtt.Client()
  client.on_connect = on_connect
  client.on_disconnect = on_disconnect
  client.on_message = on_message

  # Configure TLS/SSL if enabled
  if MQTT_USE_TLS:
    if MQTT_CA_CERT:
      # Use provided CA certificate for verification
      ssl_ctx = ssl.create_default_context(cafile=MQTT_CA_CERT)
      logger.info("Using CA certificate: %s", MQTT_CA_CERT)
    else:
      # Use system default CA certificates
      ssl_ctx = ssl.create_default_context()

    if MQTT_TLS_INSECURE:
      # Skip certificate verification (insecure)
      ssl_ctx.check_hostname = False
      ssl_ctx.verify_mode = ssl.CERT_NONE
      logger.warning("TLS certificate verification disabled (insecure)")

    client.tls_set_context(ssl_ctx)

  client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

  logger.info("Connecting to MQTT broker at %s:%d...", MQTT_SERVER, MQTT_PORT)
  logger.info("Subscribing to: %s", MQTT_SUB_TOPIC)
  logger.info("V2X API endpoint: %s", V2X_API_URL)
  try:
    client.connect(MQTT_SERVER, MQTT_PORT, keepalive=60)
    client.loop_forever()
  except KeyboardInterrupt:
    logger.info("Shutting down gracefully...")
    client.disconnect()
  except Exception as e:
    logger.exception("Fatal error: %s", e)
    return 1

  return 0


if __name__ == "__main__":
  exit(main())
