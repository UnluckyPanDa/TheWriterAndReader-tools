# Writer Policy

This policy applies to `twr write` actions and to any agent using
`twr-writing-tool`.

## Required Inputs

Before drafting, refining, explaining, or promoting prose, load:

1. External tool config and workspace config.
2. The selected story config (`story.yaml`).
3. The writer profile at the configured `writer.profile` path.
4. Current story state from `state/story_status.yaml` and
   `state/chapter_status.yaml`.
5. The current write pack from `context/write_pack.md` when available.
6. Relevant accepted canon from `canon/`.
7. Relevant storyline files from `storyline/`, especially chapter plan,
   reveal lock, part outline, and master outline.
8. Prior accepted chapters or summaries needed for continuity.
9. Review feedback when refining a draft.

Chapter drafting must rebuild the active write pack before model generation.
Do not reuse a nonempty pack without verifying its story and chapter inputs.

If a required input is missing, report the gap in the run output instead of
inventing replacement facts.

## Allowed Writes

Writing tools may write only inside the selected story folder and only to the
configured paths for:

- `drafts/`
- `chapters/`
- `summaries/`
- `handover/`
- `context/`
- `runs/`
- `state/`
- `canon_updates/pending/`

Promoting a draft to `chapters/` is allowed only when the chapter gate permits
acceptance or the user explicitly requests the promotion.

## Canon Boundary

Writing tools must not directly edit `canon/`, series canon, or series timeline
files. New facts, corrections, relationship changes, naming changes, visual
details, or timeline implications must be written as proposed updates under the
configured `canon_policy.proposed_updates_path`, normally
`canon_updates/pending/`.

Each proposed canon update must include:

- The source chapter or draft.
- The exact new or changed fact.
- Why the fact is needed.
- Whether it affects story canon, series canon, timeline state, or reveal state.

## Drafting Rules

- Keep prose consistent with accepted canon, accepted chapters, the writer
  profile, language settings, and the active chapter plan.
- Validate a scene contract with a concrete pressure and state change before
  generating chapter prose.
- Do not reveal hidden truths before the reveal lock allows them.
- Use the point of view, names, titles, and forms of address that are valid for
  the current chapter.
- Keep chapter prose free of tool commentary, analysis, review notes, and TODOs.
- Put assumptions, missing context, and canon questions in run notes or pending
  canon updates, not inside the chapter body.
- Do not repeatedly explain away the same blocking review issue. If the
  higher-intelligence re-review keeps the issue blocked, rewrite the prose.

## Conflict Handling

When instructions conflict, use this precedence:

1. Explicit user instruction for the current run.
2. Repository policies in `shared/policies/`.
3. Story config and chapter gate state.
4. Accepted canon and accepted chapters.
5. Storyline files.
6. Generated context packs.
7. Drafts and review notes.

Do not silently resolve canon conflicts. Surface the conflict and propose the
smallest safe change.
