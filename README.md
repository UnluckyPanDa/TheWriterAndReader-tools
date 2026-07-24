# TheWriterAndReader Tools

Reusable local-first tooling for TheWriterAndReader novel workspaces.

This repository contains code, prompts, templates, policies, schemas, skills, CLI entry points, and tests. It must not contain active story manuscripts, series canon, drafts, reviews, publish outputs, or machine-specific secrets.

## Repository Roles

- `cli/`: user-facing `twr` command entry points.
- `tools/`: writing, review, publish, and story-wizard tool implementations.
- `shared/`: reusable templates, policies, schemas, config helpers, and libraries.
- `.agents/skills/twr/`: the single installable cross-device skill.
- `.agents/skills/twr-*/`: compatibility tool-area skills for existing installs.
- `tests/`: validation and runtime tests.

## Runtime Config

Real config belongs outside this repository at:

```text
~/.config/the-writer-and-reader/config.yaml
```

## Install and Initialize on Another Device

In Codex, ask it to install the skill from this URL, then restart Codex:

```text
https://github.com/UnluckyPanDa/TheWriterAndReader-tools/tree/main/.agents/skills/twr
```

In the new Codex session, say `Initialize TWR` or invoke `$twr`. The skill runs
one idempotent first-use setup that:

1. provisions a private Python 3.11 runtime when needed;
2. installs the bundled TWR wheel and its declared dependencies;
3. creates `~/.config/the-writer-and-reader/config.yaml` only when missing;
4. detects reachable Ollama models and selects an installed local model for the new config;
5. checks Python, `jsonschema`, Ollama reachability, loopback permission, and configured fallback-chain models;
6. records initialization success only after `twr doctor` passes.

No repository checkout, manual virtual environment, pip command, `PYTHONPATH`,
or PATH change is required. Later runs reuse the private runtime. The only
remaining user-managed setup is provider, endpoint, model, and explicitly
enabled online credentials in the external config.

After initialization, create and validate a workspace with:

```text
twr wizard workspace init --workspace /path/to/workspace --workspace-id my-workspace
twr wizard story add --workspace /path/to/workspace --story story-1 --title "Story One" --language en
twr doctor --workspace /path/to/workspace
```

Use `config.example.yaml` as the import/export shape. Online API and Codex CLI
providers are disabled in the example until the user explicitly enables them.
Set `num_ctx` on each Ollama-backed model profile to control the context size
for that model. A request-level value overrides the selected profile, and the
profile overrides an optional provider-wide default. If none is configured,
Ollama uses its own default.

The optional Codex writing and review routes use dedicated read-only profiles.
Reviews also use one bounded evidence subagent:

```text
mkdir -p ~/.codex/twr-reviewer
mkdir -p ~/.codex/twr-reviewer/agents
cp shared/templates/codex/twr-reviewer.config.toml shared/templates/codex/twr-writer.config.toml ~/.codex/twr-reviewer/
cp shared/templates/codex/agents/twr_story_reviewer.toml ~/.codex/twr-reviewer/agents/
CODEX_HOME=~/.codex/twr-reviewer codex login
twr doctor --config ~/.config/the-writer-and-reader/config.yaml
```

Enable `codex` for reviews or `codex_writer` for writing only after that check
passes. The configured `codex_home` must be that isolated directory and must not
contain `AGENTS.md` or `AGENTS.override.md`. Each operation starts a fresh Codex
session. Set `session.retention` to `persisted` to retain the parent thread or
`ephemeral` to discard it after the run. The writing and review intelligence
maps resolve each abstract level to an explicit Codex model and reasoning
effort. Configured subagent reviews fail closed unless the child spawn, wait,
completion, and parent ordering are present in the Codex JSONL stream.

## Wizard Scaffolds

Create external workspace/story/series scaffolds with:

```text
twr wizard workspace init --workspace /path/to/workspace --workspace-id my-workspace
twr wizard story add --workspace /path/to/workspace --story story-1 --title "Story One" --language en
twr wizard series add --workspace /path/to/workspace --series series-1 --title "Series One"
```

Wizard commands refuse to overwrite existing workspace, story, or series targets.

New story scaffolds include `canon/relationship_graph.yaml`. For an existing
story, initialize the graph explicitly, edit its character and relationship
records, then build a self-contained local 3D viewer:

```text
twr wizard relation-plot init --workspace /path/to/workspace --story story-1
twr wizard relation-plot build --workspace /path/to/workspace --story story-1
```

The viewer is written to
`stories/<story-id>/build/relation-plot/index.html`. It supports rotation,
zooming, search, group and relationship filters, chapter visibility, and graph
selection, neighborhood focus, and PNG export without loading scripts or story
data from the internet.

## Local Web GUI

Launch the local tools control room with an optional initial workspace:

```text
twr web --workspace /path/to/workspace
```

