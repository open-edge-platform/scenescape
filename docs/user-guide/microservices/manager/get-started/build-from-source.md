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

  **Expected output:** Manager image build completes successfully.

- **Rebuild manager image** (clean + build):

  ```bash
  make rebuild-manager
  ```

  **Expected output:** Existing manager image is cleaned and a fresh manager image is built successfully.

## Next Steps

Run the service using [Get Started](../get-started.md).
