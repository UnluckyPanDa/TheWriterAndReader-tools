# Multi-device review policy

Review is an append-only handoff around the active chapter draft. One writer
owns a chapter at a time. A review thread or device may prepare a request,
execute reviewers, and transfer the result; it may not edit the draft, canon,
accepted chapter, or current gate while executing.

`review prepare` records the story/chapter identity, draft SHA-256, review-pack
SHA-256, reviewer-input fingerprint, and expected reviewer set. `review execute`
validates that request and writes only a run-scoped result bundle. `review apply`
validates the complete result, every record identity, the request digest, the
current draft hash, and the current input fingerprint before promoting all
reviewer records and rebuilding the gate last.

Review model output is flexible. TWR preserves the exact raw response and a
normalization receipt while continuing to write strict V1 canonical JSON and
Markdown records for older readers. Schema/package version alone is not a
reason to reject an otherwise understandable legacy artifact; ambiguous,
contradictory, stale, tampered, or evidence-free content remains blocked.

Local providers remain the default. Private story content is not sent to an
online provider by this protocol.
