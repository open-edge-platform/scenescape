# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import time
import sys

from argparse import ArgumentParser, Namespace
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Tuple, IO, Any

from scene_common.mqtt import PubSub

# Default configuration constants
MQTT_DEFAULT_ROOTCA = "/run/secrets/certs/scenescape-ca.pem"
MQTT_DEFAULT_AUTH = "/run/secrets/controller.auth"

# Configure logging
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MQTTRecorderError(Exception):
  """Custom exception for MQTT recorder errors"""
  pass


# TODO: extend and reuse this class in tests that have this functionality
class MQTTRecorder:
  """MQTT message recorder"""

  def __init__(self, broker: str, topic: str, auth_file: str = MQTT_DEFAULT_AUTH,
               rootca_file: str = MQTT_DEFAULT_ROOTCA):
    """Initialize the MQTT recorder.

    Args:
      broker: MQTT broker address
      topic: MQTT topic to subscribe to
      auth_file: Path to authentication file
      rootca_file: Path to root CA certificate file
    """
    self.broker = broker
    self.topic = topic
    self.auth_file = auth_file
    self.rootca_file = rootca_file
    self.client: Optional[PubSub] = None
    self.output_file: Optional[IO[str]] = None
    self.message_count = 0

    # Validate inputs
    self._validate_inputs()

  def _validate_inputs(self) -> None:
    """Validate input parameters"""
    if not self.broker:
      raise MQTTRecorderError("Broker address is required")
    if not self.topic:
      raise MQTTRecorderError("Topic is required")

  def _read_auth_credentials(self) -> Tuple[str, str]:
    """Read user and password from JSON auth file.

    Returns:
      Tuple of (username, password)

    Raises:
      MQTTRecorderError: If auth file is invalid or missing
    """
    auth_path = Path(self.auth_file)

    if not auth_path.exists():
      raise MQTTRecorderError(f"Auth file not found: {self.auth_file}")

    try:
      with open(auth_path, 'r', encoding='utf-8') as f:
        auth_data = json.load(f)

      if 'user' not in auth_data or 'password' not in auth_data:
        raise MQTTRecorderError(
          f"Auth file {self.auth_file} missing 'user' or 'password' fields"
        )

      return auth_data['user'], auth_data['password']

    except json.JSONDecodeError as e:
      raise MQTTRecorderError(
        f"Invalid JSON format in auth file {self.auth_file}: {e}"
      ) from e
    except Exception as e:
      raise MQTTRecorderError(
        f"Failed to read auth file {self.auth_file}: {e}"
      ) from e

  def _on_connect(self, mqttc: PubSub, obj: Any, flags: Any, rc: int) -> None:
    """Callback for MQTT connection event"""
    if rc == 0:
      logger.info("Connected to MQTT broker successfully")
      try:
        mqttc.subscribe(self.topic)
        logger.info(f"Subscribed to topic: {self.topic}")
      except Exception as e:
        logger.error(f"Failed to subscribe to topic {self.topic}: {e}")
    else:
      logger.error(f"Failed to connect to MQTT broker with code: {rc}")

  def _on_message(self, mqttc: PubSub, obj: Any, msg: Any) -> None:
    """Callback for MQTT message received event"""
    try:
      # Decode message payload
      message_str = msg.payload.decode("utf-8")
      message_data = json.loads(message_str)

      self.message_count += 1
      logger.debug(f"Received message {self.message_count} on topic {msg.topic}")

      # Write to output file if specified
      if self.output_file is not None:
        json.dump(message_data, self.output_file, separators=(',', ':'))
        self.output_file.write("\n")
        self.output_file.flush()  # Ensure data is written immediately

    except UnicodeDecodeError as e:
      logger.error(f"Failed to decode message payload as UTF-8: {e}")
    except json.JSONDecodeError as e:
      logger.error(f"Failed to parse message as JSON: {e}")
    except Exception as e:
      logger.error(f"Error processing message: {e}")

  @contextmanager
  def _output_file_context(self, output_path: Optional[str]):
    """Context manager for output file handling"""
    if output_path is None:
      self.output_file = None
      yield
    else:
      try:
        # Ensure parent directory exists
        output_file_path = Path(output_path)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file_path, 'w', encoding='utf-8') as f:
          self.output_file = f
          logger.info(f"Writing messages to: {output_path}")
          yield
      except Exception as e:
        raise MQTTRecorderError(f"Failed to open output file {output_path}: {e}") from e
      finally:
        self.output_file = None

  def record(self, interval: int, output_path: Optional[str] = None) -> int:
    """Record MQTT messages for the specified interval.

    Args:
      interval: Number of seconds to record messages
      output_path: Optional path to save captured messages

    Returns:
      Number of messages recorded

    Raises:
      MQTTRecorderError: If recording fails
    """
    if interval <= 0:
      raise MQTTRecorderError("Recording interval must be positive")

    logger.info(f"Starting MQTT recording: topic={self.topic}, broker={self.broker}, interval={interval}s")

    try:
      # Get authentication credentials
      user, password = self._read_auth_credentials()
      auth_string = f'{user}:{password}'

      # Initialize MQTT client
      self.client = PubSub(auth_string, None, self.rootca_file, self.broker)
      self.client.onConnect = self._on_connect
      self.client.onMessage = self._on_message

      # Connect to broker
      logger.info(f"Connecting to MQTT broker: {self.broker}")
      self.client.connect()

      # Start recording with output file context
      with self._output_file_context(output_path):
        self.client.loopStart()

        try:
          time.sleep(interval)
        finally:
          self.client.loopStop()

      logger.info(f"Recording completed. Captured {self.message_count} messages")
      return self.message_count

    except Exception as e:
      if isinstance(e, MQTTRecorderError):
        raise
      raise MQTTRecorderError(f"Recording failed: {e}") from e
    finally:
      if self.client:
        try:
          self.client.disconnect()
        except Exception as e:
          logger.warning(f"Error disconnecting from MQTT broker: {e}")


