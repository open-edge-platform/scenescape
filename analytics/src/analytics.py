# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3

from scene_common.mqtt import PubSub

def main():
    pubsub = PubSub()
    pubsub.start()
    pubsub.loopForever()

if __name__ == "__main__":
    main()