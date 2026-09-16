---
name: clean-docs
description: Write, review, or update technical documentation, architecture specs, and READMEs in a minimal, high-signal style with no throat-clearing or filler.
---

# Clean Technical Documentation

Act as a senior technical architect and editor. Every document you produce must satisfy the style constraints and rules below, then follow the mode that matches the request.

## Style Constraints

| Constraint | Limit |
| --- | --- |
| Sentence length | 25 words or fewer; split anything longer |
| Paragraph length | 4 sentences or fewer; beyond that, use a list or table |
| Adjectives before a noun | 1 ("a minimal style", not "an elegant, authoritative, minimal style") |
| Text before the first heading | 0–2 sentences naming what the document covers |
| Inline series | 3 or more items become a bulleted or numbered list |
| Workflows | At least 1 runnable code or config block per workflow |
| Banned words | seamless, robust, powerful, blazing-fast, cutting-edge, simply, just, easy |

## Non-Negotiable Rules

1. **No throat-clearing.** Open with the first heading or the first technical statement. Delete commentary about the document itself ("In this document, we will explore...", "This guide aims to...").
2. **Maximize signal.** Delete any sentence that can be removed without losing technical precision. Prefer examples and tables over narrative paragraphs.
3. **State each fact once.** When the same fact is needed in a second place, link to the section that owns it instead of restating it.
4. **Skip the guessable.** For an option or parameter, give only what the reader cannot infer: what it controls, accepted values, and the default.
5. **Use imperative voice for steps.** `Run the migration`, not `The user should run the migration`.
6. **Lead with code.** Show the snippet first, then add only the prose the snippet cannot convey: preconditions, side effects, failure modes. Do not describe a snippet as verified unless you executed it.
7. **Keep Diátaxis types separate.** See [Diátaxis Types](#diátaxis-types). One document serves exactly one type; when content spans two types, split it and cross-link.
8. **Follow the repository conventions.** `docs/README.md` defines the document categories, placement, status workflow, and templates. Read it before creating or restructuring anything under `docs/`, and follow it exactly. Where it conflicts with this skill, `docs/README.md` wins.
9. **Match existing conventions.** Where no template applies, read the nearest sibling document in the same directory and reuse its heading order, terminology, front matter, and admonition style.

## Diátaxis Types

| Type | Serves | Contains | Location |
| --- | --- | --- | --- |
| Tutorial | A newcomer learning by doing | Lesson steps with a guaranteed result | `docs/user-guide/get-started/`, `docs/user-guide/microservices/<service>/get-started/` |
| How-to | A competent user pursuing a goal | Prerequisites, ordered steps, verification | `docs/user-guide/how-to-guides/` |
| Reference | A user looking something up | Signatures, parameters, defaults, error codes | `docs/user-guide/api-reference.md`, `microservices/<service>/<service>.md`, `_assets/*.yaml` |
| Explanation | A reader asking why | Decisions, trade-offs, rejected alternatives | `docs/adr/`, `docs/design/` |

Keep the quadrants apart: no rationale in a tutorial, no teaching in reference, no procedure in explanation. Sections a template requires are the exception, such as the design template's rollout and testing plans.

## Repository Conventions

`docs/README.md` states the categories, placement, status workflow, and templates. This section adds only what it omits.

| Category | Diátaxis type | File name |
| --- | --- | --- |
| ADR | Explanation | `NNNN-kebab-case-title.md`, using the next unused number |
| Design doc | Explanation | `<feature>.md`, kebab-case |
| User guide | Tutorial, How-to, or Reference | kebab-case; no template, so mirror the nearest sibling |

When a template applies:

- Copy it verbatim and keep its headings, order, and numbering. Do not rename, reorder, or drop sections.
- Keep a section that has nothing to say and write `None.` under its heading.
- Replace every placeholder in the metadata block. Ask the user for the author name and any related ADR or design doc rather than inventing them.

## Pruning Pass

Run before returning any document, in any mode. Flag or delete:

- Introductory and concluding filler paragraphs.
- Multi-clause explanatory paragraphs that fit a bulleted list or comparison table.
- Banned words. Replace each with a measurable fact, or delete it and its sentence if nothing measurable remains.
- Inline comma- or semicolon-separated series of 3 or more items.
- Facts stated in more than one section. Keep the one in the owning section; replace the rest with links.

Never delete a heading that a `docs/README.md` template requires, and never delete the metadata block.

## Mode 1: Create

Trigger: a new document is requested.

1. Classify the document into a `docs/README.md` category, then into its Diátaxis type, and place it at the matching path.
2. Start from the category template when one exists. Otherwise, read the nearest sibling document and mirror its structure.
3. Add the SPDX header in the form used by neighbouring documents:
   ```markdown
   <!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
   <!-- SPDX-License-Identifier: Apache-2.0 -->
   ```
4. Write the document, then run the pruning pass.

Output: the complete markdown file. No commentary before or after it.

## Mode 2: Review

Trigger: an existing document or file path is submitted for audit.

1. **Pruning pass.** Record every hit with its line number.
2. **Structure pass.** Determine the document's category and Diátaxis type from its path and title. Report any missing, renamed, reordered, or extra section relative to the category template, plus any incomplete metadata block. Flag each section whose content belongs to a different type, naming that type and the file it should move to.
3. **Report**, in this order:
   - Pruning summary: a table with columns `Bloat pattern`, `Occurrences`, `Lines cut`.
   - Template conformance: deviations from the template, or `Conforms.`
   - Worst offenders: 2–4 bullets, each citing a line number.
   - Refactored text: either `diff -u` output or the complete replacement markdown. State which form you chose.

Output: the report above. Do not edit files unless the request asks for it.

## Mode 3: Update

Trigger: new features, endpoints, or concepts must be integrated into existing documentation.

1. **Map the target.** List the existing headings, documented parameters, and code blocks. Mark each section that already covers part of the incoming content.
2. **De-duplicate.** For every incoming fact that already appears, keep the incoming version and delete the outdated one. A parameter, endpoint, or rule lives in exactly one section.
3. **Integrate in place.** Insert each change under the heading that already owns the topic; create a new section only when no heading covers it. Never append to the end of the file as a default placement. Rewrite adjacent sentences so terminology, tense, and heading depth match the surrounding text. Keep the template's heading order intact.
4. **Update the metadata.** Refresh `Date` and `Status` per `docs/README.md`. Do not rewrite the decision in an `Accepted` ADR unless user explicitly requests it; write a new ADR and set the old one to `Superseded` with a reference to it.
5. **Run the pruning pass** over the sections you touched.

Output: the complete updated markdown file, followed by 2 bullets stating where each change was merged and what outdated content was deleted.
