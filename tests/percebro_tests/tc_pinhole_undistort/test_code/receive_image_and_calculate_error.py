#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import argparse
import base64
import cv2
import json
import numpy as np
import os
import sys
import time

from scene_common.mqtt import PubSub

parser = argparse.ArgumentParser()

# Test parameters
parser.add_argument("--original_image_file", type=str, help="Original image directory", required=True)
parser.add_argument("--output_image_file", type=str, help="Output image directory", required=True)
parser.add_argument("--output_json_file", type=str, help="Output json directory", required=True)
parser.add_argument("--camera_name", type=str, help="Camera name", required=True)

# MQTT parameters
parser.add_argument("--broker_url", type=str, help="Broker host", default="broker.scenescape.intel.com")
parser.add_argument("--broker_port", type=int, help="Broker port", default=1883)
parser.add_argument("--auth", type=str, help="Auth", default="/run/secrets/percebro.auth")
parser.add_argument("--rootcert", type=str, help="Rootcert", default="/run/secrets/certs/scenescape-ca.pem")
parser.add_argument("--connection_timeout", type=int, help="Connection timeout", default=60)
parser.add_argument("--recieve_image_soft_timeout", type=int, help="Recieve image soft timeout", default=10)
parser.add_argument("--recieve_image_hard_timeout", type=int, help="Recieve image hard timeout", default=60)

IMAGE_RECIEVED = False
OUTPUT_IMAGE_FILE = None

def json2im(jstr):
  image_array = np.frombuffer(base64.b64decode(jstr), dtype=np.uint8)
  image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
  return image

def findCheckerboardCorners(image):
  criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
  gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

  # Find chessboard corners
  ret, corners = cv2.findChessboardCorners(gray, (10, 7), None)

  # If corners are found, add object points and image points
  if ret == True:
    corners2 = cv2.cornerSubPix(gray,corners, (11,11), (-1,-1), criteria)
    return corners2
  return corners

def calculate_reprojection_error(corners, corners2):
  error = cv2.norm(corners, corners2, cv2.NORM_L2)/len(corners)
  return error

def calculateMse(img1, img2):
  mat1 = np.array(img1)
  mat2 = np.array(img2)
  dmat = mat1 - mat2
  smat = np.square(dmat)
  mse = np.mean(smat)
  return mse

def sendImageCMD(client, camera_name):
  client.publish(PubSub.formatTopic(PubSub.CMD_CAMERA, camera_id = camera_name), "sendImage")

def onConnect(client, userdata, flags, rc):
  print("connected to broker...")

def compareImage(original_image, output_image):
  mean_square_error = calculateMse(original_image, output_image)

  original_corners = findCheckerboardCorners(original_image)
  output_corners = findCheckerboardCorners(output_image)

  if original_corners is not None and output_corners is not None:
    reprojection_error = calculate_reprojection_error(original_corners, output_corners)
    return mean_square_error, reprojection_error
  else:
    return mean_square_error, None

def onMessage(client, userdata, message):
  global IMAGE_RECIEVED
  global OUTPUT_IMAGE_FILE
  msg = json.loads(str(message.payload.decode('utf-8')))
  topic = str(message.topic)

  print(topic)

  topic_type = topic.split('/')[0:-1]
  if (topic_type == ['scenescape', 'image', 'camera']):
    camera_name = topic.split('/')[-1]
    recieved_image = json2im(msg['image'])
    # Save the recieved image
    cv2.imwrite(OUTPUT_IMAGE_FILE, recieved_image)
    IMAGE_RECIEVED = True

def startClient(params, camera_name):
  client = PubSub(params['auth'], None, params['rootcert'],params['broker_url'], params['broker_port'])
  client.onMessage = onMessage
  client.onConnect = onConnect

  client.connect()
  print("connecting to broker... ")

  subscription = 'scenescape/image/camera/' + camera_name

  client.subscribe(subscription)

  client.loopStart()
  return client

def main(args):
  global OUTPUT_IMAGE_FILE

  OUTPUT_IMAGE_FILE = args.output_image_file

  # Check if original image file exists
  if not os.path.exists(args.original_image_file):
    print("Original image file does not exist")
    sys.exit(1)

  # Check if output_json_file exists
  if not os.path.exists(args.output_json_file):
    print("Output json file does not exist")
    sys.exit(1)

  param = {
    'auth': args.auth,
    'rootcert': args.rootcert,
    'broker_url': args.broker_url,
    'broker_port': args.broker_port
  }

  # Start time
  start_time = time.time()

  # Start the MQTT client
  print("Starting MQTT client...")
  client = startClient(param, args.camera_name)

  while True:
    current_time = time.time()
    if (client.isConnected == False):
      if(current_time - start_time > args.connection_timeout):
        print("Connection timeout")
        break
    else:
      if(IMAGE_RECIEVED == False):
        if(current_time - start_time > args.recieve_image_soft_timeout and current_time - start_time < args.recieve_image_hard_timeout):
          print("Image not recieved within soft time out, sending image command")
          sendImageCMD(client, args.camera_name)
          time.sleep(1)
        elif(current_time - start_time > args.recieve_image_hard_timeout):
          with open(args.output_json_file, 'a') as f:
            json.dump({"input_image": args.camera_name, "image_recieved": "false"}, f)
            f.write("\n")
          print("Image not recieved within hard timeout, exiting...")
          break

      else:
        original_image = cv2.imread(args.original_image_file)
        output_image = cv2.imread(args.output_image_file)

        mean_square_error, reprojection_error = compareImage(original_image, output_image)

        with open(args.output_json_file, 'a') as f:
          if reprojection_error is None:
            json.dump({"input_image": args.camera_name, "image_recieved": "true", "mean_square_error": mean_square_error}, f)
            f.write("\n")
          else:
            json.dump({"input_image": args.camera_name, "image_recieved": "true", "mean_square_error": mean_square_error, "reprojection_error": reprojection_error}, f)
            f.write("\n")
        print("Image recieved and compared successfully")
        break

  # Disconnect the MQTT client
  print("Disconnecting from broker...")
  client.disconnect()
  client.loopStop()
  return

if __name__ == "__main__":
  args = parser.parse_args()
  main(args)