def build_argparser() -> ArgumentParser:
  """Build command line argument parser"""
  parser = ArgumentParser(
    description="Record MQTT messages from a specified topic"
  )
  parser.add_argument(
    "--broker",
    required=True,
    help="MQTT broker address (required)"
  )
  parser.add_argument(
    "--topic",
    required=True,
    help="MQTT topic to subscribe to (required)"
  )
  parser.add_argument(
    "--interval",
    type=int,
    default=5,
    help="Number of seconds to wait for messages (default: 5)"
  )
  parser.add_argument(
    "--output",
    help="Location to save captured MQTT messages (optional)"
  )
  parser.add_argument(
    "--auth-file",
    default=MQTT_DEFAULT_AUTH,
    help=f"Path to authentication file (default: {MQTT_DEFAULT_AUTH})"
  )
  parser.add_argument(
    "--rootca-file",
    default=MQTT_DEFAULT_ROOTCA,
    help=f"Path to root CA certificate file (default: {MQTT_DEFAULT_ROOTCA})"
  )
  parser.add_argument(
    "--verbose", "-v",
    action="store_true",
    help="Enable verbose logging"
  )
  return parser


def main() -> int:
  """Main entry point for the MQTT recorder"""
  try:
    args = build_argparser().parse_args()

    # Configure logging level
    if args.verbose:
      logging.getLogger().setLevel(logging.DEBUG)

    # Create and run recorder
    recorder = MQTTRecorder(
      broker=args.broker,
      topic=args.topic,
      auth_file=args.auth_file,
      rootca_file=args.rootca_file
    )

    message_count = recorder.record(args.interval, args.output)
    logger.info(f"Successfully recorded {message_count} messages")
    return 0

  except MQTTRecorderError as e:
    logger.error(f"MQTT Recorder Error: {e}")
    return 1
  except KeyboardInterrupt:
    logger.info("Recording interrupted by user")
    return 130
  except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return 1


if __name__ == '__main__':
  sys.exit(main())
