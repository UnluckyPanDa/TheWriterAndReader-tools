# Codex Writing and Review Profiles

`twr-writer.config.toml` generates writing directly. `twr-reviewer.config.toml`
coordinates one bounded `twr_story_reviewer` child for each review. Both run in
read-only, instruction-isolated Codex sessions.

Create a separate Codex home, install both profiles and the reviewer agent, then
authenticate that home before enabling either `codex_cli` provider:

```text
mkdir -p ~/.codex/twr-reviewer
mkdir -p ~/.codex/twr-reviewer/agents
cp shared/templates/codex/twr-reviewer.config.toml shared/templates/codex/twr-writer.config.toml ~/.codex/twr-reviewer/
cp shared/templates/codex/agents/twr_story_reviewer.toml ~/.codex/twr-reviewer/agents/
CODEX_HOME=~/.codex/twr-reviewer codex login
```

Set the provider's `codex_home` to the same directory. Keep `AGENTS.md` and
`AGENTS.override.md` out of that directory so personal Codex instructions cannot
enter isolated reviews. TWR validates the profile, instruction isolation, and
saved Codex login with `twr doctor`.

The TWR runtime resolves concrete model and reasoning settings from the writing
or review intelligence map. The profiles own isolation, approvals, web-search,
and durable role instructions. Reviewer runs fail closed unless the Codex JSONL
stream proves that exactly one child was spawned, completed through `wait`, and
finished before the parent returned its schema-constrained decision.
