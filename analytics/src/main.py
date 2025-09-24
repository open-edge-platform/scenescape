# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3

from scene_common.mqtt import PubSub

def main():
    print("Hello from Docker container!")
    print("Python version:")
    import sys
    print(sys.version)

    import datetime
    def loopForever(self):
        return self.pubsub.loopForever()
    while True:
        # Import and use other modules from src
        try:
            from utils import get_message
            msg = get_message()
        except ImportError:
            msg = "utils.py not found, running standalone"
        timestamp = datetime.datetime.now().isoformat()
        print(f"[{timestamp}] {msg}")

if __name__ == "__main__":
    main()