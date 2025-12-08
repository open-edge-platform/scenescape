# Design Document: Feature X

- **Author(s)**: [Patryk Iracki](https://github.com/Irakus)
- **Date**: 2025-08-12
- **Status**: `Proposed`
- **Related ADRs**: N/A

---

## 1. Overview

Creating SceneScape Core deployment package to simplify installation for general use cases. All demos should be built on top of that package.

## 2. Goals

- Make SceneScape easier to install for general use cases in both Docker Compose and Kubernetes environments.
- Split all demos related components from the core deployment package.
- Core package should include clean SceneScape environment without any pre-populated data.
- Scenes and Cameras should be easy to add to existing Core deployment.

## 3. Non-Goals

- Explicitly state out-of-scope items

## 4. Background / Context

Current state, problems, constraints.

## 5. Proposed Design

Detailed design, diagrams, APIs, workflows.

## 6. Alternatives Considered

Brief comparison of other approaches.

## 7. Risks and Mitigations

- Risk → mitigation
- Risk → mitigation

## 8. Rollout / Migration Plan

Steps to deploy/change incrementally.

## 9. Testing & Monitoring

How will we verify correctness, performance, reliability?

## 10. Open Questions

What is still unclear or undecided?

## 11. References

Links to ADRs, issues, PRs, discussions.
