# Canon Policy

Canon is the accepted source of truth for a story or series. Writing and review
tools may propose changes, but they must not directly edit accepted canon.

## Canon Files

Story canon normally lives in:

- `canon/canon.md`
- `canon/characters.md`
- `canon/relationships_and_names.md`
- `canon/relationship_graph.yaml`
- `canon/locations_objects.md`
- `canon/hidden_truth.md`
- `canon/visual_bible.md`

Series canon normally lives in:

- `series_canon.md`
- `timeline.md`
- `timeline_states.md`

## Direct Edit Rules

- Writing tools must not directly edit accepted story or series canon.
- Review tools must not directly edit accepted story or series canon.
- Publish tools must not directly edit accepted story or series canon.
- Wizard tools may edit canon only when the user explicitly requested canon or
  storyline maintenance and the operation is permitted by config.
- Series canon changes require approved series updates when the series config
  says approval is required.

## Proposed Updates

Use the configured `canon_policy.proposed_updates_path`, normally
`canon_updates/pending/`, for proposed changes.

Every proposal must include:

- Status: pending, approved, rejected, merged, or superseded.
- Scope: story canon, series canon, timeline, reveal state, visual bible, entity
  alias, relationship, location, object, or rule.
- Source: chapter, draft, review, user instruction, or wizard run.
- Exact current fact when known.
- Exact proposed fact.
- Reason for the change.
- Affected files if accepted.
- Reviewer or user approval requirements.

## Acceptance Rules

Accepted canon changes should be small, explicit, and traceable. Do not merge a
proposal if it conflicts with accepted chapters, reveal locks, entity aliases, or
series timeline state unless the conflict is intentionally resolved in the same
operation.

Rejected or superseded proposals should remain auditable; do not erase the fact
that they existed.

## Conflict Precedence

When canon sources conflict, use this precedence:

1. Explicit user instruction for the current run.
2. Accepted story canon and approved series canon visible to the story.
3. Accepted chapters.
4. Approved canon update records not yet merged.
5. Storyline and outline files.
6. Pending canon update proposals.
7. Drafts, reviews, and generated packs.

If the conflict changes reader-visible facts, reveal timing, relationships,
timeline state, or visual continuity, stop and surface it instead of guessing.

## Hidden Truths

Hidden truths are canon, but they are not automatically available to every
reader-facing output or viewpoint character. Writing, review, and publish tools
must respect reveal-lock and timeline visibility settings before exposing hidden
facts.
