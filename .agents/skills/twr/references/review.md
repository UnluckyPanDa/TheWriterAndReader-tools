# Review workflow

Build or refresh the review pack, then run every enabled standard, series, and
special reviewer. Do not silently skip a blocking reviewer or reuse stale
current evidence after a failed rerun.

```bash
scripts/run-twr review pack --workspace <workspace> --story <story-id> --chapter <n>
scripts/run-twr review run --workspace <workspace> --story <story-id> --chapter <n>
```

Use `review rereview` for one writer explanation when allowed. A rejected
explanation requires prose revision. Review may propose canon updates and must
not edit story or series canon directly.

Every required rewrite must reach an actual revised draft, followed by fresh
diagnostics and a full review rerun tied to that draft's SHA-256. Acceptance
requires canonical reviewer JSON, passing correctness, and an accepting
Novelness Gate. For every issue in the revision receipt, the originating
reviewer must either keep the same issue ID open or add the exact
`resolved_prior_issue:<issue_id>` reviewer note after verifying the current
prose. If every configured reviewer model fails, preserve the failed
gate and run provenance; do not replace them with a hand-written accepted gate.
