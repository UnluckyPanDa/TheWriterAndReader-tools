---
name: twr-publish-tool
description: "Use for TheWriterAndReader publishing work through the `twr publish` workflow: building publish packs, preparing story or chapter publishing context, validating accepted chapter sources, checking publish boundaries, or working with PDF/EPUB/HTML/asset publishing requirements. Use when the request mentions TWR publish, publish packs, story publishing, chapter publishing, or this skill by name."
---

# TWR Publish Tool Skill

## Purpose

Use this skill as the thin entry point for TheWriterAndReader publish tools. It
must read publish policy, workspace config, story config, publish pack, visual
bible, and asset review rules before acting. Do not store story-specific
publish settings or manuscript content in the skill.

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
twr publish <action> --workspace <workspace> --story <story-id> --chapter <chapter>
```

If `twr` is not on `PATH`, report that the shared CLI is not installed or not on
`PATH`; do not reimplement the command in the skill.

## Required Config Loading Order

1. Load external tool config.
2. Load workspace config.
3. Load selected story config.
4. Load `shared/policies/PUBLISH_POLICY.md`.
5. Load `shared/policies/STORY_ISOLATION_POLICY.md`.
6. Load chapter gate state and accepted chapter sources.
7. Build or read the current publish pack.
8. Load visual guidance and asset review rules when generating or reviewing
   publish assets.

## Local Ollama Access

- TWR uses its configured local provider directly; an Ollama MCP server is not
  required.
- Before a model-backed run, verify the configured Ollama model is available
  with `ollama list`.
- If Ollama reports a loopback or sandbox permission error for
  `localhost:11434` or `127.0.0.1:11434`, retry the same TWR command with
  narrowly scoped network approval.
- Treat an unreachable local provider as a failed run. Never replace it with
  mock output unless the active config explicitly enables mock behavior for a
  test or fixture.

## Supported Actions

- build publish pack
- prepare story, part, or chapter publishing context
- build PDF, EPUB, or HTML when the corresponding publish tool exists
- generate or review cover and insert assets when the corresponding publish
  tool exists

## Safety Rules

- Publish outputs must stay inside the selected story publish folder.
- Generated images must be reviewed by art style reviewer.
- If characters appear in generated images, character visual consistency review is required.
- Never edit canon directly.
- Never write into another story.
- Published text must come from accepted chapters or explicitly selected source
  text.

## Commands

Build publish pack:

```bash
twr publish pack --workspace <workspace> --story <story-id> --chapter <chapter>
```
