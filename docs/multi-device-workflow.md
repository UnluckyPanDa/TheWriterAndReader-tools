# Multi-device review workflow

The active writer remains responsible for one chapter. Review can happen in a
separate thread, device, or Git worktree and returns review artifacts to the
writer for validation and promotion.

## Prepare

On the writer worktree, build the review pack and create an immutable request:

```text
twr review prepare --workspace /path/to/workspace --story story-1 --chapter 12
```

The command writes a request below
`stories/story-1/reviews/chapter/012/handoffs/<handoff-id>/request.json`. It
binds the request to the draft SHA, review-pack SHA, reviewer configuration,
reviewer profile hashes, and expected enabled reviewers. Transfer that request
and the matching Git revision through the private repository workflow.

## Execute

On the review worktree/device, verify the host-local TWR configuration and
local model availability, then run:

```text
twr review execute --workspace /path/to/workspace --story story-1 --chapter 12 \
  --request stories/story-1/reviews/chapter/012/handoffs/<handoff-id>/request.json
```

Execution rechecks the request against the local draft and review inputs. It
does not replace current reviewer records or rebuild the current gate. The
result is an append-only bundle under `runs/chapter_012/<execution-id>/` with:

- a result manifest and digest;
- one strict V1 record per expected reviewer;
- canonical Markdown views;
- normalization receipts containing the exact raw model response, source
  format, normalization method, inferred fields, warnings, and canonical record.

Transfer the result bundle back to the writer worktree without changing the
active draft.

## Apply

On the writer worktree, apply the result with its original request:

```text
twr review apply --workspace /path/to/workspace --story story-1 --chapter 12 \
  --request stories/story-1/reviews/chapter/012/handoffs/<handoff-id>/request.json \
  --result runs/chapter_012/<execution-id>/review_handoff/review_result.json
```

Apply rejects a wrong story/chapter, changed draft, changed review-input
fingerprint, invalid digest, missing reviewer, mixed execution IDs, malformed
record, or incomplete result before current records are changed. Promotion is
gate-last. Reapplying the same result is idempotent.

After apply, inspect the current gate and continue the normal flow. A reviewer
result can recommend revision; it never edits canon or the active draft.

## Older artifacts and flexible output

The importer content-sniffs current V1 JSON, older result bundles, current or
legacy Markdown, fenced/embedded JSON, and usable prose. It derives invocation
identity, severity counts, deterministic issue IDs, rewrite scope, and gate
recommendation. It preserves the original bytes in a sidecar receipt and keeps
the existing V1 record shape so older TWR versions can read the promoted
record. Evidence-free or semantically contradictory output remains blocked.
