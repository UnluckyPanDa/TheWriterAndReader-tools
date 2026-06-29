# Publish Policy

This policy applies to `twr publish` actions and to any agent using
`twr-publish-tool`.

## Required Inputs

Before publishing, load:

1. External tool config and workspace config.
2. The selected `story.yaml`.
3. Story state and chapter gate state.
4. The publish pack from `context/publish_pack.md` when available.
5. Accepted chapters from `chapters/`.
6. Approved summaries, front matter, back matter, and publish settings when
   configured.
7. Visual guidance from `canon/visual_bible.md` for generated assets.
8. Asset review rules and relevant reviewer config.

## Allowed Outputs

Publish tools may write only under the selected story's configured `publish/`
path and supporting story-local run or asset paths. They must not overwrite
source chapters, canon, reviewer definitions, or another story's publish folder.

Generated artifacts may include:

- PDF
- EPUB
- HTML
- publish packs
- cover images
- insert images
- asset review reports

## Content Rules

Published text must come from accepted chapters or explicitly selected source
text. Do not include:

- Draft-only material.
- Review notes.
- Handover notes.
- Hidden canon.
- Pending canon proposals.
- Tool run metadata.
- Private prompts or model routing details.

Before building a full story or part, verify chapter order and report missing,
duplicate, unaccepted, or blocked chapters.

## Asset Rules

Generated images require review before they are treated as publishable. If an
asset depicts characters, character visual consistency review is required. If an
asset depicts locations, objects, symbols, or timeline-specific designs, compare
it against accepted canon and `canon/visual_bible.md`.

Rejected assets must not be included in publish output unless the user
explicitly overrides the review result.

## Failure Rules

If required publish context is missing or stale, produce a clear gap report
instead of silently publishing incomplete output. If the output path is outside
the selected story publish folder, stop.
