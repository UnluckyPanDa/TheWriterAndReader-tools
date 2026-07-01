# Publish Prompts

Store reusable publishing prompt fragments here.

Guidelines:
- Keep comments and instructions in English.
- Use placeholders such as `{story_title}`, `{language}`, and `{chapter_number}`.
- Do not include active story text or private canon.
- Keep multilingual examples short and generic.

## MVP Publish Prompt Fragment

Use this fragment when a publish command needs a compact instruction block:

```text
Prepare chapter {chapter_number} for {story_title} in {language}.
Use accepted chapter text and the publish pack only.
Exclude review notes, hidden canon, model metadata, and handover notes.
Report missing or blocked source material instead of silently publishing it.
```
