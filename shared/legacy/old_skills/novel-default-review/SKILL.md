---
name: novel-default-review
description: Run a broad long-form fiction review across continuity, character arc, pacing, style, canon risk, spoiler risk, and revision tasks. Use when asked for a general chapter, scene, outline, or draft review.
---

# Purpose

Provide a general reusable review for long-form fiction. This skill combines continuity, character, pacing, style, and revision planning without replacing specialist reviewers.

# Inputs

- Story id and target chapter or scene.
- Chapter draft or finished chapter.
- Context packet built from canon, chapter brief, and previous summaries.
- Global reviewer defaults and story-specific reviewer setup.
- Optional reviewer profile markdown.

# Required context

- Relevant canon from `stories/<story_id>/canon/`.
- Current chapter brief.
- Previous chapter summary when available.
- Known forbidden spoilers and mystery-state limits.

# Review steps

1. Check whether the chapter contradicts canon or previous summaries.
2. Check whether character choices follow known motivation and knowledge state.
3. Identify pacing problems, rushed reveals, weak hooks, and dense exposition.
4. Check prose voice, repetition, tone, and genre fit.
5. Flag canon risks, spoiler risks, and uncertainty instead of inventing missing facts.
6. Produce revision tasks that a writer agent or human can act on.

# Output format

Return Markdown with these sections:

- `## Summary`
- `## Strengths`
- `## Issues`
- `## Contradiction Risks`
- `## Canon Risks`
- `## Spoiler Risks`
- `## Revision Tasks`
- `## Optional Canon Update Proposals`

Each issue should include severity: `blocker`, `major`, `minor`, or `suggestion`.

# What not to do

- Do not rewrite the chapter directly unless explicitly asked.
- Do not overwrite canon files.
- Do not invent new canon to resolve a contradiction.
- Do not reveal future twists earlier than the allowed chapter.
- Do not use cloud APIs by default.
