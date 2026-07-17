# Codex Review Profile

`twr-reviewer.config.toml` is the dedicated read-only Codex execution profile
for TWR review runs. Create a separate Codex home, copy the profile into it,
and authenticate that home before enabling a `codex_cli` provider:

```text
mkdir -p ~/.codex/twr-reviewer
cp shared/templates/codex/twr-reviewer.config.toml ~/.codex/twr-reviewer/
CODEX_HOME=~/.codex/twr-reviewer codex login
```

Set the provider's `codex_home` to the same directory. Keep `AGENTS.md` and
`AGENTS.override.md` out of that directory so personal Codex instructions cannot
enter isolated reviews. TWR validates the profile, instruction isolation, and
saved Codex login with `twr doctor`.

The TWR runtime resolves the model and reasoning effort from
`review_policy.codex_intelligence_map`; the profile owns reviewer isolation,
approval, web-search, and durable reviewer instructions.
