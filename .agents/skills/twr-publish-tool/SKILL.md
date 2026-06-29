# TWR Publish Tool Skill
## Purpose
Use this skill when the user asks to publish a story, publish a part, generate PDF/EPUB/HTML, generate covers, or generate insert illustrations.
This skill is the entry point for publish tools. It must read publish config, story config, publish pack, visual bible, and asset review rules before acting.
## Supported Actions
- publish story
- publish part
- build PDF
- build EPUB
- build HTML
- generate cover
- generate insert images
- review generated assets
## Safety Rules
- Publish outputs must stay inside the selected story publish folder.
- Generated images must be reviewed by art style reviewer.
- If characters appear in generated images, character visual consistency review is required.
- Never edit canon directly.
- Never write into another story.
## Commands
Publish:
```bash
twr publish --workspace <workspace> --story <story-id> --format <pdf|epub|html>
```
Generate asset:
```bash
twr publish asset --workspace <workspace> --story <story-id> --type <cover|insert>
```