The GUI opens on `http://127.0.0.1:8765/` and can initialize workspaces, add
stories and series, build writing/review/publish packs, generate drafts, run
reviewers, validate configuration, and build or open the 3D relationship plot.
Configuration path, validation, import, and export operations are also
available. Its Reader section provides chapter reading with `[[wiki_key]]`
links into canon and storyline pages. Writing, Review, Storyline, Relations,
Publishing, and System are separate sections; the Review section stores user
comments per chapter. The workspace bar includes a native folder picker and a
history of previously loaded workspaces. Theme and workspace history are saved
in the local user settings file at `~/.config/the-writer-and-reader/ui-settings.yaml`.
The System tab also lets the user switch the interface between English and
Traditional Chinese (`繁體中文`).
The GUI invokes a fixed allowlist of existing tool functions and does not
expose an arbitrary command or shell endpoint. Use `--no-open` to start the
server without opening a browser, or `--port <port>` to select a different
loopback port.

For account login and external HTTPS access, see
[`docs/web-auth.md`](docs/web-auth.md). The supported setup uses Supabase Auth
for login and Tailscale Serve or Funnel for the path to the loopback server.

## Story Writing and Review Skills

Use the unified `twr` skill for setup, writing, review, publishing, and wizard
workflows. Existing `twr-writing-tool`, `twr-review-tool`, `twr-publish-tool`,
and `twr-story-wizard` installs remain compatible. All skills operate on an
external story workspace; do not use this tools repository as the story
workspace.

Normal chapter flow:

```text
twr write pack --workspace /path/to/workspace --story story-1 --chapter 1
twr write draft --workspace /path/to/workspace --story story-1 --chapter 1
twr write diagnose --workspace /path/to/workspace --story story-1 --chapter 1
twr review pack --workspace /path/to/workspace --story story-1 --chapter 1
twr review run --workspace /path/to/workspace --story story-1 --chapter 1
twr write revise --workspace /path/to/workspace --story story-1 --chapter 1 --mode strengthen-viewpoint
twr review run --workspace /path/to/workspace --story story-1 --chapter 1
twr write accept --workspace /path/to/workspace --story story-1 --chapter 1
```

For private multi-device review, keep one active writer for the chapter and
use the append-only review handoff protocol:

```text
twr review prepare --workspace /path/to/workspace --story story-1 --chapter 1
twr review execute --workspace /path/to/workspace --story story-1 --chapter 1 --request <request.json>
twr review apply --workspace /path/to/workspace --story story-1 --chapter 1 --request <request.json> --result <review_result.json>
```

Execution writes only a run-scoped result bundle. Apply validates the request,
draft SHA, review-input fingerprint, complete reviewer set, and run binding
before promoting canonical V1 records and rebuilding the gate last. Review
normalization accepts current/legacy JSON or Markdown, fenced/embedded JSON,
and semantically clear prose while preserving raw output in sidecar receipts.
See [`docs/multi-device-workflow.md`](docs/multi-device-workflow.md).

For explicit scene control, use:

```text
twr write plan-scene --workspace /path/to/workspace --story story-1 --chapter 1
twr write draft-scene --workspace /path/to/workspace --story story-1 --chapter 1 --scene scene-1
twr write assemble-chapter --workspace /path/to/workspace --story story-1 --chapter 1
```

Targeted revision modes are `compress`, `deepen`, `de-duplicate`,
`improve-dialogue`, `strengthen-viewpoint`, `rebalance-exposition`,
`improve-transition`, `strengthen-hook`, and `prose-polish`. Rebuild only the
Novelness Gate from current evidence with `twr review novelness`.
Use `twr write revise-scene --scene <id> --mode <mode>` for a local issue in an
active scene draft; neighboring scenes and the assembled chapter are untouched.
When a writer disputes one cited issue, save one explanation and run the
higher-intelligence check with `twr review rereview --reviewer <id>
--explanation-file <path>`. A rejected explanation requires prose revision; the
same reviewer cannot receive a second explanation for that chapter.

Writing reads the selected story config, writer profile, canon, storyline, prior
context, and `context/write_pack.md`, then writes generated outputs inside the
selected story folder. Review reads the selected story config, reviewer config,
standard reviewers, target draft, canon, reveal lock, storyline, and
`context/review_pack.md`, then writes review outputs inside the selected story
folder.

`twr write draft` rebuilds a relevance-bounded write pack, validates a scene
contract and action skeleton, drafts each scene, deepens the assembled prose,
compresses repeated meaning, polishes voice and rhythm, and records deterministic
diagnostics. `twr review run` records correctness and novelness independently;
acceptance requires continuity, reveal-lock, editor, pacing, tone, and character
review results. Exact source-wording detection independently prevents a generic
review pass from accepting copied source prose. Intermediate drafts, diagnostics,
scene contracts, model attempts, context counts, and run metadata remain inside
the selected story's `runs/` directory.

Neither skill may directly edit story canon, series canon, or another story's
files. Canon-impacting findings or new facts must be recorded as proposed canon
updates inside the selected story folder.

## Safety Defaults

- Use local Ollama models first.
- Do not commit real config or API keys.
- Do not store story content in this tools repository.
- Do not edit story canon directly from writing or review tools.
- Use the unified `twr` skill for new installs; keep tool-area skills only for compatibility.
