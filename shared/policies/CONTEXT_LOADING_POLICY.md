# Context Loading Policy

Load enough context to act safely, but do not flood a task with unrelated story
or series material.

## Load Order

Use this order for story work:

1. External tool config.
2. Workspace config.
3. Selected `story.yaml`.
4. Applicable repository policies from `shared/policies/`.
5. `state/story_status.yaml` and `state/chapter_status.yaml`.
6. Generated task pack when present and fresh:
   `context/write_pack.md`, `context/review_pack.md`,
   `context/publish_pack.md`, or `context/handover.md`.
7. Accepted canon from `canon/`.
8. Storyline files from `storyline/`.
9. Writer profile or reviewer config for the active task.
10. Prior accepted chapters, summaries, drafts, reviews, or assets only when
    needed for the current chapter, gate, or publish target.

For series-aware stories, load `series.yaml`, `series_canon.md`,
`timeline.md`, `timeline_states.md`, and `context/series_pack.md` only according
to the selected story's `series` and `timeline_position.canon_visibility`
settings.

## Minimal Context Rule

Load the narrowest set of files that can answer the current task:

- For writing, prefer the active write pack plus the relevant canon and chapter
  plan.
- For review, prefer the active review pack, reviewer config, target draft or
  chapter, accepted canon, and reveal lock.
- For publish, prefer the active publish pack, accepted chapters, publish config,
  visual bible, and approved assets.
- For wizard and canon work, load the relevant template, target config, current
  canon, and state files before writing.

## Freshness Rule

Generated packs are summaries, not authority. If a pack conflicts with
`story.yaml`, state files, accepted canon, accepted chapters, or current reviewer
config, treat the source file as authoritative and regenerate or mark the pack
stale.

## Missing Context

If required context cannot be found:

- Do not guess canon, paths, story IDs, reviewer enablement, gate state, or
  timeline facts.
- Report the missing file or field.
- Continue only when the task can be completed safely without that fact.

## Precedence

When loaded files disagree, use this precedence:

1. Explicit user instruction for the current run.
2. Repository policies.
3. Story or series config.
4. State and gate files.
5. Accepted canon and accepted chapters.
6. Storyline and reveal-lock files.
7. Generated context packs.
8. Drafts, reviews, and handover notes.
