# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
import base64
import requests
import os
import threading
from typing import Dict
from django.core.files.base import ContentFile
import paho.mqtt.client as mqtt

from scene_common.mqtt import PubSub
from scene_common import log

class CameraImageCollector:
    """Collects calibration images from all cameras in a scene."""

    def __init__(self):
        self.collected_images = {}
        self.image_condition = threading.Condition()
        self.max_wait_time = 30  # seconds

    def collect_images_for_scene(self, scene, mqtt_client):
        """
        Collect calibration images from all cameras attached to the scene.

        Args:
            scene: Scene object containing cameras
            mqtt_client: MQTT client for communication

        Returns:
            dict: Dictionary mapping camera_id to base64 image data
        """
        # Get all cameras for this scene
        cameras = scene.sensor_set.filter(type='camera')

        if not cameras.exists():
            raise ValueError("No cameras found in scene")

        log.info(f"Found {cameras.count()} cameras in scene {scene.name}")

        # Reset collected images
        self.collected_images = {}

        # Subscribe to image calibration topics for all cameras
        for camera in cameras:
            topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera.sensor_id)
            mqtt_client.addCallback(topic, self._on_calibration_image_received)
            log.info(f"Subscribed to calibration images for camera {camera.sensor_id}")

        # Send getcalibrationimage command to all cameras
        for camera in cameras:
            cmd_topic = PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id=camera.sensor_id)
            msg = mqtt_client.publish(cmd_topic, "getcalibrationimage", qos=2)
            log.info(f"Sent getcalibrationimage command to camera {camera.sensor_id}")
            if not msg.is_published() and msg.rc == mqtt.MQTT_ERR_SUCCESS:
              mqtt_client.loopStart()
              msg.wait_for_publish()
              mqtt_client.loopStop()

        # Wait for images to be collected
        self.image_condition.acquire()
        try:
            start_time = time.time()
            while len(self.collected_images) < cameras.count():
                elapsed = time.time() - start_time
                remaining_time = self.max_wait_time - elapsed

                if remaining_time <= 0:
                    break

                self.image_condition.wait(timeout=remaining_time)

        finally:
            self.image_condition.release()

        # Unsubscribe from topics
        for camera in cameras:
            topic = PubSub.formatTopic(PubSub.IMAGE_CALIBRATE, camera_id=camera.sensor_id)
            mqtt_client.removeCallback(topic)

        if len(self.collected_images) < cameras.count():
            missing_cameras = [cam.sensor_id for cam in cameras if cam.sensor_id not in self.collected_images]
            raise ValueError(f"Failed to collect images from cameras: {missing_cameras}")

        log.info(f"Successfully collected images from {len(self.collected_images)} cameras")
        return self.collected_images

    def _on_calibration_image_received(self, client, userdata, message):
        """MQTT callback for receiving calibration images."""
        try:
            msg_data = json.loads(message.payload.decode("utf-8"))
            topic = PubSub.parseTopic(message.topic)
            camera_id = topic['camera_id']

            if 'image' in msg_data:
                self.image_condition.acquire()
                try:
                    self.collected_images[camera_id] = {
                        'data': msg_data['image'],
                        'timestamp': msg_data.get('timestamp', ''),
                        'filename': f"{camera_id}_calibration.jpg"
                    }
                    log.info(f"Received calibration image from camera {camera_id}")
                    self.image_condition.notify()
                finally:
                    self.image_condition.release()
            else:
                log.warning(f"No image data in calibration message from camera {camera_id}")

        except Exception as e:
            log.error(f"Error processing calibration image: {e}")


