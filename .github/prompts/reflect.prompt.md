---
agent: agent
description: "Reflect on this conversation and suggest instruction updates"
---

# Self-Reflection Task

## Instruction Placement Rule (Critical)

Before proposing documentation changes, apply this hierarchy:

1. Put detailed procedural policy in the most specific skill file under `.github/skills/`.
2. Keep `.github/copilot-instructions.md` as orchestration/entry-point guidance with pointers to skill files.
3. Keep `Agents.md` files service-specific with concrete examples and commands, not duplicated global policy text.
4. Do not duplicate the same checklist/policy text across global instructions and skill files.
5. If overlap is unavoidable, keep one canonical source and replace duplicates with short references.

6. Review the entire conversation history.
7. Identify patterns where I had to correct you or clarify my intent.
8. Suggest specific additions or modifications to the `.github/copilot-instructions.md`, files under `.github/skills` directory, `Agents.md` in each service directory and other relevant documentation to prevent these issues in the future.
9. Recommend any new 'Agent Skills', tools or prompts that would have made this task easier.
10. Provide the output as a set of actionable diffs or markdown blocks.
11. Explicitly identify any missed instruction and classify the root cause as:
    - discovery failure
    - execution failure
    - verification failure
12. For test-related tasks, always include:
    - the Makefile target that should have been run
    - whether it was actually run
    - the exact command and pass/fail summary (or the blocker)
