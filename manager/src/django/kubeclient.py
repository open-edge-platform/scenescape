# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pprint
import hashlib
import re

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from scene_common import log
from scene_common.mqtt import PubSub
from scene_common.rest_client import RESTClient

class KubeClient():
  topics_to_subscribe = []

  def __init__(self, broker, mqttAuth, mqttCert, mqttRootCert, restURL):
    self.ns = os.environ.get('KUBERNETES_NAMESPACE')
    self.release = os.environ.get('HELM_RELEASE')
    self.repo = os.environ.get('HELM_REPO')
    self.image = os.environ.get('HELM_IMAGE')
    self.tag = os.environ.get('HELM_TAG')
    # Get pull secrets
    self.pull_secrets = []
    i = 0
    while True:
      secret = os.environ.get(f'KUBERNETES_PULL_SECRET_{i}')
      if secret is None:
        break
      # prevent infinite loop
      elif i == 16:
        break
      self.pull_secrets.append(secret)
      i += 1

    kubeclient_topic = PubSub.formatTopic(PubSub.CMD_KUBECLIENT)
    self.topics_to_subscribe.append((kubeclient_topic, self.cameraUpdate))

    self.client = PubSub(mqttAuth, mqttCert, mqttRootCert, broker, keepalive=240)
    self.client.onConnect = self.mqttOnConnect
    self.client.connect()

    self.restURL = restURL
    self.restAuth = mqttAuth
    self.rest = RESTClient(restURL, rootcert=mqttRootCert, auth=self.restAuth)

  def mqttOnConnect(self, client, userdata, flags, rc):
    """! Subscribes to a list of topics on MQTT.
    @param   client    Client instance for this callback.
    @param   userdata  Private user data as set in Client.
    @param   flags     Response flags sent by the broker.
    @param   rc        Connection result.

    @return  None
    """
    for topic, callback in self.topics_to_subscribe:
      log.info("Subscribing to" + topic)
      self.client.addCallback(topic, callback)
      log.info("Subscribed" + topic)
    return

  def cameraUpdate(self, client, userdata, message):
    """! MQTT callback function which calls save or delete functions depending
    on the message action received.
    @param   client      MQTT client.
    @param   userdata    Private user data as set in Client.
    @param   message     Message on MQTT bus.

    @return  None
    """
    msg = json.loads(message.payload)
    log.info("Kubeclient received: " + pprint.pformat(msg))
    if msg['action'] == 'save':
      res = self.save(msg)
    elif msg['action'] == 'delete':
      res = self.delete(self.objectName(msg))
    if res:
      log.error("Kubeclient action success.")
    else:
      log.error("Kubeclient action failure.")
    return

  def save(self, msg):
    """! Function to save a deployment
    @param   msg            dictionary containing relevant video deployment details
                            sent over MQTT

    @return  boolean        status of the operation
    """
    deployment_name = self.objectName(msg)
    previous_deployment_name = self.objectName(msg, previous=True)
    pipelineConfig = self.generatePipelineConfiguration(msg, {})
    deployment_name = self.objectName(msg)
    container_name = self.objectName(msg, container=True)
    sensor_id = msg['sensor_id']
    deployment_body = self.generateDeploymentBody(deployment_name, container_name, sensor_id, pipelineConfig)
    try:
      existing_deployment = self.read(deployment_name)
      log.info("Deployment exists. Checking for changes...")
      if not existing_deployment:
        raise ApiException(status=404)
      if existing_deployment['args'] != args:
        log.info("Parameters have changed. Updating the deployment...")
        self.api_instance.patch_namespaced_deployment(name=deployment_name,
                                                      namespace=self.ns, body=deployment_body)
      else:
        log.info("No changes in parameters. No update required.")
    except ApiException as e:
      if e.status == 404:
        if previous_deployment_name != deployment_name:
          log.info("Name changed. Deleting previous deployment...")
          self.delete(previous_deployment_name)
        log.info("Deployment does not exist. Creating new deployment...")
        self.api_instance.create_namespaced_deployment(namespace=self.ns, body=deployment_body)
        log.info("Deployment created.")
      else:
        log.error(f"Exception: {e}")
        return False
    return True

  def read(self, deployment_name):
    """! Function to read a deployment
    @param   deployment_name   deployment name

    @return  deployment        relevant deployment details as a dict
    """
    try:
      api_response = self.api_instance.read_namespaced_deployment(deployment_name, self.ns)
      deployment = {
        'name': api_response.metadata.name,
        'args': api_response.spec.template.spec.containers[0].args
      }
      return deployment
    except ApiException as e:
      if e.status == 404:
        log.error("Deployment not found.")
      else:
        log.error(f"Exception: {e}")
      return None

  def delete(self, deployment_name):
    """! Function to delete a deployment
    @param   deployment_name   deployment name

    @return  boolean           status of the operation
    """
    log.info(f"Deleting {deployment_name}")
    try:
      if self.read(deployment_name):
        self.api_instance.delete_namespaced_deployment(name=deployment_name, namespace=self.ns)
      return True
    except ApiException as e:
      log.error(f"Exception: {e}")
      return False

  def handleIntrinsics(self, msg):
    """! Function to handle intrinsics/fov differences from the database preload
    @param   msg               input MQTT message

    @return  intrinsics        intrinsics as a json string
    """
    if 'intrinsics' in msg:
      intrinsics = msg['intrinsics']
    else:
      if not (msg['intrinsics_fy'] and msg['intrinsics_cx'] and msg['intrinsics_cy']):
        if not msg['intrinsics_fx']:
          msg['intrinsics_fx'] = 70
        intrinsics = {"fov": msg['intrinsics_fx']}
      else:
        intrinsics = {
          "fx": msg['intrinsics_fx'],
          "fy": msg['intrinsics_fy'],
          "cx": msg['intrinsics_cx'],
          "cy": msg['intrinsics_cy']
        }
    return json.dumps(intrinsics)

  def generateDeploymentBody(self, deployment_name, container_name, sensor_id, pipelineConfig):
    """! Function to generate the deployment body (configuration) for a camera
    with parameters as an input
    @param   deployment_name   deployment name
    @param   container_name    container name
    @param   sensor_id         sensor id
    @param   pipelineConfig    pipeline configuration as a json string

    @return  body              deployment body
    """

    pipelineConfigMapName = self.createPipelineConfigmap(pipelineConfig)
    # TODO: remove this and use the return value of createPipelineConfigmap when implemented
    if "atag" in deployment_name:
      pipelineConfigMapName=f"{self.release}-queuing-video-config"
    else :
      pipelineConfigMapName=f"{self.release}-retail-video-config"

    # volume mounts and volumes for the container
    volume_mounts = [
      client.V1VolumeMount(name="video-config", mount_path="/home/pipeline-server/config.json", sub_path="config.yaml"),
      client.V1VolumeMount(name="sscape-adapter", mount_path="/home/pipeline-server/user_scripts/gvapython/sscape"),
      client.V1VolumeMount(name="model-proc", mount_path="/tmp/person-detection-retail-0013.json", sub_path="person-detection-retail-0013.json"),
      client.V1VolumeMount(name="models-storage", mount_path="/home/pipeline-server/models", sub_path="models"),
      client.V1VolumeMount(name="sample-data", mount_path="/home/pipeline-server/videos", sub_path="sample_data"),
      client.V1VolumeMount(name="pipeline-root", mount_path="/var/cache/pipeline_root"),
      client.V1VolumeMount(name="root-cert", mount_path="/run/secrets/certs/scenescape-ca.pem", sub_path="scenescape-ca.pem"),
    ]

    volumes = [
      client.V1Volume(name="video-config", config_map=client.V1ConfigMapVolumeSource(name=pipelineConfigMapName)),
      client.V1Volume(name="sscape-adapter", config_map=client.V1ConfigMapVolumeSource(name=f"{self.release}-sscape-adapter")),
      client.V1Volume(name="models-storage", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=f"{self.release}-models-pvc")),
      client.V1Volume(name="sample-data", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=f"{self.release}-sample-data-pvc")),
      client.V1Volume(name="pipeline-root", empty_dir=client.V1EmptyDirVolumeSource()),
      client.V1Volume(name="root-cert", secret=client.V1SecretVolumeSource(secret_name=f"{self.release}-scenescape-ca.pem")),
      client.V1Volume(name="model-proc", config_map=client.V1ConfigMapVolumeSource(name=f"{self.release}-model-proc")),
    ]

    # environment variables for the container
    env = [
      client.V1EnvVar(name="RUN_MODE", value="EVA"),
      client.V1EnvVar(name="DETECTION_DEVICE", value="CPU"),
      client.V1EnvVar(name="CLASSIFICATION_DEVICE", value="CPU"),
      client.V1EnvVar(name="ENABLE_RTSP", value="true"),
      client.V1EnvVar(name="RTSP_PORT", value="8554"),
      client.V1EnvVar(name="REST_SERVER_PORT", value="8080"),
      client.V1EnvVar(name="GENICAM", value="Balluff"),
      client.V1EnvVar(name="GST_DEBUG", value="1,gencamsrc:2"),
      client.V1EnvVar(name="ADD_UTCTIME_TO_METADATA", value="true"),
      client.V1EnvVar(name="APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC", value="false"),
      client.V1EnvVar(name="MQTT_HOST", value="broker." + self.ns + ".svc.cluster.local"),
      client.V1EnvVar(name="MQTT_PORT", value="1883"),
    ]

    # ports
    ports = [client.V1ContainerPort(container_port=8554, name="rtsp"),
             client.V1ContainerPort(container_port=8080, name="rest-api")]

    # command && args
    command = ["/bin/bash", "-c"]
    args = [
        "mkdir -p /home/pipeline-server/models/object_detection/person && "
        "cp /tmp/person-detection-retail-0013.json /home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json && "
        "touch /tmp/healthy && "
        "runuser -u intelmicroserviceuser ./run.sh"
    ]

    # container configuration
    container = client.V1Container(
        name=container_name,
        image=f"{self.repo}/{self.image}:{self.tag}",
        tty=True,
        security_context=client.V1SecurityContext(privileged=True, run_as_user=0, run_as_group=0),
        command=command,
        args=args,
        env=env,
        ports=ports,
        image_pull_policy="Always",
        readiness_probe=client.V1Probe(_exec=client.V1ExecAction(
            command=["cat", "/tmp/healthy"]
        ), period_seconds=1),
        volume_mounts=volume_mounts
    )
    # deployment configuration
    deployment_spec = client.V1DeploymentSpec(
      replicas=1,
      selector={'matchLabels': {'app': container_name[:63]}},
      template=client.V1PodTemplateSpec(
        metadata={'labels': {'app': container_name[:63], 'release': self.release, 'sensor-id-hash': sensor_id}},
        spec=client.V1PodSpec(
          share_process_namespace=True,
          containers=[container],
          image_pull_secrets=[client.V1LocalObjectReference(name=secret) for secret in self.pull_secrets],
          restart_policy="Always",
          volumes=volumes
        )
      )
    )
    deployment = client.V1Deployment(
      api_version="apps/v1",
      kind="Deployment",
      metadata=client.V1ObjectMeta(
        name=deployment_name,
        labels={'app': container_name[:63], 'release': self.release, 'sensor-id-hash': self.hash(sensor_id)},
      ),
      spec=deployment_spec
    )
    return deployment

  def objectName(self, msg, previous=False, container=False):
    """! Function to return deployment/container object name based on MQTT message
    Returns deployment by default
    @param   msg               input MQTT message
    @param   previous          flag to use previous name and sensor_id
    @param   container         flag to output container name instead

    @return  output_string     output deployment/container name
    """
    deployment = "-dep"
    release = self.release
    if previous:
      name = msg['previous_name']
      sensor_id = msg['previous_sensor_id']
    else:
      name = msg['name']
      sensor_id = msg['sensor_id']
    if container:
      deployment = ""
      release = self.release[:16]
    output_string = f"{release}-{self.k8sName(name)}-{self.k8sName(sensor_id)}-{self.hash(sensor_id, 8)}-video{deployment}"
    return output_string

  def hash(self, input, truncate=None):
    """! Function to generate a SHA1 hash of a string, optional truncation
    @param   input             input string
    @param   deployment_name   deployment name

    @return  hash_string       SHA1 hash
    """
    hash = hashlib.sha1(usedforsecurity=False)
    hash.update(str(input).encode('utf-8'))
    hash_string = hash.hexdigest()
    if truncate is not None and isinstance(truncate, int) and truncate > 0:
      return hash_string[:truncate]
    return hash_string

  def k8sName(self, input):
    """! Function to only allow lowercase alphanumeric characters and hyphens in a string
         truncated to 16 characters
    @param   input             input string

    @return  output            SHA1 hash
    """
    input = input.lower()
    input = input.replace(' ', '-')
    input = re.sub(r'[^a-z0-9-]', '', input)
    output = input[:16]
    return output

  def apiAdapter(self, camera):
    """! Function to modify response from REST API to be compatible with
         the MQTT message

    @return  None
    """
    camera['sensor_id'] = camera['uid']
    camera_data = {
      'previous_sensor_id': "",
      'previous_name': "",
      'action': "save"
    }
    camera_data.update(camera)
    return camera_data

  def initializeCameras(self):
    """! Function to start camera containers after web server is ready

    @return  None
    """
    results = self.rest.getCameras({})
    for camera in results['results']:
      log.info(f"Saving camera {camera['name']}")
      res = self.save(self.apiAdapter(camera))
      if res:
        log.error("Kubeclient action success.")
      else:
        log.error("Kubeclient action failure.")
    return

  def setup(self):
    """! Function to set up the Kubernetes API client

    @return  None
    """
    config.load_incluster_config()
    self.api_instance = client.AppsV1Api()
    self.initializeCameras()

  def loopForever(self):
    return self.client.loopForever()

  # TODO: implement this function to generate the pipeline configuration based on msg and models_config
  # for now, it returns dummy configuration
  def generatePipelineConfiguration(self, msg, models_config):
    """! Function to save a deployment
    @param   msg            dictionary containing relevant video deployment details
                            sent over MQTT
    @param   models_config  dictionary containing model configuration details
    @return  string         returns the pipeline json as a string
    """
    return """
{
  "config": {
    "logging": {
      "C_LOG_LEVEL": "INFO",
      "PY_LOG_LEVEL": "INFO"
    },
    "pipelines": [
      {
        "name": "qcam1",
        "source": "gstreamer",
        "pipeline": "rtspsrc location=rtsp://mediaserver:8554/queuing-cam1 latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
        "auto_start": true,
        "parameters": {
          "type": "object",
          "properties": {
            "camera_config": {
              "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "cameraid": {
                  "type": "string"
                },
                "metadatagenpolicy": {
                  "type": "string",
                  "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                  "type": "boolean",
                  "description": "Publish frame to mqtt"
                }
              }
            }
          }
        },
        "payload": {
          "parameters": {
            "camera_config": {
              "cameraid": "atag-qcam1",
              "metadatagenpolicy": "detectionPolicy"
            }
          }
        }
      }
    ]
  }
}
"""

  # TODO: implement this function to create a configmap for the pipeline configuration
  # and return the name of the configmap
  def createPipelineConfigmap(self, pipelineConfig):
    """! Function to create a configmap for the pipeline configuration
    @param   pipelineConfig  json string containing the pipeline configuration
    @return  string         returns the name of the configmap
    """
    return "queuing-video-config"
  


