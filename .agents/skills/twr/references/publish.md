# Publish workflow

Publish only accepted chapter sources and keep outputs inside the selected
story publish directory.

```bash
scripts/run-twr publish pack --workspace <workspace> --story <story-id> --chapter <n>
```

Apply the requested PDF, EPUB, HTML, or asset action only when that command is
available. Require visual review for generated assets and character consistency
review when characters appear.
