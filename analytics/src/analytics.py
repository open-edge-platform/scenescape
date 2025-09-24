# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3

from scene_common.mqtt import PubSub

def main():
    # Example credentials and broker info, replace with actual values or config
    mqtt_auth = None
    client_cert = None
    root_cert = None
    mqtt_broker = "localhost"
    keepalive = 60

    pubsub = PubSub(mqtt_auth, client_cert, root_cert, mqtt_broker, keepalive=keepalive)

    # Subscribe to DATA_REGULATED topic (replace scene_id as needed)
    scene_id = "your_scene_id"  # TODO: set this appropriately
    pubsub.addCallback(PubSub.formatTopic(PubSub.DATA_REGULATED, scene_id=scene_id), handle_regulated_message)

    # Subscribe to ANALYTICS_CLUSTERS topic (replace scene_id as needed)
    pubsub.addCallback(PubSub.formatTopic(PubSub.ANALYTICS_CLUSTERS, scene_id=scene_id), handle_analytics_clusters_message)

    pubsub.connect()
    pubsub.loopForever()


def handle_regulated_message(client, userdata, message):
    print(f"Received DATA_REGULATED message: {message.topic}")
    # Add processing logic here
    return

def handle_analytics_clusters_message(client, userdata, message):
    print(f"Received SYS_ANALYTICS_CLUSTERS message: {message.topic}")
    # Add processing logic here
    return

if __name__ == "__main__":
    main()