QUEUEING_CONFIG = """
{
  "config": {
    "logging": {
      "C_LOG_LEVEL": "INFO",
      "PY_LOG_LEVEL": "INFO"
    },
    "pipelines": [
      {
        "name": "qcam1",
        "source": "gstreamer",
        "pipeline": "rtspsrc location=rtsp://mediaserver:8554/queuing-cam1 latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
        "auto_start": true,
        "parameters": {
          "type": "object",
          "properties": {
            "ntp_config": {
              "element": {
                "name": "timesync",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "ntpServer": {
                  "type": "string"
                }
              }
            },
            "camera_config": {
              "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "cameraid": {
                  "type": "string"
                },
                "metadatagenpolicy": {
                  "type": "string",
                  "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                  "type": "boolean",
                  "description": "Publish frame to mqtt"
                }
              }
            }
          }
        },
        "payload": {
          "parameters": {
            "ntp_config": {
              "ntpServer": "ntpserv"
            },
            "camera_config": {
              "cameraid": "atag-qcam1",
              "metadatagenpolicy": "detectionPolicy"
            }
          }
        }
      },
      {
        "name": "qcam2",
        "source": "gstreamer",
        "pipeline": "rtspsrc location=rtsp://mediaserver:8554/queuing-cam2 latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
        "auto_start": true,
        "parameters": {
          "type": "object",
          "properties": {
            "ntp_config": {
              "element": {
                "name": "timesync",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "ntpServer": {
                  "type": "string"
                }
              }
            },
            "camera_config": {
              "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "cameraid": {
                  "type": "string"
                },
                "metadatagenpolicy": {
                  "type": "string",
                  "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                  "type": "boolean",
                  "description": "Publish frame to mqtt"
                }
              }
            }
          }
        },
        "payload": {
          "parameters": {
            "ntp_config": {
              "ntpServer": "ntpserv"
            },
            "camera_config": {
              "cameraid": "atag-qcam2",
              "metadatagenpolicy": "detectionPolicy"
            }
          }
        }
      }
    ]
  }
}
"""

