# TWR Review Tool Skill
## Purpose
Use this skill when the user asks to review a draft, run reviewers, manage review gates, re-review writer explanations, or review series canon updates.
This skill is the entry point for all review tools. It does not contain individual reviewer logic. Reviewer behavior must be loaded from config and reviewer files.
## Required Config Loading Order
1. Load external tool config.
2. Load workspace config.
3. Load selected story config.
4. Load reviewer config.
5. Load standard reviewers from the tools repo.
6. Load copied series reviewers from the story folder.
7. Load story special reviewers.
8. Load review model routing config.
9. Build or read review pack.
## Reviewer Layers
Run reviewers in this order:
1. Standard reviewers from `tools/review/standard-reviewers/`
2. Copied series reviewers from `stories/<story-id>/reviewers/series/`
3. Story special reviewers from `stories/<story-id>/reviewers/special/`
4. Combined review
5. Review gate
## Re-review Rule
If the writer explains an issue instead of rewriting, re-review must use a higher intelligence level than the original reviewer.
If the re-review keeps the issue blocked, the writer must rewrite.
## Safety Rules
- Never edit canon directly.
- Never edit series canon directly.
- Never write outside the selected story folder.
- Never silently disable a reviewer.
- Never skip blocking reviewers unless config says disabled.
## Commands
Review chapter:
```bash
twr review chapter --workspace <workspace> --story <story-id> --chapter <chapter>
```
Re-review issue:
```bash
twr review rereview --workspace <workspace> --story <story-id> --chapter <chapter> --issue <issue-id>
```
Review series update:
```bash
twr review series-update --workspace <workspace> --story <story-id> --update <update-file>
```
