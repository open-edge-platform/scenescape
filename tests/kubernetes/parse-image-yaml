#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2024 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import sys
import yaml

def parseYamlFiles(fileList):
  images = []
  options = []
  for file in fileList:
    with open(file, 'r') as stream:
      try:
        data = yaml.safe_load(stream)
        if 'services' in data:
          for service in data['services']:
            if 'EXAMPLEDB' in data.get('services', {}).get('pgserver', {}).get('environment', {}):
              service += ":EXAMPLEDB"
            else:
              service += ":"
            images.append(service)
      except yaml.YAMLError as exc:
        print(f"Error parsing {file}: {exc}")
  return images

def checkImages(images, validImages):
  imageCount = { image: 0 for image in validImages }
  imageOption = { image: "NOENV" for image in validImages }

  for image in images:
    option = image.split(":")[1]
    image = image.split(":")[0]
    if image in imageCount:
      imageCount[image] += 1
      if option:
        imageOption[image] = option

  result = ' '.join([f"{validImages[image]}:{imageOption[image]}={count}" for image, count in imageCount.items()])

  return result

if __name__ == "__main__":
  if len(sys.argv) != 2:
    print(f"Usage: python {sys.argv[0]} 'file1.yml:file2.yml:file3.yml'")
    sys.exit(1)

  fileList = sys.argv[1].split(':')
  # Make sure that the service names in our docker compose match the Kubernetes deployments
  validImages = {
    'pgserver': 'pgserver',
    'broker': 'broker',
    'web': 'web',
    'ntpserv': 'ntp',
    'scene': 'scene',
    'camcalibration': 'camcalibration'
  }

  images = parseYamlFiles(fileList)
  result = checkImages(images, validImages)
  print(result)
