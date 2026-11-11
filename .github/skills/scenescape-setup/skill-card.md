<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

## Description:

Deploys or resumes a Scenescape installation on a host, from gathering camera and scene inputs through calibration, reconstruction, and tracking verification.

## Owner: Intel Corporation

### License/Terms of Use:

Apache-2.0

## Use Case:

Developers and operators use this skill to bootstrap a Scenescape deployment, resume a prior deployment, or repeat a selected deployment phase using user-provided stream URLs or video files, camera IDs, scene name, and mapping choice.

### Deployment Geography for Use:

Global

## Known Risks and Mitigations:

Risk: Deployment commands can start containers, modify files in the deployment directory, and access camera streams and other configured services. Incorrect inputs or an unintended fresh deployment can disrupt existing work.
Mitigation: Gather and validate deployment inputs with the user, read the skill's guardrails before any launch, and require explicit confirmation for destructive actions such as `--fresh`, deleting the deployment directory, or `docker compose down -v`.

## Reference(s):

- [Skill instructions](./SKILL.md)
- [Deployment orchestrator](./scripts/deploy_scenescape.sh)
- [Deployment guardrails](./references/agent-guardrails.md)
- [Deployment and completion workflow](./references/deploy-and-complete.md)

## Skill Output:

**Output Type(s):** [Deployment instructions, Configuration, Shell commands, Deployment artifacts]
**Output Format:** [Markdown with inline code blocks and structured deployment files]
**Output Parameters:** [Deployment directory, phase, deployment status, scene UID, verification results]
**Other Properties Related to Output:** [May create or update deployment files and run host Docker commands]

## Ethical Considerations:

Camera streams and resulting scene data may contain personal or sensitive information. Operators should ensure they have authorization to process the selected streams and follow applicable privacy, security, and retention requirements.
