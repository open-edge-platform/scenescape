# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pprint
import hashlib
import re

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from manager.ppl_generator import PipelineConfigGenerator

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
    log.info(f"Saving camera {msg['name']}")
    # validate input
    if not (msg['name']):
      log.error("No name provided in the message. Cannot create deployment.")
      return False

    deployment_name = self.objectName(msg)
    container_name = self.objectName(msg, container=True)
    sensor_id = msg['sensor_id']
    previous_deployment_name = self.objectName(msg, previous=True)
    if not (previous_deployment_name):
      log.warn("No previous deployment name provided in the message. Assuming this is a new camera.")

    # create the configmap
    pipelineConfig = self.generatePipelineConfiguration(msg)
    log.info(f"Creating ConfigMap for deployment {msg['name']}...")
    try:
      pipelineConfigMapName = self.createPipelineConfigmap(deployment_name, pipelineConfig)
    except ValueError as e:
      log.error(f"Failed to create ConfigMap: {e}")
      return False

    # delete existing deployment if it exists to simplify update logic, patching is more error-prone, so we always delete + create
    try:
      if self.api_instance.read_namespaced_deployment(deployment_name, self.ns):
        log.info(f"Deployment {deployment_name} exists. Deleting it so we can recreate...")
        self.api_instance.delete_namespaced_deployment(name=deployment_name, namespace=self.ns)
    except ApiException as e:
      if e.status != 404:
        log.warn(f"Exception when checking/deleting existing deployment: {e}")

    # delete previous deployment if it exists
    try:
      if previous_deployment_name and previous_deployment_name != deployment_name:
        if self.api_instance.read_namespaced_deployment(previous_deployment_name, self.ns):
          log.info(f"Deployment {previous_deployment_name} exists. Deleting it...")
          self.api_instance.delete_namespaced_deployment(name=previous_deployment_name, namespace=self.ns)
    except ApiException as e:
      if e.status != 404:
        log.warn(f"Exception when checking/deleting previous deployment: {e}")

    # create the deployment
    log.info(f"Creating deployment {deployment_name}...")
    deployment_body = self.generateDeploymentBody(deployment_name, container_name, sensor_id, pipelineConfigMapName)
    try:
      self.api_instance.create_namespaced_deployment(namespace=self.ns, body=deployment_body)
      log.info(f"Deployment {deployment_name} created.")
    except ApiException as e:
      log.error(f"Exception when creating deployment: {e}")
      return False

    return True

  def delete(self, deployment_name):
    """! Function to delete a deployment
    @param   deployment_name   deployment name

    @return  boolean           status of the operation
    """
    log.info(f"Deleting {deployment_name}")
    try:
      if self.api_instance.read_namespaced_deployment(deployment_name, self.ns):
        self.api_instance.delete_namespaced_deployment(name=deployment_name, namespace=self.ns)
    except ApiException as e:
      log.error(f"Exception when deleting deployment: {e}")
      return False

    log.info(f"Deleting configmap associated with {deployment_name}")
    try:
      configmap_name = deployment_name
      self.core_api.delete_namespaced_config_map(name=configmap_name, namespace=self.ns)
    except ApiException as e:
      if e.status != 404:
        log.warn(f"Exception when deleting existing ConfigMap: {e}")
        return False

    return True

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

  def generateDeploymentBody(self, deployment_name, container_name, sensor_id, pipelineConfigMapName):
    """! Function to generate the deployment body (configuration) for a camera
    with parameters as an input
    @param   deployment_name   deployment name
    @param   container_name    container name
    @param   sensor_id         sensor id
    @param   pipelineConfigMapName    pipeline configuration

    @return  body              deployment body
    """
    # volume mounts and volumes for the container
    volume_mounts = [
      client.V1VolumeMount(name="video-config", mount_path="/home/pipeline-server/config.json", sub_path="config.yaml"),
      client.V1VolumeMount(name="sscape-adapter", mount_path="/home/pipeline-server/user_scripts/gvapython/sscape"),
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
#      client.V1EnvVar(name="GST_DEBUG", value="1,gencamsrc:2"),
      client.V1EnvVar(name="GST_DEBUG", value="3"),
      client.V1EnvVar(name="ADD_UTCTIME_TO_METADATA", value="true"),
      client.V1EnvVar(name="APPEND_PIPELINE_NAME_TO_PUBLISHER_TOPIC", value="false"),
      client.V1EnvVar(name="MQTT_HOST", value="broker." + self.ns + ".svc.cluster.local"),
      client.V1EnvVar(name="MQTT_PORT", value="1883"),
    ]

    # ports
    ports = [client.V1ContainerPort(container_port=8554, name="rtsp"),
             client.V1ContainerPort(container_port=8080, name="rest-api")]

    # container configuration
    container = client.V1Container(
        name=container_name,
        image=f"{self.repo}/{self.image}:{self.tag}",
        tty=True,
        security_context=client.V1SecurityContext(privileged=True, run_as_user=0, run_as_group=0),
        env=env,
        ports=ports,
        image_pull_policy="Always",
        readiness_probe=client.V1Probe(_exec=client.V1ExecAction(
            command=["curl", "-I", "-s", "http://localhost:8080/pipelines"]
        ), period_seconds=10, initial_delay_seconds=10, timeout_seconds=5, failure_threshold=5),
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
    deployment = ""
    release = self.release
    if previous:
      name = msg['previous_name']
      if not (name):
        # returning empty string to indicate no previous name (so we can skip previous deployment deletion)
        return ""
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
      log.info(f"Initializing camera {camera['name']}...")
      res = self.save(self.apiAdapter(camera))
      if res:
        log.error(f"Camera {camera['name']} initialized successfully.")
      else:
        log.error(f"Camera {camera['name']} initialization failed.")
    return

  def setup(self):
    """! Function to set up the Kubernetes API client

    @return  None
    """
    config.load_incluster_config()
    self.api_instance = client.AppsV1Api()
    self.core_api = client.CoreV1Api()
    self.initializeCameras()

  def loopForever(self):
    return self.client.loopForever()

  def generatePipelineConfiguration(self, msg):
    """! Function to save a deployment
    @param   msg            dictionary containing relevant video deployment details
                            sent over MQTT
    @return  string         returns the pipeline json as a string
    """
    log.info(f"Generating pipeline configuration for camera: {msg['name']}")
    ppl_config_generator = PipelineConfigGenerator(msg)
    config = ppl_config_generator.get_config_as_json()
    if config is None:
      raise ValueError("Dynamic configuration generation failed.")

    return config

  def createPipelineConfigmap(self, deploymentName, pipelineConfig):
    """! Function to create a configmap for the pipeline configuration
    @param   deploymentName  name of the deployment (used as configmap name)
    @param   pipelineConfig  json string containing the pipeline configuration
    @return  string         returns the name of the configmap
    """
    configMapName = deploymentName

    metadata = client.V1ObjectMeta(name=configMapName)
    data = {"config.yaml": pipelineConfig}
    config_map = client.V1ConfigMap(api_version="v1", kind="ConfigMap", metadata=metadata, data=data)

    # Delete existing ConfigMap if it exists to simplify update logic, patching is more error-prone, so we always delete + create
    try:
      if self.core_api.read_namespaced_config_map(name=configMapName, namespace=self.ns):
        log.info(f"ConfigMap {configMapName} exists. Deleting it so we can recreate...")
        self.core_api.delete_namespaced_config_map(name=configMapName, namespace=self.ns)
    except ApiException as e:
      if e.status != 404:
        log.warn(f"Exception when checking/deleting existing ConfigMap: {e}")

    # create the configmap
    try:
      self.core_api.create_namespaced_config_map(namespace=self.ns, body=config_map)
      log.info(f"ConfigMap {configMapName} created.")
    except ApiException as e:
      raise ValueError(f"Failed to create ConfigMap {configMapName}: {e}")

    return configMapName
