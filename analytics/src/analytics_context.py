# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3

from asyncio import log
import json
import os

from scene_common.mqtt import PubSub

class AnalyticsContext:

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
        self.updateSubscriptions()
        self.updateObjectClasses()
        self.updateTRSMatrix()
        topic = PubSub.formatTopic(PubSub.DATA_REGULATED)
        self.pubsub.addCallback(topic, self.handleDatabaseMessage)
        log.info("Subscribed to", topic)
        return
    
    def updateObjectClasses(self):
        results = self.cache_manager.data_source.getAssets()
        if results and 'results' in results:
            for scene in self.scenes:
                scene.tracker.updateObjectClasses(results['results'])
        return

    def updateTRSMatrix(self):
        for scene in self.cache_manager.allScenes():
            if scene.trs_xyz_to_lla is not None:
                res = self.cache_manager.data_source.setTRSMatrix(scene.uid, scene.trs_xyz_to_lla)
                if res.errors:
                    log.info(
                            "Failed to update trs matrix for scene %s. Errors: %s",
                            scene.name,
                            res.errors,
                            )
        return

    def updateSubscriptions(self):
        log.debug("UPDATE SUBSCRIPTIONS")
        self.cache_manager.invalidate()
        if not hasattr(self, 'subscribed'):
            self.subscribed = set()
        need_subscribe = set()

        if not hasattr(self, 'subscribed_children'):
            self.subscribed_children = dict()
        need_subscribe_child = dict()

        self.scenes = self.cache_manager.allScenes()
        for scene in self.scenes:
            for camera in scene.cameras:
                need_subscribe.add((PubSub.formatTopic(PubSub.DATA_CAMERA, camera_id=camera),
                                    self.handleMovingObjectMessage))
        for sensor in scene.sensors:
            need_subscribe.add((PubSub.formatTopic(PubSub.DATA_SENSOR, sensor_id=sensor),
                                self.handleSensorMessage))
        if hasattr(scene, 'children'):
            child_scenes = self.cache_manager.data_source.getChildScenes(scene.uid)

            for info in child_scenes.get('results', []):
                if info['child_type'] == 'local':
                    self.cache_manager.sceneWithID(info['child']).retrack = info['retrack']

                    need_subscribe.add((PubSub.formatTopic(PubSub.DATA_EXTERNAL,
                                                        scene_id=info['child'], thing_type="+"),
                                        self.handleMovingObjectMessage))

                    need_subscribe.add((PubSub.formatTopic(PubSub.EVENT, region_type="+",
                                                        event_type="+",
                                                        scene_id=info['child'],
                                                        region_id="+"),
                                        self.republishEvents))
                else:
                    child_obj = ChildSceneController(self.root_cert, info, self)
                    self.cache_manager.cached_child_transforms_by_uid[info['remote_child_id']] = Scene.deserialize(info)
                    need_subscribe_child[info['remote_child_id']] = child_obj
                    need_subscribe.add((PubSub.formatTopic(PubSub.SYS_CHILDSCENE_STATUS, scene_id=info['remote_child_id']), child_obj.publishStatus))

        # disconnect old children clients
        for old_child, cobj in self.subscribed_children.items():
            if old_child not in need_subscribe_child:
                self.cache_manager.cached_child_transforms_by_uid.pop(old_child, 'None')
            cobj.loopStop()

        # connect to all children
        for new_child, cobj in need_subscribe_child.items():
            log.info(f"Connecting to remote child {new_child}")
            cobj.loopStart()

        self.subscribed_children = need_subscribe_child

        new = need_subscribe - self.subscribed
        old = self.subscribed - need_subscribe
        for topic, callback in old:
            self.pubsub.removeCallback(topic)
            log.info("Unsubscribed from", topic)
        for topic, callback in new:
            self.pubsub.addCallback(topic, callback)
            log.info("Subscribed to", topic)
        self.subscribed = need_subscribe
        return
