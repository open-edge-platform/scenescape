# SceneScape Documentation

This repository organizes project documentation into three categories:

- **ADRs (Architecture Decision Records)** → Capture _key architectural decisions_ and their reasoning.
- **Design Docs** → Explain _how a feature, service, or system will be built_.
- **User Guides** → Provide _how-to and operational guidance_ for developers, operators, or end users.

All documents are written in Markdown and stored in Git for version control and review.

## Directory Layout

```sh
/docs
├── adr         # Short, decision-focused docs
│   ├── 0001-record-architecture-decissions.md
    └── ...
├── design      # Longer, detailed blueprints
│   ├── streaming-video-webrtc-ui.md
    └── ...
├── user-guide  # Practical usage & operations
│   ├── getting-started-guide.md
│   ├── hardening-guide.md
│   └── ...
```

## When to Write Each Doc

### ADR (Architecture Decision Record)

- Write an ADR **whenever you make a significant architectural choice**.
- It answers the **“What did we decide and why?”** question.
- Keeps history of decisions, even if they’re later changed (superseded).

Typical examples:

- Database choice (PostgreSQL vs MySQL)
- Message broker (Kafka vs RabbitMQ)
- Deployment model (Kubernetes vs Docker Compose)

ADRs are **short and focused** (1–2 pages max).

### Design Doc

- Write a Design Doc when you’re planning a **new feature, service, or system change**.
- It answers the **“How will we implement this?”** question.
- Provides enough detail for review, planning, and onboarding.

Typical examples:

- Feature redesign (e.g., Tracker performance improvements”)
- Adding a new service to the system
- Introducing caching or a new API

Design Docs are **more detailed** (5–20 pages).

### User Guide

- Write a User Guide when you need to explain **how to use, operate, or troubleshoot the system**.
- Answers **“How do I…?”** questions.

Examples:

- Deploying the app
- How to use the feature X
- Common troubleshooting steps

## Which Comes First?

- **If the decision is small but important** → Write an **ADR first** (e.g., “Use PostgreSQL”). Later, if the implementation is complex, add a **Design Doc**.
- **If the change is large and needs exploration** → Write a **Design Doc first**. Extract one or more **ADRs** from it for the final architectural choices.
- **User Guides** are written once users or operators need instructions (often after ADR + Design Doc work is done).

**Rule of thumb**:

- **ADR** = immutable record of decisions
- **Design Doc** = evolving design blueprint
- **User Guide** = practical manual for usage and operations

## Workflow

When creating a new ADR or design document, always start with the `Proposal` status. After review, the document should be updated to either `Accepted` or `Rejected`:

- **Proposal**: Initial status for new decisions or designs.
- **Accepted**: The proposal has been reviewed and approved for implementation.
- **Rejected**: The proposal was reviewed but not approved.

For ADRs, if a new ADR replaces an existing one, update the status of the old ADR to `Superseded` and reference the new ADR in the `Superseded by` field. This maintains a clear history of architectural decisions.

## Templates

- [ADR Template](adr/template.md)
- [Design Doc Template](design/template.md)
