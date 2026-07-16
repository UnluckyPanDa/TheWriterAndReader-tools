---
name: twr-review-tool
description: "Use for TheWriterAndReader story review work in any installed Codex project: building review packs, reviewing drafts or chapters, running configured reviewers, managing review gates, re-reviewing writer explanations, or reviewing series canon updates through the `twr review` workflow. Use when the request mentions TWR review, chapter review, review packs, review gates, configured reviewers, or this skill by name."
---

# TWR Review Tool Skill

## Purpose

Use this skill as the thin entry point for TheWriterAndReader review tools. Do
not store individual reviewer logic in the skill. Load reviewer behavior from
the selected workspace config, story config, reviewer config, and reviewer
files.

## Workspace Resolution

1. If the user provides `--workspace`, a path, or a project root, use that
   workspace.
2. Otherwise, if the current project contains `workspace.yaml`, use the current
   project root as the workspace.
3. Otherwise, search upward from the current directory for `workspace.yaml`.
4. If no workspace is clear, ask for the workspace path before writing files.
5. Never use the TheWriterAndReader tools repository itself as the story
   workspace unless the user explicitly says it is a workspace and it contains
   `workspace.yaml`.

Use explicit command arguments after resolution:

```bash
twr review <action> --workspace <workspace> --story <story-id> --chapter <chapter>
```

If `twr` is not on `PATH`, report that the shared CLI is not installed or not on
`PATH`; do not reimplement the command in the skill.

## Required Config Loading Order

1. Load external tool config.
2. Load workspace config.
3. Load selected story config.
4. Load reviewer config.
5. Load standard reviewers from the tools repo.
6. Load copied series reviewers from the story folder.
7. Load story special reviewers.
8. Load review model routing config.
9. Build or read review pack.

## Reviewer Layers

Run reviewers in this order:

1. Standard reviewers from `tools/review/standard-reviewers/`
2. Copied series reviewers from `stories/<story-id>/reviewers/series/`
3. Story special reviewers from `stories/<story-id>/reviewers/special/`
4. Combined review
5. Review gate

## Re-review Rule

If the writer explains an issue instead of rewriting, re-review must use a higher intelligence level than the original reviewer.
If the re-review keeps the issue blocked, the writer must rewrite.

## Safety Rules

- Never edit canon directly.
- Never edit series canon directly.
- Never write outside the selected story folder.
- Never silently disable a reviewer.
- Never skip blocking reviewers unless config says disabled.

## Commands

Build review pack:

```bash
twr review pack --workspace <workspace> --story <story-id> --chapter <chapter>
```

Run configured reviewers:

```bash
twr review run --workspace <workspace> --story <story-id> --chapter <chapter>
```
