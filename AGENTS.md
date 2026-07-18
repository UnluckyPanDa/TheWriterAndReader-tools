# TheWriterAndReader Tools Agent Rules

## Repository Purpose

This repository contains reusable TWR tooling: CLI code, templates, prompts,
policies, schemas, skills, and tests. Keep all implementation and examples
story-neutral.

Active stories, series, manuscripts, and private canon belong in a separate
workspace repository. Templates may define their structure without containing
real story content.

## Instruction Priority

1. Follow the user's current request and preserve its scope.
2. Follow the safety and content boundaries in this file.
3. Follow established patterns in the files being changed.
4. Prefer the smallest complete change that satisfies the request.

Ask for clarification only when missing information would materially change the
result or authorize a broader action.

## Required Boundaries

- Never add active story or series folders to this repository.
- Never store real local configuration, credentials, API keys, tokens, secrets,
  private canon, or manuscript content.
- Use local models by default. Enable an online provider only when the user
  explicitly requests it.
- Writing and review tools may read canon for context; they must not edit canon.
- Story-wizard and canon-editing operations must validate model routing and
  destination paths before writing.
- Keep skills as thin workflow entry points. Use the unified `twr` skill for new
  installs and retain tool-area skills as compatibility entry points.
- Preserve public interfaces unless the requested change requires an interface
  change.

## Working Method

Before editing:

1. Check the current branch and working-tree state. Treat existing changes as
   user-owned work.
2. Inspect only the files needed to understand the requested behavior and its
   tests.
3. Briefly state the relevant architecture and a concise 3-7 step plan.

While editing:

- Make targeted changes and follow existing style, naming, error handling, and
  module boundaries.
- Prefer modifying existing code. Add a file or abstraction only when it has a
  clear reusable responsibility.
- Preserve unrelated work. Do not reformat, rename, reorganize, update
  dependencies, or change build configuration outside the request.
- Add or update focused tests when behavior changes.
- Do not perform Git write operations unless the user explicitly requests them.

After editing:

1. Run the narrowest relevant tests or validation.
2. Review the scoped diff and run `git diff --check` on changed files.
3. Report changed files, validation performed, assumptions, and remaining risks.

Use `./tests/run_tests.sh` only when the requested scope warrants the complete
Python suite. Use focused `python -m pytest ...` commands for isolated Python
changes and `node --test tests/prompt-assets.test.mjs` for prompt-asset changes.

## Approved Skills

Use the matching skill when the request falls within its workflow:

- `twr`: first-run setup and unified routing for new cross-device installs.
- `twr-writing-tool`: draft generation, continuation, refinement, handoff, and
  accepted-draft promotion.
- `twr-review-tool`: review packs, configured reviewers, review gates, and
  re-review.
- `twr-publish-tool`: publish packs and PDF, EPUB, HTML, or asset publishing.
- `twr-story-wizard`: workspace, story, series, template, and canon-structure
  setup.

Skills orchestrate the CLI and shared tooling; durable behavior belongs in the
underlying implementation, policies, schemas, prompts, and tests.

The unified `twr` skill owns first-run bootstrap and routes to the same durable
tool implementations. Its references may separate writing, review, publish,
and wizard instructions for progressive loading.
