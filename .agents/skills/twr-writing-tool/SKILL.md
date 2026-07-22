---
name: twr-writing-tool
description: "Use for TheWriterAndReader story drafting work in any installed Codex project: generating, continuing, refining, rewriting, explaining review issues, updating handoff, or promoting accepted drafts through the `twr write` workflow. Use when the request mentions TWR writing, story drafting, chapter drafting, write packs, or this skill by name."
---

# TWR Writing Tool Skill

## Purpose

Use this skill as the thin entry point for TheWriterAndReader writing tools.
Do not store story-specific writing rules in the skill. Load the selected
workspace, story config, writer profile, context pack, and model routing config
before acting.

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
twr write <action> --workspace <workspace> --story <story-id> --chapter <chapter>
```

If `twr` is not on `PATH`, report that the shared CLI is not installed or not on
`PATH`; do not reimplement the command in the skill.

## Required Config Loading Order

1. Load external tool config.
2. Load workspace config.
3. Load selected story config.
4. Load writer profile from the story folder.
5. Load model routing config.
6. Build or read the current write pack.
7. Run the requested writing command.

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

- build relevance-bounded write packs
- plan validated scene contracts and skeletons
- generate scene-by-scene, five-pass chapter drafts
- diagnose repetition, paragraph movement, and source wording reuse
- refine drafts with targeted revision modes
- explain review issue once
- update handover
- promote accepted draft to chapter

## Safety Rules

- Never edit canon directly.
- Never edit series canon directly.
- Never write outside the selected story folder.
- Never guess the story path.
- Never repeatedly reject the same reviewer issue.
- If reviewer rejects a writer explanation, rewrite is required.
- A revision command must select generated revision prose, then diagnostics and
  all required reviewers must rerun against its new hash before acceptance.
- Preserve the revision issue receipt and require originating reviewers to
  explicitly clear every prior rewrite-required issue ID on the revised prose.
- Do not turn failed model or manual review notes into an accepted gate.

## Cross-device handoff

- Keep one device as the writer for an active chapter.
- Handoff only through a scoped pushed commit. Report branch, commit, story,
  chapter, draft SHA-256, gate status, run id, and next action.
- The receiving device must use a clean tree, fast-forward to that commit,
  verify the hash, reload state/handover/instruction, and regenerate packs.
- Recheck external config, local models, loopback access, and Codex runtime on
  every receiving host; these are host-local.

## Commands

Build write pack:

```bash
twr write pack --workspace <workspace> --story <story-id> --chapter <chapter>
```

Generate draft:

```bash
twr write draft --workspace <workspace> --story <story-id> --chapter <chapter>
```

Plan, draft, and assemble scenes explicitly:

```bash
twr write plan-scene --workspace <workspace> --story <story-id> --chapter <chapter>
twr write draft-scene --workspace <workspace> --story <story-id> --chapter <chapter> --scene <scene-id>
twr write assemble-chapter --workspace <workspace> --story <story-id> --chapter <chapter>
```

Diagnose and apply a targeted revision:

```bash
twr write diagnose --workspace <workspace> --story <story-id> --chapter <chapter>
twr write revise --workspace <workspace> --story <story-id> --chapter <chapter> \
  --mode <compress|deepen|de-duplicate|improve-dialogue|strengthen-viewpoint|rebalance-exposition|improve-transition|strengthen-hook|prose-polish>
```

Promote only after the current draft has a complete accepted review gate:

```bash
twr write accept --workspace <workspace> --story <story-id> --chapter <chapter>
```

Draft stages tolerate usable prose and older chapter layouts. Mechanical
wrappers are stripped and understandable scene plans are normalized; when
planning metadata remains unusable but chapter prose is usable, the run records
an explicit unstructured-planning fallback. Canon, accepted chapters, and the
active writer draft remain outside the review handoff and are never edited by
review execution.
