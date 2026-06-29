# Skill Policy

## Core Rule

Use one skill per tool area. Skills are entry points into this tools repo; they
must not become story-specific prompt dumps.

Do not create one skill per reviewer, writer, model, role, story, or series.

## Approved Skills

- twr-writing-tool
- twr-review-tool
- twr-publish-tool
- twr-story-wizard

## Forbidden Skill Patterns

Do not create:

- one skill per reviewer
- one skill per character
- one skill per story
- one skill per model
- one skill per genre

## Skill Responsibility

A skill should:

1. Identify the correct tool area.
2. Read required configs.
3. Run the correct command.
4. Enforce safety rules.

A skill should not contain:

- story canon
- reviewer prompts
- writer personality
- specific model names
- API keys
- full prompt templates

## Required References

Each approved skill must point back to the reusable source of truth:

- Writing behavior: `shared/policies/WRITER_POLICY.md`
- Review behavior: `shared/policies/REVIEW_POLICY.md`
- Publish behavior: `shared/policies/PUBLISH_POLICY.md`
- Canon behavior: `shared/policies/CANON_POLICY.md`
- Context loading: `shared/policies/CONTEXT_LOADING_POLICY.md`
- Story boundaries: `shared/policies/STORY_ISOLATION_POLICY.md`
- Templates: `tools/wizard/templates/`
- Standard reviewers: `tools/review/standard-reviewers/`

## Packaging Rules

- Published skills in `.agents/skills/twr-*` should stay thin and command
  oriented.
- Do not copy story canon, generated packs, review outputs, drafts, chapters, or
  private workspace state into a reusable skill.
- Do not bake a concrete model name into a skill. Use provider groups and model
  routing config.
- Do not duplicate full reviewer prompts in skills. Reviewer behavior belongs in
  reviewer files and configs.
- When a tool contract changes, update the policy or template first, then update
  the skill summary if needed.

## Safety Rules

Skills must preserve the same write boundaries as the underlying tool:

- Writing and review skills cannot edit canon directly.
- Publish skills cannot write outside the selected story publish folder.
- Story wizard skills cannot silently overwrite existing canon or merge series
  updates without approval.
- Any ambiguous workspace, story, or series target must be resolved before the
  skill writes files.
