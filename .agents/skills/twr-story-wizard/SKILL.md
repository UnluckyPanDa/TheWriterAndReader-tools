# TWR Story Wizard Skill
## Purpose
Use this skill when the user asks to create a story, create a series, edit canon, edit storyline, edit writer profile, set up reviewers, copy reviewers, copy writer settings, propose series canon updates, or merge approved series updates.
Story wizard actions modify high-risk story structure and canon. They must use online-only high-accuracy model routing.
## Required Config Loading Order
1. Load external tool config.
2. Confirm story tools use online-only high-accuracy provider group.
3. Load workspace config.
4. Load story or series config if applicable.
5. Load templates from the tools repo.
6. Validate output path.
7. Write only to selected workspace.
## Safety Rules
- Do not use local-only models for canon or storyline creation.
- Do not silently overwrite canon.
- Do not directly merge series canon without approved series update.
- Create stories from templates.
- Create series from templates.
- Never invent a new folder structure.
- Existing story or series changes require explicit user intent.
## Commands
Create story:
```bash
twr wizard create-story --workspace <workspace>
```
Create series:
```bash
twr wizard create-series --workspace <workspace>
```
Propose series update:
```bash
twr wizard propose-series-update --workspace <workspace> --story <story-id>
```
Merge approved series update:
```bash
twr wizard merge-series-update --workspace <workspace> --series <series-id> --update <update-file>
```
