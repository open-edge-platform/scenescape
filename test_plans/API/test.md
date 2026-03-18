```text
# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: LicenseRef-Intel
```

- [LP/EI/API/SECURITYFEATURE: Security Feature Opt-In](#lpeiapisecurityfeature-security-feature-opt-in)
  - [Test suite requirements mapping](#test-suite-requirements-mapping)
  - [Test suite setup](#test-suite-setup)
    - [Hardware Requirements](#hardware-requirements)
  - [Test suite prerequisites](#test-suite-prerequisites)
    - [Follow test environment prerequisites](#follow-test-environment-prerequisites)
    - [Clean Environment](#clean-environment)
    - [Clone related repos](#clone-related-repos)
    - [Deploy Maestro and charts](#deploy-maestro-and-charts)
  - [LP/EI/API/SECURITYFEATURE/01: Onboard Host With Default Configuration](#lpeiapisecurityfeature01-onboard-host-with-default-configuration)
    - [Test summary](#test-summary)
    - [Test requirements mapping](#test-requirements-mapping)
    - [Test priority](#test-priority)
    - [Prerequisites](#prerequisites)
    - [Test steps](#test-steps)
  - [LP/EI/API/SECURITYFEATURE/02: Onboard Host With Security Feature Enabled](#lpeiapisecurityfeature02-onboard-host-with-security-feature-enabled)
    - [Test summary](#test-summary-1)
    - [Test requirements mapping](#test-requirements-mapping-1)
    - [Test priority](#test-priority-1)
    - [Prerequisites](#prerequisites-1)
    - [Test steps](#test-steps-1)
  - [LP/EI/API/SECURITYFEATURE/03: Host Provisioning with SB/FDE Enabled](#lpeiapisecurityfeature03-host-provisioning-with-sbfde-enabled)
    - [Test summary](#test-summary-2)
    - [Test requirements mapping](#test-requirements-mapping-2)
    - [Test priority](#test-priority-2)
    - [Prerequisites](#prerequisites-2)
    - [Test steps](#test-steps-2)
  - [LP/EI/API/SECURITYFEATURE/04: Host Provisioning with SB/FDE Disabled](#lpeiapisecurityfeature04-host-provisioning-with-sbfde-disabled)
    - [Test summary](#test-summary-3)
    - [Test requirements mapping](#test-requirements-mapping-3)
    - [Test priority](#test-priority-3)
    - [Prerequisites](#prerequisites-3)
    - [Test steps](#test-steps-3)

# LP/EI/API/SECURITYFEATURE: Security Feature Opt-In

`EIM Secure Boot And Full Disk Encryption`

- This test plan describes the test scenarios for enabling Secure Boot and Full Disk Encryption (FDE) features. The goal is to ensure that users can selectively enable Secure Boot and FDE, while ensuring proper system operation when these features are disabled.

## Test suite requirements mapping

- [ITEP-20450](https://jira.devtools.intel.com/browse/ITEP-20450)
- [ITEP-22574](https://jira.devtools.intel.com/browse/ITEP-22574)

## Test suite setup

### Hardware Requirements

An AWS cluster

- Jump host access
- Validation host to connect to jump host and download kubeconfig file to access EKS cluster
- An Edge Node, can be DellXR12, core platforms like ASUS and ADL-P CRB/RVP

## Test suite prerequisites

- AWS access to the cluster
- Access to jump host of the AWS cluster with ssh keys
- Cluster deployment with ArgoCD from the CI pipeline

### Follow test environment prerequisites

Cluster deployment from CI pipeline

### Clean Environment

- CI pipeline will destroy the cluster and setup new cluster with ArgoCD

### Clone related repos

- NA

### Deploy Maestro and charts

- ArgoCD deployment via CI pipeline performed by DevOps team
- Login to ArgoCD portal and verify all services are up and running without any issue [https://argocd.{clustefqdn}](https://argocd.{clustefqdn})
- Login to Validation host
- get the AWS secret keys from [https://intellogin.awsapps.com/start/#/?tab=accounts](https://intellogin.awsapps.com/start/#/?tab=accounts)

```shell
export AWS_ACCESS_KEY_ID="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
export AWS_SECRET_ACCESS_KEY="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
export AWS_SESSION_TOKEN="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"

#on one terminal / or in screen
sshuttle -r ubuntu@${jumphostIP} ${jumphostsubnet}  --ssh-cmd "ssh -i ./.ssh/${private_key}"

#on another terminal, download kubeconfig file
aws eks --region us-west-2 update-kubeconfig --name <cluster name>

#verify all pods and services are up and running
kubectl get all -A

#specifically look for orch-infra for EIM components
kubectl get pod -n orch-infra
```

## LP/EI/API/SECURITYFEATURE/01: Onboard Host With Default Configuration

Affects Versions: ITEP-3.0

### Test summary

- Verify that the host was onboaded with disabled security feature.

### Test requirements mapping

- [ITEP-20450](https://jira.devtools.intel.com/browse/ITEP-20450)
- [ITEP-22574](https://jira.devtools.intel.com/browse/ITEP-22574)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register host, providing either the serial number or the UUID and host name.
1. Boot the host device.
1. Retrieve data from host and confirm that the security features is disabled.

## LP/EI/API/SECURITYFEATURE/02: Onboard Host With Security Feature Enabled

Affects Versions: ITEP-3.0

### Test summary

- Verify that the host was onboaded with enabled security feature.

### Test requirements mapping

- [ITEP-20450](https://jira.devtools.intel.com/browse/ITEP-20450)
- [ITEP-22574](https://jira.devtools.intel.com/browse/ITEP-22574)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register host, providing either the serial number or the UUID and host name.
1. Recreate the provider with the security feature enabled.
1. Boot the host device.
1. Retrieve data from host and confirm that the security features is enabled.

## LP/EI/API/SECURITYFEATURE/03: Host Provisioning with SB/FDE Enabled

Affects Versions: ITEP-3.0

### Test summary

- Verify that the host data align with instance configuration.

### Test requirements mapping

- [ITEP-20450](https://jira.devtools.intel.com/browse/ITEP-20450)
- [ITEP-22574](https://jira.devtools.intel.com/browse/ITEP-22574)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register host, providing either the serial number or the UUID and host name.
1. Create an instance, setting security feature to `SECURITY_FEATURE_SECURE_BOOT_AND_FULL_DISK_ENCRYPTION` and associated with host.
1. Retrieve data from host and confirm that the security features matches the one in the instance.

## LP/EI/API/SECURITYFEATURE/04: Host Provisioning with SB/FDE Disabled

Affects Versions: ITEP-3.0

### Test summary

- Verify that the host data align with instance configuration.

### Test requirements mapping

- [ITEP-20450](https://jira.devtools.intel.com/browse/ITEP-20450)
- [ITEP-22574](https://jira.devtools.intel.com/browse/ITEP-22574)

### Test priority

- P1

### Prerequisites

- [Prerequisites](#test-suite-prerequisites)

### Test steps

1. Register host, providing either the serial number or the UUID and host name.
1. Create an instance, setting security feature to `SECURITY_FEATURE_NONE` and associated with host.
1. Retrieve data from host and confirm that the security features matches the one in the instance.
