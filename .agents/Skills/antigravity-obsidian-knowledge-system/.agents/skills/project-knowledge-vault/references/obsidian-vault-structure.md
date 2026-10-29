# Obsidian Vault Structure

Use this as a starting point for a technical learning vault. Adapt it to an existing vault instead of reorganizing everything automatically.

```text
00 Home/
  Home.md
  Learning Dashboard.md
01 Projects/
  Project Template.md
  Example Project/
    Project Overview.md
    Architecture.md
    Implementation Map.md
02 Concepts/
  Concept Template.md
  Architecture/
  Languages and Frameworks/
  Databases and Data/
  APIs and Integrations/
  Testing and Tooling/
  Security/
03 Experiments/
  Experiment Template.md
04 Learning Logs/
  Learning Log Template.md
05 Decisions/
  Decision Template.md
06 Glossary/
  Glossary.md
99 Templates/
```

## Linking model

A useful learning chain is:

`Project note → Concept note → Experiment note → Learning log`

For example:

- Project: `[[Example Project]]`
- Concept: `[[Dependency Injection]]`
- Experiment: `[[DI Container Experiment - 2026-10-29]]`
- Learning log: `[[Learning Log - 2026-10-29]]`

Use the real names and dates relevant to the vault. These are examples, not claims about the user's project.

## Suggested frontmatter

Use YAML frontmatter consistently if starting a new vault. Do not add properties to every existing note without checking the vault's conventions first.

### Concept note

```yaml
---
type: concept
status: learning
tags:
  - concept
created: YYYY-MM-DD
last-reviewed: YYYY-MM-DD
projects: []
---
```

### Experiment note

```yaml
---
type: experiment
status: planned
created: YYYY-MM-DD
concepts: []
projects: []
---
```

### Project note

```yaml
---
type: project
status: active
created: YYYY-MM-DD
technologies: []
---
```

## Home note example

```markdown
# Technical Learning Home

## Active projects
- [[Project Name]]

## Concepts I'm learning
- Add concept links here.

## Recent experiments
- Add experiment links here.

## Questions to investigate
- [ ] Add an open technical question.

## Recently learned
- Add links to recent learning logs.
```

Prefer manual curation or simple queries until the system's needs are clear. Do not require community plugins for the basic workflow.
