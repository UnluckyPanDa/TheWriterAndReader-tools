# TheWriterAndReader Tools Plan

## Current Migration Stage

The repository split is structural-first. Runtime tools should be implemented after the tools repo, workspace repo, templates, skills, and validation checks are stable.

## Runtime Implementation Order

1. Config loader and import/export commands.
2. Workspace and story loaders.
3. Model router.
4. Local CLI runner.
5. Context pack builders.
6. Draft generator.
7. Review runner and review gate.
8. Story wizard commands.
9. Publish tools.

## Design Constraints

- Tools repo stays clean of active story content.
- Workspace repo owns stories, series, canon, drafts, reviews, assets, state, and publish files.
- External config owns model routing, provider enablement, commands, fallback order, and machine-specific paths.
- Local-first is the default. Online model use must be explicit and policy-checked.
