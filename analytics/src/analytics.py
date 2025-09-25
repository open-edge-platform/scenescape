# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3

from asyncio import log
import json
import os

from scene_common.mqtt import PubSub

class AnalyticsApp:

    def __init__(self, mqtt_auth, client_cert, root_cert, mqtt_broker):
        self.mqtt_auth = mqtt_auth
        self.client_cert = client_cert
        self.root_cert = root_cert
        self.mqtt_broker = mqtt_broker

        self.pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=60)
        self.pubsub.onConnect = self.onConnect
        self.pubsub.connect()

        return
    
    def loopForever(self):
        return self.pubsub.loopForever()
    
    # MQTT callbacks
    def onConnect(self, client, userdata, flags, rc):
        log.info("Connected with result code", rc)
        if rc != 0:
            exit(1)
        self.subscribed = set()
        topic = PubSub.formatTopic(PubSub.DATA_REGULATED)
        self.pubsub.addCallback(topic, self.handleDatabaseMessage)
        log.info("Subscribed to", topic)
        return
