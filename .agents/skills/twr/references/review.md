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
