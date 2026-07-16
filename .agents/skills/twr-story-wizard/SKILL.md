---
name: twr-story-wizard
description: "Use for TheWriterAndReader workspace, story, and series setup through the `twr wizard` workflow: initializing workspaces, adding story scaffolds, adding series scaffolds, using bundled templates, validating workspace paths, or handling story-wizard/canon-structure tasks. Use when the request mentions TWR story wizard, story setup, series setup, workspace scaffolding, or this skill by name."
---

# TWR Story Wizard Skill

## Purpose

Use this skill as the thin entry point for TheWriterAndReader story-wizard
tools. Do not store story-specific canon, storyline, reviewer profiles, or
writer profiles in the skill. Load reusable templates and policy files from the
tools repo, then write only to the selected external workspace.

## Workspace Resolution

1. If the user provides `--workspace`, a path, or a project root, use that
   workspace.
2. For workspace initialization, the target path may be new.
3. For story or series creation, the workspace must already contain
   `workspace.yaml`.
4. Never use the TheWriterAndReader tools repository itself as the story
   workspace unless the user explicitly says it is a workspace and it contains
   `workspace.yaml`.
5. If the target workspace is unclear, ask for the workspace path before
   writing files.

## Required Config Loading Order

1. Load external tool config when the requested wizard action needs model
   routing.
2. Load workspace config when operating on an existing workspace.
3. Load story or series config if modifying an existing story or series.
4. Load templates from `tools/wizard/templates/`.
5. Load relevant policies from `shared/policies/`, especially
   `SKILL_POLICY.md`, `STORY_ISOLATION_POLICY.md`, `CANON_POLICY.md`, and
   `CONTEXT_LOADING_POLICY.md`.
6. Validate output paths before writing.
7. Write only to the selected workspace.

## Safety Rules

- Do not silently overwrite canon.
- Do not directly merge series canon without approved series update.
- Create stories from templates.
- Create series from templates.
- Never invent a new folder structure.
- Existing story or series changes require explicit user intent.
- If a requested action requires canon or storyline generation, validate model
  routing before writing and keep online providers disabled unless the user
  explicitly enables them.

## Commands

Initialize workspace:

```bash
twr wizard workspace init --workspace <workspace> --workspace-id <workspace-id>
```

Add story:

```bash
twr wizard story add --workspace <workspace> --story <story-id> --title <title> --language <language>
```

Add series:

```bash
twr wizard series add --workspace <workspace> --series <series-id> --title <title>
```

Initialize and build a local 3D relationship plot:

```bash
twr wizard relation-plot init --workspace <workspace> --story <story-id>
twr wizard relation-plot build --workspace <workspace> --story <story-id>
```