class MappingServiceClient:
    """Client for interacting with the mapping service API."""

    def __init__(self):
        # Get mapping service URL from environment or use default
        self.base_url = os.environ.get('MAPPING_SERVICE_URL', 'http://mapping.scenescape.intel.com:8000')
        self.timeout = 300  # 5 minutes timeout for mesh generation

    def reconstruct_mesh(self, images: Dict[str, Dict], model_type='mapanything', mesh_type='mesh'):
        """
        Call mapping service to reconstruct 3D mesh from images.

        Args:
            images: Dictionary of camera images with base64 data
            model_type: Model to use ('mapanything' or 'vggt')
            mesh_type: Output type ('mesh' or 'pointcloud')

        Returns:
            dict: Response from mapping service
        """
        # Prepare request data
        image_list = []
        for camera_id, image_data in images.items():
            image_list.append({
                'data': image_data['data'],
                'filename': image_data['filename']
            })

        request_data = {
            'model_type': model_type,
            'output_format': 'glb',
            'mesh_type': mesh_type,
            'images': image_list
        }

        log.info(f"Sending {len(image_list)} images to mapping service for reconstruction")

        try:
            response = requests.post(
                f"{self.base_url}/reconstruct",
                json=request_data,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                result = response.json()
                log.info(f"Mapping service completed successfully in {result.get('processing_time', 0):.2f}s")
                return result
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error', f'HTTP {response.status_code}')
                log.error(f"Mapping service error: {error_msg}")
                raise Exception(f"Mapping service error: {error_msg}")

        except requests.exceptions.Timeout:
            raise Exception("Mapping service request timed out")
        except requests.exceptions.ConnectionError:
            raise Exception("Could not connect to mapping service")
        except Exception as e:
            log.error(f"Mapping service request failed: {e}")
            raise


class MeshGenerator:
    """Main class for generating 3D meshes from scene cameras."""

    def __init__(self):
        self.image_collector = CameraImageCollector()
        self.mapping_client = MappingServiceClient()

    def generate_mesh_from_scene(self, scene, model_type='mapanything', mesh_type='mesh'):
        """
        Generate a 3D mesh from all cameras in a scene.

        Args:
            scene: Scene object
            model_type: Model to use for reconstruction
            mesh_type: Type of mesh output

        Returns:
            dict: Result with success status and details
        """
        start_time = time.time()

        # Initialize MQTT client for camera communication
        broker = os.environ.get("BROKER")
        auth = os.environ.get("BROKERAUTH")
        rootcert = os.environ.get("BROKERROOTCERT")
        if rootcert is None:
          rootcert = "/run/secrets/certs/scenescape-ca.pem"
        cert = os.environ.get("BROKERCERT")
        try:
            log.info(f"Connecting to MQTT broker at {broker}")
            mqtt_client = PubSub(auth, cert, rootcert, broker)
            mqtt_client.connect()

            # Collect images from all cameras in the scene
            log.info(f"Starting mesh generation for scene {scene.name}")
            images = self.image_collector.collect_images_for_scene(scene, mqtt_client)

            log.info(f"Collected {len(images)} images, calling mapping service")
            # Call mapping service to generate mesh
            mapping_result = self.mapping_client.reconstruct_mesh(
                images, model_type, mesh_type
            )

            log.info("Mapping service returned result")

            # Save the generated mesh to the scene
            if mapping_result.get('success') and mapping_result.get('glb_data'):
                self._save_mesh_to_scene(scene, mapping_result['glb_data'])

                processing_time = time.time() - start_time
                log.info(f"Mesh generation completed successfully in {processing_time:.2f}s")

                return {
                    'success': True,
                    'message': f'Successfully generated mesh from {len(images)} cameras',
                    'processing_time': processing_time,
                    'camera_count': len(images)
                }
            else:
                raise Exception("Mapping service did not return GLB data")

        except Exception as e:
            processing_time = time.time() - start_time
            log.error(f"Mesh generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'processing_time': processing_time
            }
        finally:
            # Cleanup MQTT connection
            try:
                mqtt_client.disconnect()
            except:
                pass

    def _save_mesh_to_scene(self, scene, glb_data_base64):
        """
        Save the generated GLB mesh to the scene's map field.

        Args:
            scene: Scene object to update
            glb_data_base64: Base64 encoded GLB file data
        """
        try:
            # Decode base64 GLB data
            glb_bytes = base64.b64decode(glb_data_base64)

            # Generate filename for the mesh
            filename = f"{scene.name}_generated_mesh_{int(time.time())}.glb"

            # Save to scene's map field
            scene.map.save(
                filename,
                ContentFile(glb_bytes),
                save=True
            )

            # Update the map_processed timestamp
            scene.map_processed = time.time()
            scene.save(update_fields=['map_processed'])

            log.info(f"Saved generated mesh to scene {scene.name} as {filename}")

        except Exception as e:
            log.error(f"Failed to save mesh to scene: {e}")
            raise Exception(f"Failed to save mesh file: {e}")