---
name: novel-continuity-review
description: Review long-form fiction chapters for continuity, canon consistency, timeline errors, character knowledge-state errors, and contradiction risks. Use when asked to review a chapter, scene, outline, or story bible for continuity.
---

# Purpose

Find continuity errors before they enter the manuscript or canon.

# Inputs

- Target chapter, scene, outline, or bible excerpt.
- Context packet.
- Canon files and previous summaries.
- Story-specific reviewer overrides.

# Required context

- `world.md`, `rules.md`, `timeline.md`, `characters.md`, and optional `mystery_state.md`.
- Previous chapter summaries.
- Current chapter brief.

# Review steps

1. Check timeline order, dates, ages, elapsed time, travel time, and duplicated events.
2. Check names, aliases, terminology, relationship labels, and changed wording.
3. Check whether a character knows information too early or forgets known information.
4. Compare chapter claims against story bible and previous summaries.
5. Check whether events have missing consequences.
6. Separate confirmed contradictions from uncertain risks.

# Output format

Return Markdown with:

- `## Summary`
- `## Issues`
- `## Timeline Risks`
- `## Character Knowledge Risks`
- `## Canon Risks`
- `## Revision Tasks`
- `## Optional Canon Update Proposals`

Every issue must include severity, evidence, reasoning, and suggested fix direction.

# What not to do

- Do not change canon directly.
- Do not invent timeline facts.
- Do not treat absent information as contradiction unless canon requires it.
- Do not rewrite prose unless explicitly asked.
