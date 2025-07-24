# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

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
    advanced_args = []
    for item in ['threshold', 'aspect', 'cv_subsystem', 'sensor', 'sensorchain', 'sensorattrib',
                 'virtual', 'frames', 'modelconfig', 'rootcert', 'cert', 'cvcores',
                 'ovcores', 'ovmshost', 'framerate', 'maxcache', 'filter', 'maxdistance']:
      if msg.get(item, "") not in ["", None]:
        advanced_args.append(f"--{item}={msg[item]}")

    for item in ['window', 'usetimestamps', 'debug', 'override_saved_intrinstics', 'stats',
                 'waitforstable', 'preprocess', 'realtime', 'faketime', 'unwarp', 'disable_rotation']:
      if msg.get(item, "") not in ["", None] and msg[item]:
        advanced_args.append(f"--{item}")

    if msg.get('distortion_k1', "") not in ["", None]:
      advanced_args.append(f"--distortion=[{msg['distortion_k1']},{msg['distortion_k2']},{msg['distortion_p1']},{msg['distortion_p2']},{msg['distortion_k3']}]")

    if msg.get('resolution', "") not in ["", None]:
      # Handle the case where Kubernetes is initializing the camera (seed data)
      advanced_args.append(f"--resolution={msg['resolution']}")
    elif msg.get('width', "") not in ["", None] and msg.get('height', "") not in ["", None]:
      # Handle case which user updating the camera
      advanced_args.append(f"--resolution=[{msg['width']}, {msg['height']}]")

    args = [
      "percebro", "--broker", f"broker.{self.ns}",
      f"--camera={msg['command']}", f"--cameraid={msg['sensor_id']}",
      f"--intrinsics={self.handleIntrinsics(msg)}", f"--camerachain={msg['camerachain']}",
      *advanced_args,
      f"--ntp=ntpserv.{self.ns}",
      "--auth=/run/secrets/percebro.auth",
      f"--resturl=web.{self.ns}",
      f"broker.{self.ns}"
    ]
    deployment_body = self.generateDeploymentBody(msg, args)
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

  def generateDeploymentBody(self, msg, args):
    """! Function to generate the deployment body (configuration) for a camera
    with parameters as an input
    @param   msg               input MQTT message
    @param   args              parameter arguments for container

    @return  body              deployment body
    """
    # volume mounts and volumes for the container
    volume_mounts = [
      client.V1VolumeMount(name="certs", mount_path="/run/secrets/certs", read_only=True),
      client.V1VolumeMount(name="percebro-auth", mount_path="/run/secrets/percebro.auth", sub_path="percebro.auth", read_only=True),
      client.V1VolumeMount(name="models-storage", mount_path="/opt/intel/openvino/deployment_tools/intel_models", sub_path="models"),
      client.V1VolumeMount(name="sample-data-storage", mount_path="/home/scenescape/SceneScape/sample_data", sub_path="sample_data"),
      client.V1VolumeMount(name="videos-storage", mount_path="/videos"),
      client.V1VolumeMount(name="dri", mount_path="/dev/dri")
    ]
    volumes = [
      client.V1Volume(name="certs", secret=client.V1SecretVolumeSource(secret_name=f"{self.release}-certs")),
      client.V1Volume(name="percebro-auth", secret=client.V1SecretVolumeSource(secret_name=f"{self.release}-percebro.auth")),
      client.V1Volume(name="models-storage", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=f"{self.release}-models-pvc")),
      client.V1Volume(name="sample-data-storage", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=f"{self.release}-sample-data-pvc")),
      client.V1Volume(name="videos-storage", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=f"{self.release}-videos-pvc")),
      client.V1Volume(name="dri", host_path=client.V1HostPathVolumeSource(path="/dev/dri"))
    ]
    # container configuration
    container_name = self.objectName(msg, container=True)
    container = client.V1Container(
      name=container_name,
      image=f"{self.repo}/{self.image}:{self.tag}",
      args=args,
      image_pull_policy="Always",
      security_context=client.V1SecurityContext(privileged=True),
      readiness_probe=client.V1Probe(_exec=client.V1ExecAction(
        command=["cat", "/tmp/healthy"]
        ),
        period_seconds=1
      ),
      volume_mounts=volume_mounts
    )
    # deployment configuration
    deployment_spec = client.V1DeploymentSpec(
      replicas=1,
      selector={'matchLabels': {'app': container_name[:63]}},
      template=client.V1PodTemplateSpec(
        metadata={'labels': {'app': container_name[:63], 'release': self.release, 'sensor-id-hash': self.hash(msg['sensor_id'])}},
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
        name=self.objectName(msg),
        labels={'app': container_name[:63], 'release': self.release, 'sensor-id-hash': self.hash(msg['sensor_id'])}),
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
