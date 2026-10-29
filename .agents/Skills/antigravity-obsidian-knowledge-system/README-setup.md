# Antigravity + Obsidian Technical Knowledge System

This starter bundle contains a workspace-scoped Antigravity skill and starter templates for an Obsidian technical learning vault.

## 1. Install the skill

Copy the `.agents/` directory into the root of the project workspace opened in Antigravity.

Expected skill path:

```text
<workspace-root>/.agents/skills/project-knowledge-vault/SKILL.md
```

Antigravity's current documentation uses `.agents/skills/<skill-folder>/SKILL.md` for workspace skills. See the official [Agent skills documentation](https://www.antigravity.google/docs/skills?tab=ide).

## 2. Configure the vault path

Tell Antigravity the actual local path to your Obsidian vault, and add it to the project's trusted instructions/configuration if appropriate. Do not guess the path. Example placeholder:

```text
OBSIDIAN_VAULT_PATH: /absolute/path/to/your/ObsidianVault
PROJECT_DOCS_PATH: docs
```

Use the real path for your machine. If the vault is outside the workspace, verify that Antigravity has permission to read/write it. Do not grant broad filesystem access just for convenience.

## 3. Start small

1. Ask Antigravity to inspect the repository and the vault structure without editing anything.
2. Review its proposed documentation inventory and knowledge-note map.
3. Ask it to create one concept note and one experiment note as a pilot.
4. Review the links, source evidence, and preservation of existing notes.
5. Only then approve wider updates.

## 4. Try the skill

In Antigravity, invoke `/project-knowledge-vault` if slash-command invocation is available, or prompt:

> Use the project-knowledge-vault skill. First inspect this repository and my configured Obsidian vault without changing files. Propose a map of project modules, existing documentation, concept notes, and gaps. Ask me before creating or moving many notes.

Then try:

> Explain one important concept in this project. Trace it to source code and tests, draft an Obsidian concept note, and propose a safe experiment. Do not claim the experiment ran unless you execute it and record the actual result.

## 5. Operating model

- Repository docs: verified instructions and implementation reference.
- Obsidian: learning, conceptual understanding, experiments, and cross-project connections.
- Links: use `[[Obsidian Note]]` inside the vault and relative Markdown links in repository docs where appropriate.
- Safety: preserve existing notes, never copy secrets, and ask before destructive changes.
- Verification: distinguish facts, inferences, planned experiments, and observed results.

The skill does not continuously monitor changes by itself. Invoke it after meaningful changes or configure a separate automation workflow with explicit permissions and review.
