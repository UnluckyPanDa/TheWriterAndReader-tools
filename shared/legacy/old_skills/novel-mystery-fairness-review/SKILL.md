---
name: novel-mystery-fairness-review
description: Review mystery, suspense, and secret-driven fiction for fair clues, hidden information, premature reveals, impossible deductions, red herring quality, and reader-versus-character knowledge. Use when a chapter involves mystery logic or reveal timing.
---

# Purpose

Protect mystery fairness and spoiler timing while preserving suspense.

# Inputs

- Target chapter or outline.
- `mystery_state.md` or equivalent secret-state canon.
- Chapter number and allowed reveal boundaries.
- Previous summaries and chapter brief.

# Required context

- Known clues already revealed to the reader.
- Knowledge available to each character.
- Forbidden spoilers for the current chapter.
- Planned red herrings and true clues when documented.

# Review steps

1. Check clue placement and whether clues are visible enough in retrospect.
2. Check hidden information and whether the reader is unfairly deprived of needed facts.
3. Flag premature reveal of future twists.
4. Check impossible deductions or characters using knowledge they do not have.
5. Evaluate red herring quality and whether it misleads fairly.
6. State uncertainty where future reveal plans are not available.

# Output format

Return Markdown with:

- `## Summary`
- `## Fairness Issues`
- `## Clue Placement`
- `## Reader Knowledge`
- `## Character Knowledge`
- `## Premature Reveal Risks`
- `## Revision Tasks`

# What not to do

- Do not expose future spoilers unless the chapter is allowed to know them.
- Do not invent the solution.
- Do not make canon changes directly.
- Do not rewrite the mystery logic unless explicitly asked.
