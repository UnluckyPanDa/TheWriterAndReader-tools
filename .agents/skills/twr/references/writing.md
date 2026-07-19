# Writing workflow

Use explicit workspace, story, and chapter arguments. Build the context pack,
generate the draft, diagnose it, review it, revise when required, rerun review,
and accept only a draft with a complete gate whose hash matches the draft.

```bash
scripts/run-twr write pack --workspace <workspace> --story <story-id> --chapter <n>
scripts/run-twr write draft --workspace <workspace> --story <story-id> --chapter <n>
scripts/run-twr write diagnose --workspace <workspace> --story <story-id> --chapter <n>
scripts/run-twr review run --workspace <workspace> --story <story-id> --chapter <n>
scripts/run-twr write accept --workspace <workspace> --story <story-id> --chapter <n>
```

Use `plan-scene`, `draft-scene`, and `assemble-chapter` for explicit scene
control. Use `revise` or `revise-scene` with the requested supported mode for
targeted changes. Writing may read canon and must not edit it. Acceptance must
fail closed when continuity JSON or grounding remains invalid.

When review recommends revision, apply the requested chapter or scene revision,
rerun diagnostics, and rerun all required reviewers against the new draft hash.
The revision run records every canonical `rewrite_required` issue in
`revision_issue_receipt.json`. The originating reviewer must explicitly clear
each issue ID from evidence in the revised prose before the gate can pass.
Do not accept a draft from a hand-written gate, a stale review, or a revision
run that kept the original prose. A failed configured model chain may support a
manual diagnosis, but it must leave failed provenance and must not be converted
into an accepted model verdict.

## Cross-device continuation

Treat Git as the durable handoff boundary and keep one writer responsible for
an active chapter at a time. The sending device must close or explicitly fail
the current stage, make a scoped commit, push it, and report the branch, commit,
story, chapter, draft SHA-256, gate status, run id, and next action. Include the
accepted chapter, canonical review records and gates, failure provenance,
handover, state, and next instruction when those files changed.

The receiving device must start from a clean tree, fetch and fast-forward to
the reported commit, verify the branch and draft hash, then reload state,
handover, and the active instruction. Regenerate context packs and recheck the
host-local TWR config, Ollama models, loopback permission, and Codex runtime;
those surfaces do not travel with the repository. Use separate branches or
worktrees for concurrent experiments and never let two devices revise the same
active chapter simultaneously.
