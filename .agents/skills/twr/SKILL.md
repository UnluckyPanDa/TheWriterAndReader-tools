---
name: twr
description: Use for installing, initializing, configuring, diagnosing, or running any TheWriterAndReader workflow, including workspace and story setup, drafting, scene planning, review gates, accepted-draft promotion, handover, and publishing. Use when the request mentions TWR, TheWriterAndReader, `twr` commands, a TWR workspace, or this skill by name.
---

# TWR

## Initialize the runtime

Run the bundled initializer before every TWR operation:

```bash
bash scripts/bootstrap.sh --ensure
```

On Windows, run:

```powershell
& scripts/bootstrap.ps1 -Ensure
```

The initializer must provision a private Python 3.11 runtime when needed,
install the bundled TWR wheel, create the external config once, detect local
Ollama models, and run `twr doctor`. Request narrowly scoped network or
loopback approval when the environment requires it.

Never ask the user to clone the tools repository, create a virtual environment,
run pip, set `PYTHONPATH`, or add TWR to `PATH`. Never overwrite an existing
config. If initialization reports configuration issues, ask only for unresolved
provider, endpoint, or model choices and run the initializer again.

Invoke TWR through `scripts/run-twr`; it resolves the private runtime without a
PATH dependency.

## Resolve the workspace

Use an explicit workspace supplied by the user. Otherwise use the nearest
ancestor containing `workspace.yaml`. Ask for a path before writing when the
target remains ambiguous. Never use the tools or skill directory as a story
workspace.

Initialize a new workspace and story with:

```bash
scripts/run-twr wizard workspace init --workspace <workspace> --workspace-id <id>
scripts/run-twr wizard story add --workspace <workspace> --story <story-id> --title <title> --language <language>
scripts/run-twr doctor --workspace <workspace>
```

## Load the relevant workflow

- Read `references/writing.md` for drafting, revision, acceptance, and handover.
- Read `references/review.md` for reviewers, reruns, and gates.
- Read `references/publish.md` for publish packs and accepted-source publishing.
- Read `references/wizard.md` for workspace, story, series, and relation setup.

Load only the reference required for the current request. Keep online providers
disabled until the user explicitly enables them for story content. Preserve
story and series canon unless the requested wizard operation explicitly edits
their structure.
