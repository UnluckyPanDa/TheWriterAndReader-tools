---
name: novel-reviewer-setup
description: Create or modify story-specific reviewer setup for a long-form fiction project. Use when adding, disabling, overriding, or profiling reviewers for a specific story without changing global defaults.
---

# Purpose

Help configure reviewers for one story while keeping global reviewer defaults reusable.

# Inputs

- Story id.
- Story genre or premise if already known.
- Desired reviewer additions, disables, or overrides.
- Optional reviewer profile text.

# Required context

- Global defaults in `config/reviewer_defaults.yaml`.
- Story reviewer setup at `stories/<story_id>/reviewers.yaml`.
- Optional profile files under `stories/<story_id>/reviewer_profiles/`.

# Review steps

1. Ask what kind of story this is only if the existing files do not make the setup clear.
2. Create or modify `stories/<story_id>/reviewers.yaml`.
3. Enable or disable default reviewers for this story.
4. Add custom reviewers under `custom_reviewers`.
5. Create optional profile markdown files under the story folder.
6. Preserve global defaults unless the user explicitly asks to edit them.

# Output format

Return a concise summary of:

- Reviewers enabled.
- Reviewers disabled.
- Custom reviewers added.
- Profile files created.
- Any unresolved setup questions.

# What not to do

- Do not edit `config/reviewer_defaults.yaml` unless explicitly asked.
- Do not modify canon.
- Do not create a reviewer that rewrites chapters by default.
- Do not hardcode setup to one private story.
