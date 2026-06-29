# TWR Writing Tool Skill
## Purpose
Use this skill when the user asks to generate, continue, refine, rewrite, or explain a story draft.
This skill is the entry point for the writing tools. It does not contain story-specific writing rules. It must read the selected workspace, story config, writer profile, context pack, and model routing config before acting.
## Required Config Loading Order
1. Load external tool config.
2. Load workspace config.
3. Load selected story config.
4. Load writer profile from the story folder.
5. Load model routing config.
6. Build or read the current write pack.
7. Run the requested writing command.
## Supported Actions
- generate draft
- refine draft from review
- explain review issue once
- update handover
- promote accepted draft to chapter
## Safety Rules
- Never edit canon directly.
- Never edit series canon directly.
- Never write outside the selected story folder.
- Never guess the story path.
- Never repeatedly reject the same reviewer issue.
- If reviewer rejects a writer explanation, rewrite is required.
## Commands
Generate draft:
```bash
twr write draft --workspace <workspace> --story <story-id> --chapter <chapter>
```
Refine draft:
```bash
twr write refine --workspace <workspace> --story <story-id> --chapter <chapter>
```
Explain review issue:
```bash
twr write explain --workspace <workspace> --story <story-id> --chapter <chapter> --issue <issue-id>
```
