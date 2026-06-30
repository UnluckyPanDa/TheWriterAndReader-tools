# MVP Implementation Checklist

## Current Status

- [x] Inspect existing repo structure and placeholder state.
- [x] Add package `__init__.py` files for CLI, shared libraries, and tool packages.
- [x] Implement config loading, validation, import/export, and example fallback.
- [x] Implement workspace, story, and series loaders.
- [x] Implement safe write and path rule helpers.
- [x] Implement model router and provider runners.
- [x] Implement write pack builder.
- [x] Implement draft generation.
- [x] Implement review pack, reviewer runner, review combiner, and review gate.
- [ ] Implement publish pack builder.
- [ ] Wire argparse CLI commands.
- [ ] Fill non-empty prompt templates.
- [ ] Create fixture workspace.
- [ ] Add focused pytest coverage.
- [ ] Run required CLI validation commands.
- [ ] Run `pytest`.
- [ ] Scan for empty Python files and empty prompt markdown.

## Next File To Do

`tools/publish/build_publish_pack.py`
