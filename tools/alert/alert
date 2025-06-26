#!/usr/bin/env python3

# SPDX-FileCopyrightText: (C) 2020 - 2025 Intel Corporation
# SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
# This file is licensed under the Limited Edge Software Distribution License Agreement.

import json
import os
from argparse import ArgumentParser

import cv2
from event import Event
from image import Image
from pushover import Pushover
from region import Region

from scene_common import log
from scene_common.geometry import Rectangle
from scene_common.mqtt import PubSub
from scene_common.timestamp import get_epoch_time, get_iso_time

ETOPIC = PubSub.formatTopic(PubSub.EVENT, event_type="count", scene_id="+",
                            region_id="+", region_type="region")
RTOPIC = PubSub.formatTopic(PubSub.DATA_REGION, region_id="+", scene_id="+", thing_type="+")
DEBOUNCE_DELAY = 60
VEHICLE_DELAY = 5

def build_argparser():
  parser = ArgumentParser()
  parser.add_argument("broker", nargs="?", default="localhost",
                      help="hostname or IP of MQTT broker")
  parser.add_argument("--rootcert", default="/run/secrets/certs/scenescape-ca.pem",
                      help="path to ca certificate")
  parser.add_argument("--resturl", default="https://web.scenescape.intel.com/api/v1",
                      help="URL of REST server")
  parser.add_argument("--cert", help="path to client certificate")
  parser.add_argument("--auth", help="user:password or JSON file for MQTT authentication")
  return parser

class Alert:
  def __init__(self, event, priority=None, sound=None, pushover=None):
    self.when = event.when
    self.priority = priority
    self.sound = sound
    self.region = event.region
    self.image = None
    self.pushover = pushover
    return

  def send(self, message):
    self.pushover.send(message, self.sound, self.image, self.priority)
    # FIXME - send email/MMS?
    return

  def __repr__(self):
    return f"Alert: {self.region} {self.sound} {get_iso_time(self.when)}"

class EventHandler:
  def __init__(self, auth, broker, restURL, cert, rootCert):
    self.auth = auth
    self.broker = broker
    self.restURL = restURL
    self.cert = cert
    self.rootCert = rootCert

    self.alerts = {}

    dirpath = os.path.dirname(os.path.realpath(__file__))
    confpath = os.path.join(dirpath, "config.json")
    with open(confpath) as f:
      self.config = json.load(f)

    self.pushover = Pushover(self.config['pushover']['token'], self.config['pushover']['key'])

    return

  def loop(self):
    log.info("Connecting to broker", self.broker)
    client = PubSub(self.auth, self.cert, self.rootCert, self.broker)
    client.onConnect = self.onConnect
    client.connect()
    client.loopForever()
    return

  def onConnect(self, client, userdata, flags, rc):
    log.info("Connected")
    #client.addCallback(ETOPIC, self.eventReceived)
    client.addCallback(RTOPIC, self.regionReceived)
    return

  def publishEvent(self, event):
    now = get_epoch_time()

    pri = event.priority(self.config)
    tone = event.tone(self.config)
    alert = Alert(event, priority=pri, sound=tone, pushover=self.pushover)

    lastAlert = None
    if alert.region in self.alerts:
      lastAlert = self.alerts[alert.region]

    if not lastAlert \
       or now - lastAlert.when > DEBOUNCE_DELAY \
       or (lastAlert.priority is None and alert.priority is not None) \
       or (lastAlert.priority is not None and alert.priority is not None
           and lastAlert.priority < alert.priority):
      log.info("Object types", list(event.counts.keys()))
      log.info("People", event.counts['person'])
      log.info("Vehicles", event.counts['vehicle'])
      log.info("Last", lastAlert)

      vis = set()
      for obj in event.objects:
        if 'visibility' in obj:
          vis.update(obj['visibility'])
      log.info("THE VISION " + str(vis) + "\n")
      if len(vis) == 0:
        #vis = self.config['cameras'].keys()
        return False

      images = []
      for cam in vis:
        # img = Image(self.config['cameras'][cam], cam)
        img = Image(self.restURL, cam, event.timestamp, self.rootCert, self.auth)
        if img is not None and hasattr(img, 'image'):
          img.markObjects(cam, event)
          images.append(img)

      spotted = ""
      log.info(event)
      for otype in event.counts:
        log.info(otype, event.counts[otype])
        if event.counts[otype] > 0:
          if len(spotted):
            spotted += " and "
          spotted += otype
      spotted = alert.region + ": " + spotted

      size = Image.largest(images)
      if size[0] > 1920:
        size[0] = 1920
      if size[1] > 1440:
        size[1] = 1440
      resized = Image.scaleImages(size, images)
      alert.image = cv2.vconcat(resized)
      alert.send(spotted + " spotted!")
      log.info("EVENT", event.region, pri, tone, event.counts)

      self.alerts[alert.region] = alert
    elif lastAlert:
      # Didn't send alert but update the time of the last alert to the
      # most recent event so that alerts aren't constantly being sent
      # until the region is empty again.
      lastAlert.when = alert.when
    return

  def eventReceived(self, client, userdata, message):
    msg = str(message.payload.decode("utf-8"))
    event = Event(json.loads(msg))
    now = get_epoch_time()
    log.info("Event received", msg, event.region,
            event.counts['person'], event.counts['vehicle'])

    if event.counts['person'] > 0 or event.counts['vehicle'] > 0:
      self.publishEvent(event)
    return True

  def regionReceived(self, client, userdata, message):
    topic = PubSub.parseTopic(message.topic)
    rname = topic['region_id']

    msg = str(message.payload.decode("utf-8"))
    region = Region(json.loads(msg), rname)
    #log.debug("Region received", topic, msg)

    valid = False
    people = []
    vehicles = []
    for obj in region.objects:
      otype = obj['type']
      bbMeters = Rectangle(obj['bb_meters'])
      if otype == 'person' and bbMeters.width > 0.2 and bbMeters.height > 0.2:
        people.append(obj)
      elif otype == 'vehicle':
        if bbMeters.width < 5 and bbMeters.height < 3:
          log.info("BBOX SIZE", bbMeters.width, bbMeters.height,
                  bbMeters.width < 5, bbMeters.height < 3)
          vehicles.append(obj)

    if len(region.objects):
      for obj in region.objects:
        if obj['type'] != 'vehicle':
          valid = True
        else:
          for rname in obj['regions']:
            r = obj['regions'][rname]
            tdelta = region.when - r['entered_epoch']
            if tdelta >= VEHICLE_DELAY:
              valid = True
              break
        if valid:
          break

    if valid and (len(people) or len(vehicles)):
      edict = {
        'counts': {'person': len(people), 'vehicle': len(vehicles)},
        'region_name': rname,
        'objects': region.objects,
        'timestamp': region.timestamp
      }
      event = Event(edict)
      self.publishEvent(event)
    return

def main():
  args = build_argparser().parse_args()

  handler = EventHandler(args.auth, args.broker, args.resturl, args.cert, args.rootcert)
  handler.loop()
  return

if __name__ == '__main__':
  exit(main() or 0)
