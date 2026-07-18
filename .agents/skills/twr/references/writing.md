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
