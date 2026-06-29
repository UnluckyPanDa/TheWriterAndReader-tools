# Review Policy

This policy applies to `twr review` actions and to any agent using
`twr-review-tool`.

## Required Inputs

Before reviewing, load:

1. External tool config and workspace config.
2. The selected `story.yaml`.
3. `reviewers/reviewer_config.yaml`.
4. Standard reviewer definitions from `tools/review/standard-reviewers/`.
5. Copied series reviewers from `reviewers/series/` when configured.
6. Story special reviewers from `reviewers/special/` when configured.
7. The current review pack from `context/review_pack.md` when available.
8. The target draft, chapter, explanation, or series update.
9. Accepted canon, reveal lock, chapter plan, prior accepted chapters, and state
   files needed to judge the target.

## Reviewer Order

Run reviewer layers in this order:

1. Standard reviewers.
2. Series reviewers.
3. Story special reviewers.
4. Combined review.
5. Review gate.

Do not silently disable, skip, or downgrade a reviewer. A blocking reviewer may
be skipped only when the reviewer config explicitly disables it.

## Allowed Writes

Review tools may write review reports, gate state, run metadata, and proposed
canon updates inside the selected story folder. Review tools must not directly
edit:

- `canon/`
- series canon
- series timeline files
- accepted chapter text
- reviewer definitions

## Finding Format

Actionable findings should include:

- Reviewer name.
- Severity or blocking status.
- A short title.
- Evidence from the target text or canon.
- Why it matters.
- The smallest useful fix.
- Whether it requires rewrite, canon proposal, or user decision.

Do not require changes for personal taste unless the relevant reviewer is
configured to enforce that taste. Preserve the story's declared language, genre,
voice, and writer profile.

## Re-review Rule

If a writer explains an issue instead of rewriting, the re-review must use a
higher intelligence level than the original reviewer. If the re-review keeps the
issue blocked, the writer must rewrite before the gate can clear.

## Gate Rule

A chapter may pass the review gate only when all enabled blocking reviewers are
clear or explicitly disabled in config. Pending canon updates, reveal-lock
breaks, entity alias drift, or series continuity conflicts should remain visible
in the gate result until resolved.
