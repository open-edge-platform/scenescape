## 📝 Description

Adds **ADR 12 — MLOps Integration and Reuse** under [docs/adr/0012-mlops-integration-reuse.md](docs/adr/0012-mlops-integration-reuse.md).

The ADR records the architectural decision for SceneScape to delegate selected capabilities to, and reuse, existing/upcoming Intel® Open-Edge-Platform (OEP) components: Model Downloader, ViPPET, DLSPS, Stream Manager, and Geti.

Status: **Proposed**. A follow-up Design Doc will be introduced in a separate PR (link: TBD).

<!--
No related GitHub issue. Internal JIRA ticket reference (if any) belongs in the PR title per the checklist below.
-->

## ✨ Type of Change

Select the type of change your PR introduces:

- [ ] 🐞 **Bug fix** – Non-breaking change which fixes an issue
- [ ] 🚀 **New feature** – Non-breaking change which adds functionality
- [ ] 🔨 **Refactor** – Non-breaking change which refactors the code base
- [ ] 💥 **Breaking change** – Changes that break existing functionality
- [x] 📚 **Documentation update**
- [ ] 🔒 **Security update**
- [ ] 🧪 **Tests**
- [ ] 🚂 **CI**

## 🧪 Testing Scenarios

Documentation-only change. No runtime code or build artifacts are affected.

- [x] ✅ Tested manually (Markdown rendering reviewed; ADR follows [`docs/adr/template.md`](docs/adr/template.md) and the workflow in [`docs/README.md`](docs/README.md); external component links verified to resolve)
- [ ] 🤖 Ran automated end-to-end tests *(not applicable — no code changes)*

## ✅ Checklist

Before submitting the PR, ensure the following:

- [x] 🔍 PR title is clear and descriptive
- [ ] 📝 For internal contributors: If applicable, include the JIRA ticket number (e.g., ITEP-123456) in the PR **title**. Do **not** include full URLs
- [x] 💬 I have commented my code, especially in hard-to-understand areas *(not applicable — documentation only)*
- [x] 📄 I have made corresponding changes to the documentation *(this PR adds documentation)*
- [x] ✅ I have added tests that prove my fix is effective or my feature works *(not applicable — no functional change)*
