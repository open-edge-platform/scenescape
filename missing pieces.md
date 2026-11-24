<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Missing pieces for PR #2184

Status checked on 24 November 2026 against PR head `8d379c28`. The PR is a
mergeable draft. Upstream `main` has been merged into the branch. There are no
submitted reviews or inline review threads yet.

## Code and tests

- [ ] Validate and push the page-number pagination change. It removes the
  arbitrary 500-offset limit and uses Django's paginator, as the REST API does.
  Check the focused MCP tests, Django integration tests, and
  `make complexity-check SERVICE=manager` for the final commit.

## Integration and CI

- [ ] Build a fresh production Manager image with the pinned dependencies.
- [ ] Verify the MCP endpoint with PostgreSQL and through the deployed
  Apache/TLS path using a real MCP client: initialize, discover the tools,
  call both tools, and check that an invalid or revoked token is rejected.
  Record the environment and results in the PR.
- [ ] Obtain passing required CI results for the final PR head and investigate
  any failures. The earlier pre-merge run for `f457511` reported
  `action_required`; no pull-request-triggered workflow runs were returned
  for `8d379c28` when checked. Check GitHub for the current status and any
  approval or rerun needed.

## Review and finish

- [ ] Ask maintainers to review `thin-mcp`'s protocol compatibility,
  maintenance and dependency risk, including the disclosed author relationship.
- [ ] Confirm that every active API-token user should be able to read the
  exposed scene summaries. Address any authorization concerns from review.
- [ ] Update the PR description with the final test results and any remaining
  limitations, mark it ready for review, and address reviewer feedback and
  required approvals before merging.
