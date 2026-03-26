<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# How to Build Manager Service from Source

## Prerequisites

- Complete the shared host and repository setup in [Getting Started](../../../get-started.md)

## Steps to build

- **Build manager image**:

  ```bash
  make manager
  ```

- **Rebuild manager image** (clean + build):

  ```bash
  make rebuild-manager
  ```

## Next Steps

Run the service using [Get Started](../get-started.md).
