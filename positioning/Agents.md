<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Positioning Service Agent Guide

Follow the repository guidance in [`../AGENTS.md`](../AGENTS.md) and the
Positioning deployment and camera onboarding guide in
[`../docs/user-guide/microservices/positioning/operations.md`](../docs/user-guide/microservices/positioning/operations.md).

Keep source adapters, the generic resolver shell, and pose models independently
testable. Never put device credentials or lab-specific camera endpoints in source,
tracked configuration, or logs. Preserve the Manager's home calibration; runtime
pose calculation must not rewrite it.