RETAIL_CONFIG = """
{
  "config": {
    "logging": {
      "C_LOG_LEVEL": "INFO",
      "PY_LOG_LEVEL": "INFO"
    },
    "pipelines": [
      {
        "name": "apriltag-cam1",
        "source": "gstreamer",
        "pipeline": "rtspsrc location=rtsp://mediaserver:8554/retail-cam1 latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
        "auto_start": true,
        "parameters": {
          "type": "object",
          "properties": {
            "camera_config": {
              "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "cameraid": {
                  "type": "string"
                },
                "metadatagenpolicy": {
                  "type": "string",
                  "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                  "type": "boolean",
                  "description": "Publish frame to mqtt"
                }
              }
            }
          }
        },
        "payload": {
          "parameters": {
            "camera_config": {
              "cameraid": "camera1",
              "metadatagenpolicy": "detectionPolicy"
            }
          }
        }
      },
      {
        "name": "apriltag-cam2",
        "source": "gstreamer",
        "pipeline": "rtspsrc location=rtsp://mediaserver:8554/retail-cam2 latency=200 ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! gvapython class=PostDecodeTimestampCapture function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=timesync ! gvadetect model=/home/pipeline-server/models/intel/person-detection-retail-0013/FP32/person-detection-retail-0013.xml model-proc=/home/pipeline-server/models/object_detection/person/person-detection-retail-0013.json ! gvametaconvert add-tensor-data=true name=metaconvert ! gvapython class=PostInferenceDataPublish function=processFrame module=/home/pipeline-server/user_scripts/gvapython/sscape/sscape_adapter.py name=datapublisher ! gvametapublish name=destination ! appsink sync=true",
        "auto_start": true,
        "parameters": {
          "type": "object",
          "properties": {
            "camera_config": {
              "element": {
                "name": "datapublisher",
                "property": "kwarg",
                "format": "json"
              },
              "type": "object",
              "properties": {
                "cameraid": {
                  "type": "string"
                },
                "metadatagenpolicy": {
                  "type": "string",
                  "description": "Meta data generation policy, one of detectionPolicy(default),reidPolicy,classificationPolicy"
                },
                "publish_frame": {
                  "type": "boolean",
                  "description": "Publish frame to mqtt"
                }
              }
            }
          }
        },
        "payload": {
          "parameters": {
            "camera_config": {
              "cameraid": "camera2",
              "metadatagenpolicy": "detectionPolicy"
            }
          }
        }
      }
    ]
  }
}
"""