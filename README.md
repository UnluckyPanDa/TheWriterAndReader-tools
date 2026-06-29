# TheWriterAndReader Tools

Reusable local-first tooling for TheWriterAndReader novel workspaces.

This repository contains code, prompts, templates, policies, schemas, skills, CLI entry points, and tests. It must not contain active story manuscripts, series canon, drafts, reviews, publish outputs, or machine-specific secrets.

## Repository Roles

- `cli/`: user-facing `twr` command entry points.
- `tools/`: writing, review, publish, and story-wizard tool implementations.
- `shared/`: reusable templates, policies, schemas, config helpers, and libraries.
- `.agents/skills/`: thin tool-area skills only.
- `tests/`: validation and runtime tests.

## Runtime Config

Real config belongs outside this repository at:

```text
~/.config/the-writer-and-reader/config.yaml
```

Use `config.example.yaml` as the import/export shape. Online providers are disabled in the example until the user explicitly enables them.

## Safety Defaults

- Use local Ollama models first.
- Do not commit real config or API keys.
- Do not store story content in this tools repository.
- Do not edit story canon directly from writing or review tools.
- Use one skill per tool area, not one skill per reviewer or role.
