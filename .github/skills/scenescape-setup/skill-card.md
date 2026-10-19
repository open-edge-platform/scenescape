<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

## Description: <br>

Deploys or resumes an Intel® SceneScape installation on a host, from gathering camera and scene inputs through calibration, reconstruction, and tracking verification. <br>

## Owner: Intel Corporation <br>

### License/Terms of Use: <br>

Apache-2.0 <br>

## Use Case: <br>

Developers and operators use this skill to bootstrap a SceneScape deployment, resume a prior deployment, or repeat a selected deployment phase using user-provided stream URLs or video files, camera IDs, scene name, and mapping choice. <br>

### Deployment Geography for Use: <br>

Global <br>

## Known Risks and Mitigations: <br>

Risk: Deployment commands can start containers, modify files in the deployment directory, and access camera streams and other configured services. Incorrect inputs or an unintended fresh deployment can disrupt existing work. <br>
Mitigation: Gather and validate deployment inputs with the user, read the skill's guardrails before any launch, and require explicit confirmation for destructive actions such as `--fresh`, deleting the deployment directory, or `docker compose down -v`. <br>

## Reference(s): <br>

- [Skill instructions](./SKILL.md) <br>
- [Deployment orchestrator](./scripts/deploy_scenescape.sh) <br>
- [Deployment guardrails](./references/agent-guardrails.md) <br>
- [Deployment and completion workflow](./references/deploy-and-complete.md) <br>

## Skill Output: <br>

**Output Type(s):** [Deployment instructions, Configuration, Shell commands, Deployment artifacts] <br>
**Output Format:** [Markdown with inline code blocks and structured deployment files] <br>
**Output Parameters:** [Deployment directory, phase, deployment status, scene UID, verification results] <br>
**Other Properties Related to Output:** [May create or update deployment files and run host Docker commands] <br>

## Ethical Considerations: <br>

Camera streams and resulting scene data may contain personal or sensitive information. Operators should ensure they have authorization to process the selected streams and follow applicable privacy, security, and retention requirements. <br>
