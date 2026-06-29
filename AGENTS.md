# TheWriterAndReader Tools Agent Rules

## Scope

This is the tools repository. It stores reusable code, templates, prompts, policies, schemas, skills, and tests only.

## Hard Rules

- Do not add active stories or series folders to this repository.
- Do not commit real local config, API keys, tokens, or secrets.
- Use local models by default.
- Keep online providers disabled unless the user explicitly enables them.
- Writing tools must not directly edit canon.
- Review tools must not directly edit canon.
- Story wizard and canon-editing tools must validate model routing and paths before writing.
- Skills must remain thin entry points, one per tool area.

## Approved Active Skills

- `twr-writing-tool`
- `twr-review-tool`
- `twr-publish-tool`
- `twr-story-wizard`

## Content Boundary

Story and series content belongs in a separate workspace repository. Templates may define structure, but must not include active manuscript or private canon content.
