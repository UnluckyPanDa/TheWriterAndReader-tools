# MCP Server (Optional)

This directory provides a local MCP server so Codex App or other MCP-capable tools can call the story workbench. The CLI scripts remain the primary entry points; MCP only wraps them as tool calls.

## Safety Rules

- MCP tools do not directly overwrite `stories/<story_id>/canon/`.
- Canon changes must first be written to `stories/<story_id>/proposed_canon_updates/`.
- `accept-canon-update` still requires an explicit command and never auto-applies model suggestions.
- `write_chapter_draft` writes only to `drafts/`; if the file already exists, it creates a timestamped draft.

## Install MCP Dependencies

`requirements.txt` does not force MCP installation, so baseline setup is not blocked by package naming or version changes. To enable MCP, install it in the local virtual environment:

```bash
python -m pip install mcp
```

If MCP still does not start after installation, use the CLI first:

```bash
python scripts/novel.py doctor
python scripts/novel.py review --story _example --chapter 1
```

## Codex App Configuration Example

Manually add a snippet like this to the config file used by Codex App. Do not let this project automatically modify global `~/.codex/config.toml`.

```toml
[mcp_servers.story_workbench]
command = "/path/to/project/.venv/bin/python"
args = ["/path/to/project/shared/lib/mcp/novel_mcp_server.py"]
```

If you do not use `.venv`, replace `command` with the Python path you want to use.

## Available Tools

- `list_stories()`
- `init_story(story_id)`
- `get_story_config(story_id)`
- `build_context(story_id, chapter_number)`
- `review_chapter(story_id, chapter_number, reviewers=None)`
- `write_chapter_draft(story_id, chapter_number, brief_file=None)`
- `propose_canon_update(story_id, chapter_number)`
- `list_reviewer_profiles(story_id)`
- `add_reviewer_profile(story_id, reviewer_id, profile_text)`
