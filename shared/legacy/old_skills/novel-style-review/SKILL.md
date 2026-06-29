---
name: novel-style-review
description: Review long-form fiction prose for voice, repetition, mood, sentence rhythm, genre fit, over-explanation, show-versus-tell balance, and tonal consistency. Use when prose style or readability needs review.
---

# Purpose

Evaluate prose quality while respecting the intended voice and genre.

# Inputs

- Chapter or scene text.
- Story style notes when available.
- Chapter brief and intended mood.
- Optional reviewer profile.

# Required context

- Target genre and tone.
- Character point of view.
- Any style promises in story config or reviewer profile.

# Review steps

1. Identify dominant voice, mood, and rhythm.
2. Flag repetition in words, sentence structures, images, and emotional beats.
3. Check over-explanation, show-versus-tell balance, and clarity.
4. Check tonal consistency with scene purpose.
5. Note genre-fit issues without overriding the story's identity.
6. Provide revision tasks instead of wholesale rewrite.

# Output format

Return Markdown with:

- `## Summary`
- `## Voice Strengths`
- `## Style Issues`
- `## Repetition`
- `## Mood And Tone`
- `## Revision Tasks`

# What not to do

- Do not flatten a distinctive voice into generic prose.
- Do not rewrite the chapter directly unless explicitly asked.
- Do not introduce new canon through stylistic suggestions.
- Do not treat market taste as a canon rule.
