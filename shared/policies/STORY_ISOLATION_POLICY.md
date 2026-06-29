# Story Isolation Policy

Every tool run must operate on one selected workspace and, when applicable, one
selected story. Story-local work stays inside that story folder.

## Path Rules

- Resolve the workspace first, then resolve the selected story from
  `story.yaml` or the explicit command arguments.
- Do not infer the story path from nearby folders when the story is ambiguous.
- Do not write outside the selected story folder for story operations.
- Do not write into another story's `canon/`, `drafts/`, `chapters/`,
  `reviewers/`, `reviews/`, `assets/`, `publish/`, or `state/` paths.
- Do not write into shared templates except when the task is explicitly to
  change the tools repo templates.

## Shared Inputs

Tools may read shared repository assets such as:

- `shared/policies/`
- `shared/templates/`
- `tools/review/standard-reviewers/`
- `tools/wizard/templates/`
- `.agents/skills/`

Those assets are reusable inputs, not story output targets.

## Series Boundary

Series-aware stories may read series canon, timeline, reviewer config, and
series context according to `story.yaml`. They may not directly write series
canon or timeline files. Series changes must be proposed, reviewed, and merged
through the approved series update workflow.

## Output Safety

Before writing, confirm the target path is inside the selected story's configured
path map. If the output path is missing, outside the story root, or points at a
different story, stop and report the unsafe target.
