# SPDX-FileCopyrightText: (C) 2023 - 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""
Main application entry point
"""

def main():
    print("Hello from Docker container!")
    print("Python version:")
    import sys
    print(sys.version)
    
    # Import and use other modules from src
    try:
        from utils import get_message
        print(get_message())
    except ImportError:
        print("utils.py not found, running standalone")

if __name__ == "__main__":
    main()