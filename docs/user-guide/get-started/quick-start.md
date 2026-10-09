<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Quick Start

This guide starts the Scenescape demo with one command.
For more configurable deployment options, see the [installation](./installation.md).

## Prerequisites

- Review the [System Requirements](./system-requirements.md).
- Clone or extract the Scenescape repository and change to its root directory.
- Run as a standard, non-root user who owns the repository checkout and can use `sudo`; the script uses `sudo` to install missing host packages and tools.
- Have network access for package, image, model, and tool downloads.

## Installation

From the repository root, run the bootstrap script:

```bash
./deploy.sh
```

To preview the dynamic pipeline configuration for cameras, run the bootstrap script in Kubernetes mode:

```bash
KUBERNETES=1 ./deploy.sh
```

## What `deploy.sh` Does Automatically

The script checks that it is running on a supported Debian/Ubuntu or Fedora/RHEL system, that `sudo` is available, and that the checkout is owned by a standard non-root user. It installs missing host packages with the system package manager:

- Debian/Ubuntu: `git`, `curl`, `make`, `openssl`, and `unzip`.
- Fedora/RHEL: `git`, `curl`, `make`, `openssl`, `unzip`, and `nmap-ncat`.

On Debian/Ubuntu, it also installs Docker if the Docker Compose plugin is missing. On Fedora/RHEL, Docker and Docker Compose must already be installed. The script checks installed Docker and Compose versions, generates passwords and TLS/authentication secrets, builds the core images, starts the demo video sources, uploads the demo scenes, and prints the generated `SUPASS` for login.

With `KUBERNETES=1`, the Kubernetes Makefile additionally installs missing `kind`, `kubectl`, and Helm tools (and optional `k9s`), creates or recreates the default Kind cluster, installs Cert Manager, loads the core images, deploys the chart, starts the video sources, and imports the demo scenes.

Some steps are conditional or interactive: the script asks for alternate ports if the default HTTPS or MQTT port is occupied, asks whether to upgrade an existing database when needed, and may use `sudo` to add the user to the Docker group. The Kubernetes flow deletes and recreates the default Kind cluster, so do not run it if that cluster contains workloads or data you need to keep.
