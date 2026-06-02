# Plan for AI-assisted creation of documents for MLOps

## Goal

Submit two separate PRs based on existing JIRA items, PowerPoint presentation and DrawIO diagrams: one for ADR and one for design doc. Prepare pull request descriptions for both using built-in GitHub template.

## Role of AI coding-agent in the process

Driving prompt:

```
AI coding-agent, I want you to be facilitator, coach and consultant in the process. If there are any inconsistencies in the architecture or design, or if some design choices and assumptions are not explicitely stated, help me identify it, flag it and support me in resolution or clarification. Do not make assuptions or design choices on your own. Help me in better analyzing, structuring and phrasing the document.
```

## Inputs

1. PowerPoint presentation
2. DrawIO diagrams
2. JIRA tickets
3. NOKIA feature request

## Outputs



## Steps

### Create ADR

  - Extract text document from presentation
  - Extract text document from JIRA tickets
  - Extract text document from NOKIA feature request
  - Treat original NOKIA feature request as a reference of what we are aiming in terms of UX, not a must have requirements
  - Help me adopt this knowledge into template docs/adr/template.md

### Create design doc

