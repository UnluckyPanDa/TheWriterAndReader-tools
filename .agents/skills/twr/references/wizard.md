# Wizard workflow

Validate destination paths before creating reusable scaffolds. Existing
workspace, story, series, or canon targets must not be overwritten silently.

```bash
scripts/run-twr wizard workspace init --workspace <workspace> --workspace-id <id>
scripts/run-twr wizard story add --workspace <workspace> --story <story-id> --title <title> --language <language>
scripts/run-twr wizard series add --workspace <workspace> --series <series-id> --title <title>
scripts/run-twr wizard relation-plot init --workspace <workspace> --story <story-id>
scripts/run-twr wizard relation-plot build --workspace <workspace> --story <story-id>
```

Keep active manuscripts and private canon in the external workspace. Online
story-content generation requires explicit user enablement.
