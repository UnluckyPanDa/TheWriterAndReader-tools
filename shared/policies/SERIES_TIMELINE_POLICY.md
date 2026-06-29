# Series Timeline Policy

Series canon and timeline state coordinate facts across multiple stories. They
are approval-based and must not be changed silently by story-local work.

## Series Sources

Use these series files when a story has `series.enabled: true`:

- `series.yaml`
- `series_canon.md`
- `timeline.md`
- `timeline_states.md`
- `context/series_pack.md`
- `reviewers/series_continuity/`

Load series facts according to the story's `timeline_position` and
`canon_visibility` settings.

## Timeline State

Timeline records should identify:

- Event or state name.
- Absolute date, relative date, era, or ordering anchor.
- Affected stories and chapters.
- Affected characters, places, objects, organizations, or rules.
- Whether the fact is public, private, hidden, or not yet visible to the active
  story.
- Dependencies and conflicts.

## Story Interaction Rules

- A story may extend series canon only when the series config allows it.
- A story may not override series canon when
  `inheritance.stories_may_override_series_canon` is false.
- Story-local tools must propose series changes rather than writing directly to
  series canon or timeline files.
- Story-local context may include events before and during the story only as
  allowed by `timeline_position.canon_visibility`.
- Events after the story must not leak into drafts, reviews, or publish outputs
  unless the story config explicitly permits loading them.

## Review Rules

Series continuity reviewers should check:

- Cross-story continuity.
- Timeline ordering.
- Entity state continuity.
- Name and alias state.
- Rule state.
- Reveal visibility.

Conflicts should produce review findings or pending series update proposals, not
silent edits.

## Merge Rules

Approved series updates may be merged only through the series update workflow.
The merge must preserve auditability by recording source story, source chapter or
run, approval status, affected files, and any rejected alternatives.
